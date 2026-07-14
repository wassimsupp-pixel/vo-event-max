# Performance notes (Feedback V1 — P1.6)

This document records the profiling instrumentation added and the slowness
sources identified so far. It is intentionally living: some items are fixed,
others are flagged for later once the app is exercised with real client data.

## Instrumentation added

- **Per-endpoint API timing** — `apps/web/src/lib/api.ts`, in the shared
  `request()` helper. In development (`NODE_ENV !== 'production'`) every call
  logs `"[api] METHOD /path → STATUS in Xms"` to the console. This measures the
  network + backend round-trip for each endpoint, so a slow page can be traced
  to the specific call responsible.
- **Sidebar exception-count query timing** — `apps/web/src/components/layout/Sidebar.tsx`.
  The direct Supabase `count` query logs `"[sidebar] exception count query → Xms"`
  in development.

**How to read it:** open the browser devtools console, navigate the app, and
sort by the `[api]` / `[sidebar]` prefixes. Anything consistently above ~500ms
is a candidate for optimization; note whether it is the network (Railway API in
Amsterdam), the DB (Supabase Paris), or the frontend render.

## Findings (from code review, to confirm with real data)

| Area | Observation | Status |
|------|-------------|--------|
| Sidebar polling | Was `setInterval(…, 5000)` on **every** page → 12 count queries/min per open tab, permanently. | **Fixed:** raised to 30s. Realtime subscription is the next step if instant updates are needed. |
| Auth on every request | `request()` awaits `supabase.auth.getSession()` before each fetch. Usually cached in memory, but worth confirming it is not adding latency per call. | To confirm via `[api]` logs. |
| Dashboard load | `dashboard/page.tsx` fetches participants + files + exceptions via `Promise.all` → already parallel on the client. | OK (parallelized). Confirm the backend endpoints themselves aren't serially blocking. |
| Exceptions on dashboard | `api.exceptions.list(eventId)` returns the full list to compute counts client-side. Fine at current volumes; may need a server-side count endpoint at scale. | Watch with real data. |
| Dead fallback id guard | Sidebar skipped counting for the removed fake event UUID. | **Fixed:** guard removed with the fake-data fallback (P1.1). |

## Recommendations not yet applied

1. **Supabase Realtime** for the exception badge instead of polling (removes the
   interval entirely; updates are pushed). Requires Realtime enabled on the
   `exceptions` table.
2. **Server-side aggregate counts** for the dashboard KPIs (a single
   `/events/:id/summary` returning counts) to avoid shipping full lists.
3. **Cache the Supabase session** reference in `api.ts` if the `[api]` logs show
   `getSession()` adding measurable per-call latency.

Revisit this file after running the real client Excel files (P1.3) — real row
counts will tell us which of the "watch" items actually matter.
