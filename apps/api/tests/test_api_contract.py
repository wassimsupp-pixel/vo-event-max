"""
tests/test_api_contract.py — the frontend and the backend must agree.

Why this file exists
--------------------
Four production bugs in a row were the same bug: the two halves of one API,
written separately, silently disagreeing.

  * the participant edit form PATCHed ``{first_name, last_name, ...}`` while
    the endpoint only ever accepted ``{field, value, reason}`` — saving a
    fiche failed 100% of the time, and had since the page was written;
  * the lock/unlock buttons called ``/lock`` with DELETE against routes that
    are ``/lock/{field}`` and ``/unlock/{field}``, both POST;
  * the list view rendered a Téléphone column the list query never selected;
  * every error message was read from ``message`` while FastAPI only ever
    sends ``detail``, so the API's explanations never reached a user.

None of these were catchable by the rest of the suite: those tests mock
Supabase and exercise the backend alone, so they happily agree with whatever
the backend does. Nothing compared it to what the frontend actually sends.

This test does exactly that, from the two sources of truth themselves:
``apps/web/src/lib/api.ts`` (every call the app can make) versus the live
OpenAPI schema FastAPI generates from the routers. No fixture to keep in
sync — add a route or change a model and this test re-reads both sides.

What it checks
--------------
1. Every path+method the frontend calls exists on the backend.
2. For calls whose body is a literal object, every field the endpoint marks
   required is present, and no field is sent that the endpoint does not
   declare.

Bodies built from a variable (``JSON.stringify(payload)``) are skipped for
check 2 — their shape isn't knowable statically. Those paths still get
check 1.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:3000")

from main import app  # noqa: E402

API_TS = Path(__file__).resolve().parents[2] / "web" / "src" / "lib" / "api.ts"

# `${...}`, allowing one level of nested braces so `${qs({ provider })}` and
# `${aiSummary ? '?ai_summary=true' : ''}` are captured whole.
_INTERP = re.compile(r"\$\{(?:[^{}]|\{[^{}]*\})*\}")
_METHOD = re.compile(r"method:\s*['\"](\w+)['\"]")


def _skip_if_frontend_absent():
    if not API_TS.exists():
        pytest.skip(f"frontend client not present at {API_TS}")


# ---------------------------------------------------------------------------
# Reading the frontend
# ---------------------------------------------------------------------------

def _read_string_literal(src: str, i: int) -> tuple[str | None, int]:
    """Read the string/template literal starting at ``src[i]``.
    Returns (contents_without_quotes, index_after_closing_quote)."""
    if i >= len(src):
        return None, i
    quote = src[i]
    if quote not in "'\"`":
        return None, i
    out, j = [], i + 1
    while j < len(src):
        c = src[j]
        if c == "\\":
            out.append(src[j:j + 2])
            j += 2
            continue
        if c == quote:
            return "".join(out), j + 1
        out.append(c)
        j += 1
    return None, j


def _read_call_args(src: str, i: int) -> tuple[str, int]:
    """Slice the text between the parens of a call whose '(' is at ``src[i]``,
    tracking quotes so parentheses inside strings don't unbalance it."""
    depth, j, start = 0, i, i + 1
    while j < len(src):
        c = src[j]
        if c in "'\"`":
            _, j = _read_string_literal(src, j)
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return src[start:j], j + 1
        j += 1
    return src[start:], j


def _canonical(path: str) -> str:
    """Reduce a path to comparable form: every parameter becomes '*', query
    strings are dropped.

      `/api/events/${eventId}/participants${query}` -> /api/events/*/participants
      `/api/events/{event_id}/participants`         -> /api/events/*/participants
    """
    p = _INTERP.sub("*", path)
    p = re.sub(r"\{[^}]*\}", "*", p)          # OpenAPI-style {event_id}
    p = p.split("?", 1)[0]                     # literal query string
    segments = []
    for seg in p.split("/"):
        # A trailing '*' glued to a literal segment is an interpolated query
        # suffix (`.../group${query}`), not a path parameter.
        if seg != "*" and seg.endswith("*"):
            seg = seg.rstrip("*")
        segments.append(seg)
    return "/".join(segments).rstrip("/")


def _literal_body_keys(args: str) -> set[str] | None:
    """Keys of a `body: JSON.stringify({ a, b: x, 'c': y })` literal.
    Returns None when the body is absent, a variable, or uses a spread —
    i.e. whenever the shape cannot be known from the source alone."""
    m = re.search(r"body:\s*JSON\.stringify\(", args)
    if not m:
        return None
    rest = args[m.end() - 1:]
    inner, _ = _read_call_args(rest, 0)
    inner = inner.strip()
    if not inner.startswith("{"):
        return None                      # JSON.stringify(payload)
    if "..." in inner:
        return None                      # { ...form, phone } — dynamic
    body = inner[1:-1]
    keys, depth, buf = set(), 0, []
    for ch in body:                      # split on top-level commas only
        if ch in "{[(":
            depth += 1
        elif ch in "}])":
            depth -= 1
        if ch == "," and depth == 0:
            buf, entry = [], "".join(buf)
            k = entry.split(":", 1)[0].strip().strip("'\"")
            if k:
                keys.add(k)
            continue
        buf.append(ch)
    entry = "".join(buf)
    k = entry.split(":", 1)[0].strip().strip("'\"")
    if k:
        keys.add(k)
    return keys or None


def _frontend_calls() -> list[dict]:
    """Every request() call in api.ts: method, path, literal body keys, line."""
    src = API_TS.read_text(encoding="utf-8")
    calls: list[dict] = []
    for m in re.finditer(r"\brequest\s*(?:<[^>]*>)?\s*\(", src):
        args, _ = _read_call_args(src, m.end() - 1)
        stripped = args.lstrip()
        path, _ = _read_string_literal(stripped, 0)
        if not path or not path.startswith("/api"):
            continue
        method_match = _METHOD.search(args)
        calls.append({
            "method": (method_match.group(1) if method_match else "GET").upper(),
            "path": path,
            "canonical": _canonical(path),
            "body_keys": _literal_body_keys(args),
            "line": src.count("\n", 0, m.start()) + 1,
        })
    return calls


# ---------------------------------------------------------------------------
# Reading the backend
# ---------------------------------------------------------------------------

def _backend_routes() -> dict[tuple[str, str], dict]:
    """(METHOD, canonical path) -> operation, from the generated schema."""
    spec = app.openapi()
    out = {}
    for path, methods in spec["paths"].items():
        for method, op in methods.items():
            out[(method.upper(), _canonical(path))] = {"op": op, "raw_path": path}
    return out


def _request_model(op: dict, spec: dict) -> dict | None:
    schema = (
        op.get("requestBody", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema", {})
    )
    ref = schema.get("$ref")
    if not ref:
        return None
    return spec["components"]["schemas"].get(ref.rsplit("/", 1)[-1])


# ---------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------

class TestFrontendBackendContract:
    def test_frontend_client_is_parsed(self):
        """A parser that silently matches nothing would make every check below
        pass vacuously — assert we actually read the client."""
        _skip_if_frontend_absent()
        calls = _frontend_calls()
        assert len(calls) > 50, f"only parsed {len(calls)} calls from {API_TS}"
        assert any(c["method"] == "PATCH" for c in calls)
        assert any(c["body_keys"] for c in calls)

    def test_every_frontend_call_hits_an_existing_route(self):
        _skip_if_frontend_absent()
        routes = _backend_routes()
        missing = [
            f"  api.ts:{c['line']}  {c['method']} {c['path']}"
            f"\n      -> no backend route for {c['method']} {c['canonical']}"
            for c in _frontend_calls()
            if (c["method"], c["canonical"]) not in routes
        ]
        assert not missing, (
            "Frontend calls that no backend route serves "
            "(wrong path, wrong verb, or a route that was renamed):\n"
            + "\n".join(missing)
        )

    def test_literal_request_bodies_match_their_endpoint_model(self):
        _skip_if_frontend_absent()
        spec = app.openapi()
        routes = _backend_routes()
        problems: list[str] = []

        for c in _frontend_calls():
            if not c["body_keys"]:
                continue
            route = routes.get((c["method"], c["canonical"]))
            if not route:
                continue                      # already reported by the test above
            model = _request_model(route["op"], spec)
            if not model:
                continue                      # endpoint takes no JSON body model
            declared = set(model.get("properties", {}))
            required = set(model.get("required", []))
            sent = c["body_keys"]

            for field in sorted(required - sent):
                problems.append(
                    f"  api.ts:{c['line']}  {c['method']} {c['path']}"
                    f"\n      -> required field '{field}' is never sent"
                )
            for field in sorted(sent - declared):
                problems.append(
                    f"  api.ts:{c['line']}  {c['method']} {c['path']}"
                    f"\n      -> sends '{field}', which the endpoint does not accept"
                )

        assert not problems, (
            "Request bodies that do not match the endpoint's model:\n"
            + "\n".join(problems)
        )

    @staticmethod
    def _error_handling_code() -> str:
        """api.ts's !res.ok block with comments stripped — the checks below
        must see real code, not prose that happens to mention the field."""
        src = API_TS.read_text(encoding="utf-8")
        start = src.index("if (!res.ok)")
        block = src[start:start + 1400]
        return "\n".join(
            line for line in block.splitlines()
            if not line.lstrip().startswith("//")
        )

    def test_error_responses_are_read_from_the_field_fastapi_sends(self):
        """FastAPI reports errors as {"detail": ...} — never {"message": ...}.
        Reading the wrong field silently discarded every backend explanation
        (a 409 "a consolidation is already running" reached users as a generic
        connection error). Pin the reader to the real field."""
        _skip_if_frontend_absent()
        code = self._error_handling_code()
        assert re.search(r"\.detail\b|\[['\"]detail['\"]\]", code), (
            "api.ts's error path must READ `detail` — the field FastAPI "
            "actually populates on HTTPException, the global handler, and 422s."
        )

    def test_validation_error_shape_is_handled(self):
        """422s put a LIST of objects in `detail`, not a string. Rendering that
        list straight into a message box shows the user '[object Object]'."""
        _skip_if_frontend_absent()
        assert "Array.isArray" in self._error_handling_code(), (
            "api.ts must handle `detail` arriving as an array (FastAPI 422 "
            "validation errors) as well as a string."
        )
