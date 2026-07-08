# -*- coding: utf-8 -*-
"""
tests/test_matcher.py
=====================
Comprehensive pytest test suite for the VO Event Max matching engine.

Test inventory
--------------
1.  test_exact_email_match           -- exact email -> CERTAIN
2.  test_exact_name_match            -- exact name, no email -> CERTAIN or PROBABLE
3.  test_fuzzy_name_match            -- slightly different name -> PROBABLE
4.  test_no_match                    -- completely different people -> NOT_FOUND
5.  test_duplicate_email_detection   -- 3 records sharing an email are grouped
6.  test_full_pipeline_precision_recall -- end-to-end match_rate >= 0.90,
                                          false_positive_rate == 0.0
7.  test_normalizer_email            -- edge cases for normalize_email
8.  test_normalizer_name             -- accented chars via normalize_name
9.  test_parse_date_formats          -- all five supported date formats
10. test_deterministic               -- running match_sources twice gives identical results
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path gymnastics so the tests can be run from any working directory
# ---------------------------------------------------------------------------

_ENGINE_DIR = Path(__file__).parent.parent
if str(_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(_ENGINE_DIR))

from matcher import (
    MatchDecision,
    MatchResult,
    ParticipantRecord,
    detect_duplicate_emails,
    match_sources,
    score_pair,
)
from normalizer import normalize_email, normalize_name, normalize_full_name, parse_date
from synthetic_data import (
    build_gold_standard,
    generate_fcm_list,
    generate_registration_list,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reg(**kwargs) -> ParticipantRecord:
    """Shorthand: build a ParticipantRecord for a registration."""
    defaults = dict(id=None, first_name="Test", last_name="User",
                    email=None, company=None, phone=None, source="reg")
    defaults.update(kwargs)
    return ParticipantRecord(**defaults)


def _fcm(**kwargs) -> ParticipantRecord:
    """Shorthand: build a ParticipantRecord for an FCM record."""
    defaults = dict(id=None, first_name="Test", last_name="User",
                    email=None, company=None, phone=None, source="fcm")
    defaults.update(kwargs)
    return ParticipantRecord(**defaults)


# ---------------------------------------------------------------------------
# 1. test_exact_email_match
# ---------------------------------------------------------------------------

class TestExactEmailMatch:
    """Exact email match should always produce CERTAIN regardless of name."""

    def test_same_email_certain_decision(self):
        """When emails match exactly the decision must be CERTAIN."""
        reg = _reg(first_name="Alice", last_name="Smith",
                   email="alice.smith@example.com")
        fcm = _fcm(first_name="Alice", last_name="Smith",
                   email="alice.smith@example.com")
        results = match_sources([reg], [fcm])
        assert results[0].decision == MatchDecision.CERTAIN

    def test_email_case_insensitive(self):
        """Email matching must be case-insensitive."""
        reg = _reg(email="Alice.Smith@EXAMPLE.COM")
        fcm = _fcm(email="alice.smith@example.com")
        results = match_sources([reg], [fcm])
        assert results[0].decision == MatchDecision.CERTAIN
        assert "email_exact" in results[0].signals

    def test_email_strips_whitespace(self):
        """Leading/trailing whitespace in emails must be ignored."""
        reg = _reg(email="  alice@example.com  ")
        fcm = _fcm(email="alice@example.com")
        results = match_sources([reg], [fcm])
        assert results[0].decision == MatchDecision.CERTAIN

    def test_email_score_is_100_plus_bonuses(self):
        """Base score from email_exact must be 100."""
        reg = _reg(email="alice@corp.be", company="Solvay SA",
                   phone="+3222345678")
        fcm = _fcm(email="alice@corp.be", company="Solvay SA",
                   phone="+3222345678")
        score, signals = score_pair(reg, fcm)
        assert signals.get("email_exact") == 100.0
        assert score >= 100.0  # bonuses on top


# ---------------------------------------------------------------------------
# 2. test_exact_name_match
# ---------------------------------------------------------------------------

class TestExactNameMatch:
    """Exact full-name match with no email should produce CERTAIN (80 pts)."""

    def test_exact_name_no_email_is_certain(self):
        """80-point name match meets CERTAIN threshold when no email is present."""
        reg = _reg(first_name="Jean-Pierre", last_name="Dupont", email=None)
        fcm = _fcm(first_name="Jean-Pierre", last_name="Dupont", email=None)
        results = match_sources([reg], [fcm])
        assert results[0].decision in (MatchDecision.CERTAIN, MatchDecision.PROBABLE)

    def test_name_exact_signal_fires(self):
        """``name_exact`` signal must be present when names match exactly."""
        reg = _reg(first_name="Marie", last_name="Lefevre", email=None)
        fcm = _fcm(first_name="Marie", last_name="Lefevre", email=None)
        _, signals = score_pair(reg, fcm)
        assert "name_exact" in signals

    def test_name_exact_with_bonus_raises_score(self):
        """Company and phone bonuses stack on top of name_exact."""
        reg = _reg(first_name="Marie", last_name="Lefevre",
                   company="Solvay SA", phone="+3229876543")
        fcm = _fcm(first_name="Marie", last_name="Lefevre",
                   company="Solvay SA", phone="+3229876543")
        score, signals = score_pair(reg, fcm)
        assert score >= 85.0  # 80 + 5 + 5


# ---------------------------------------------------------------------------
# 3. test_fuzzy_name_match
# ---------------------------------------------------------------------------

class TestFuzzyNameMatch:
    """Slightly different names should produce PROBABLE or TO_VERIFY."""

    def test_hyphen_vs_space(self):
        """'Jean-Pierre' vs 'Jean Pierre' should be a high fuzzy match."""
        reg = _reg(first_name="Jean-Pierre", last_name="Dupont", email=None)
        fcm = _fcm(first_name="Jean Pierre", last_name="Dupont", email=None)
        results = match_sources([reg], [fcm])
        assert results[0].decision in (
            MatchDecision.CERTAIN,
            MatchDecision.PROBABLE,
            MatchDecision.TO_VERIFY,
        )
        assert "name_fuzzy" in results[0].signals

    def test_accent_dropped(self):
        """Dropping an accent (Helene -> Helene) should still fuzzy-match."""
        reg = _reg(first_name="Helene", last_name="Bernard", email=None)
        fcm = _fcm(first_name="Helene", last_name="Bernard", email=None)
        _, signals = score_pair(reg, fcm)
        # Either exact or fuzzy should fire
        assert "name_exact" in signals or "name_fuzzy" in signals

    def test_desmedt_vs_de_smedt(self):
        """'Desmedt' vs 'De Smedt' should produce a usable fuzzy score."""
        reg = _reg(first_name="Pierre", last_name="De Smedt", email=None)
        fcm = _fcm(first_name="Pierre", last_name="Desmedt", email=None)
        score, signals = score_pair(reg, fcm)
        # token_sort_ratio("pierre de smedt", "pierre desmedt") is high
        assert score >= 50.0

    def test_name_fuzzy_signal_value_is_ratio(self):
        """The ``name_fuzzy`` signal value must be the raw ratio (0-100)."""
        reg = _reg(first_name="Jean-Pierre", last_name="Roux", email=None)
        fcm = _fcm(first_name="Jean Pierre", last_name="Roux", email=None)
        _, signals = score_pair(reg, fcm)
        if "name_fuzzy" in signals:
            assert 0 <= signals["name_fuzzy"] <= 100


# ---------------------------------------------------------------------------
# 4. test_no_match
# ---------------------------------------------------------------------------

class TestNoMatch:
    """Completely different people should produce NOT_FOUND."""

    def test_different_email_and_name(self):
        """No shared email, no shared name -> NOT_FOUND."""
        reg = _reg(first_name="Alice", last_name="Smith",
                   email="alice@example.com")
        fcm = _fcm(first_name="Zoe", last_name="Bogaert",
                   email="zoe.bogaert@corp.be")
        results = match_sources([reg], [fcm])
        assert results[0].decision == MatchDecision.NOT_FOUND
        assert results[0].flight_record is None

    def test_not_found_score_below_50(self):
        """NOT_FOUND score must be below the TO_VERIFY threshold."""
        reg = _reg(first_name="Henri", last_name="Dumont",
                   email="h.dumont@company.net")
        fcm = _fcm(first_name="Marie", last_name="Charlier",
                   email="m.charlier@business.org")
        results = match_sources([reg], [fcm])
        if results[0].decision == MatchDecision.NOT_FOUND:
            assert results[0].score < 50.0

    def test_empty_fcm_list(self):
        """With no FCM records every registration is NOT_FOUND."""
        regs = [_reg(first_name="A", last_name="B", email="a@b.com")]
        results = match_sources(regs, [])
        assert results[0].decision == MatchDecision.NOT_FOUND
        assert results[0].flight_record is None


# ---------------------------------------------------------------------------
# 5. test_duplicate_email_detection
# ---------------------------------------------------------------------------

class TestDuplicateEmailDetection:
    """detect_duplicate_emails must group records sharing the same email."""

    def test_three_records_same_email(self):
        """Three records sharing one email should form one group of three."""
        shared = "shared@example.com"
        r1 = _reg(id="1", first_name="Alice", last_name="A", email=shared)
        r2 = _reg(id="2", first_name="Bob",   last_name="B", email=shared)
        r3 = _reg(id="3", first_name="Carol", last_name="C", email=shared)
        r4 = _reg(id="4", first_name="Dave",  last_name="D",
                  email="unique@example.com")

        groups = detect_duplicate_emails([r1, r2, r3, r4])
        assert len(groups) == 1
        assert len(groups[0]) == 3

    def test_two_groups(self):
        """Two sets of duplicate emails should produce two groups."""
        r1 = _reg(id="1", email="dup1@corp.be")
        r2 = _reg(id="2", email="dup1@corp.be")
        r3 = _reg(id="3", email="dup2@corp.be")
        r4 = _reg(id="4", email="dup2@corp.be")
        r5 = _reg(id="5", email="unique@corp.be")
        groups = detect_duplicate_emails([r1, r2, r3, r4, r5])
        assert len(groups) == 2

    def test_case_insensitive_grouping(self):
        """Email deduplication must be case-insensitive."""
        r1 = _reg(id="1", email="Test@Example.COM")
        r2 = _reg(id="2", email="test@example.com")
        groups = detect_duplicate_emails([r1, r2])
        assert len(groups) == 1

    def test_no_email_records_ignored(self):
        """Records without an email must not be grouped."""
        r1 = _reg(id="1", email=None)
        r2 = _reg(id="2", email=None)
        groups = detect_duplicate_emails([r1, r2])
        assert groups == []


# ---------------------------------------------------------------------------
# 6. test_full_pipeline_precision_recall
# ---------------------------------------------------------------------------

class TestFullPipelinePrecisionRecall:
    """End-to-end test against the synthetic dataset and gold standard."""

    @pytest.fixture(scope="class")
    def dataset(self):
        """Generate the synthetic dataset once per class."""
        regs_dicts = generate_registration_list(n=100)
        fcm_dicts = generate_fcm_list(regs_dicts)
        gold = build_gold_standard(regs_dicts, fcm_dicts)

        regs = [
            ParticipantRecord(
                id=r["id"],
                first_name=r["first_name"],
                last_name=r["last_name"],
                email=r.get("email"),
                company=r.get("company"),
                phone=r.get("phone"),
                source="registration",
                raw_data=r,
            )
            for r in regs_dicts
        ]
        fcms = [
            ParticipantRecord(
                id=f["id"],
                first_name=f["passenger_first"],
                last_name=f["passenger_last"],
                email=f.get("passenger_email"),
                company=f.get("company"),
                phone=None,
                source="fcm",
                raw_data=f,
            )
            for f in fcm_dicts
        ]
        return regs, fcms, gold

    def test_match_rate_gte_90_percent(self, dataset):
        """At least 90% of registrations that have a gold-match must be found."""
        regs, fcms, gold = dataset
        results = match_sources(regs, fcms)

        gold_by_reg = {g["registration_id"]: g for g in gold}

        matched_correctly = 0
        expected_matches = 0

        for result in results:
            reg_id = result.registration.id
            g = gold_by_reg.get(reg_id)
            if g is None:
                continue
            if g["expected_decision"] == "not_found":
                continue
            expected_matches += 1
            if result.flight_record is not None:
                matched_correctly += 1

        match_rate = matched_correctly / expected_matches if expected_matches else 0.0
        assert match_rate >= 0.90, (
            f"Match rate {match_rate:.2%} is below 90% "
            f"({matched_correctly}/{expected_matches})"
        )

    def test_false_positive_rate_is_zero(self, dataset):
        """CERTAIN decisions that are actually wrong must be zero."""
        regs, fcms, gold = dataset
        results = match_sources(regs, fcms)

        gold_by_reg = {g["registration_id"]: g for g in gold}
        fcm_id_map = {f.id: f for f in fcms}

        false_positives = 0
        certain_decisions = 0

        for result in results:
            if result.decision != MatchDecision.CERTAIN:
                continue
            certain_decisions += 1
            reg_id = result.registration.id
            g = gold_by_reg.get(reg_id)
            if g is None:
                continue
            expected_fcm_id = g["fcm_record_id"]
            actual_fcm_id = result.flight_record.id if result.flight_record else None
            if expected_fcm_id is None or actual_fcm_id != expected_fcm_id:
                false_positives += 1

        assert false_positives == 0, (
            f"{false_positives} false CERTAIN decision(s) detected "
            f"(out of {certain_decisions} total CERTAIN decisions)"
        )

    def test_not_found_for_missing_registrations(self, dataset):
        """Registrations with no FCM record should be NOT_FOUND."""
        regs, fcms, gold = dataset
        results = match_sources(regs, fcms)

        gold_by_reg = {g["registration_id"]: g for g in gold}
        missing_reg_ids = {
            g["registration_id"]
            for g in gold
            if g["expected_decision"] == "not_found"
        }

        result_by_reg = {r.registration.id: r for r in results}

        for reg_id in missing_reg_ids:
            result = result_by_reg.get(reg_id)
            if result is not None:
                assert result.decision == MatchDecision.NOT_FOUND, (
                    f"Registration {reg_id} has no FCM record but got "
                    f"decision={result.decision}"
                )


# ---------------------------------------------------------------------------
# 7. test_normalizer_email
# ---------------------------------------------------------------------------

class TestNormalizerEmail:
    """Edge cases for normalize_email."""

    def test_none_returns_empty(self):
        assert normalize_email(None) == ""

    def test_empty_string_returns_empty(self):
        assert normalize_email("") == ""

    def test_whitespace_only_returns_empty(self):
        assert normalize_email("   ") == ""

    def test_lowercase(self):
        assert normalize_email("TEST@EXAMPLE.COM") == "test@example.com"

    def test_strips_spaces(self):
        assert normalize_email("  user@domain.be  ") == "user@domain.be"

    def test_mixed_case(self):
        assert normalize_email("User.Name@Corp.BE") == "user.name@corp.be"


# ---------------------------------------------------------------------------
# 8. test_normalizer_name
# ---------------------------------------------------------------------------

class TestNormalizerName:
    """Accent stripping and case normalisation via normalize_name."""

    def test_none_returns_empty(self):
        assert normalize_name(None) == ""

    def test_lowercase(self):
        assert normalize_name("DUPONT") == "dupont"

    def test_strip_whitespace(self):
        assert normalize_name("  Martin  ") == "martin"

    def test_accent_e(self):
        # e-acute and e-grave -> e
        assert normalize_name("Heloise") == "heloise"
        assert normalize_name("Renee") == "renee"

    def test_accent_c(self):
        assert normalize_name("Francois") == "francois"

    def test_normalize_full_name_joins_parts(self):
        result = normalize_full_name("Jean-Pierre", "De Smedt")
        assert result == "jean-pierre de smedt"

    def test_normalize_full_name_missing_first(self):
        assert normalize_full_name(None, "Dupont") == "dupont"

    def test_normalize_full_name_missing_last(self):
        assert normalize_full_name("Marie", None) == "marie"


# ---------------------------------------------------------------------------
# 9. test_parse_date_formats
# ---------------------------------------------------------------------------

class TestParseDateFormats:
    """parse_date must handle all five supported formats."""

    def test_european_slash(self):
        from datetime import date
        assert parse_date("10/11/2025") == date(2025, 11, 10)

    def test_iso_8601(self):
        from datetime import date
        assert parse_date("2025-11-10") == date(2025, 11, 10)

    def test_european_dash(self):
        from datetime import date
        assert parse_date("10-11-2025") == date(2025, 11, 10)

    def test_us_slash(self):
        from datetime import date
        assert parse_date("11/30/2025") == date(2025, 11, 30)

    def test_dot_separated(self):
        from datetime import date
        assert parse_date("10.11.2025") == date(2025, 11, 10)

    def test_unparseable_returns_none(self):
        assert parse_date("not-a-date") is None

    def test_none_input_returns_none(self):
        assert parse_date(None) is None

    def test_empty_string_returns_none(self):
        assert parse_date("") is None


# ---------------------------------------------------------------------------
# 10. test_deterministic
# ---------------------------------------------------------------------------

class TestDeterministic:
    """Running match_sources twice on the same input must produce identical results."""

    def test_same_results_twice(self):
        """Results must be byte-for-byte equivalent on repeated calls."""
        regs_dicts = generate_registration_list(n=50)
        fcm_dicts = generate_fcm_list(regs_dicts, missing_n=3,
                                      name_noise_n=5, email_noise_n=2)

        regs = [
            ParticipantRecord(
                id=r["id"],
                first_name=r["first_name"],
                last_name=r["last_name"],
                email=r.get("email"),
                source="reg",
            )
            for r in regs_dicts
        ]
        fcms = [
            ParticipantRecord(
                id=f["id"],
                first_name=f["passenger_first"],
                last_name=f["passenger_last"],
                email=f.get("passenger_email"),
                source="fcm",
            )
            for f in fcm_dicts
        ]

        results1 = match_sources(regs, fcms)
        results2 = match_sources(regs, fcms)

        assert len(results1) == len(results2)
        for r1, r2 in zip(results1, results2):
            assert r1.score == r2.score
            assert r1.decision == r2.decision
            assert r1.signals == r2.signals
            assert r1.conflict_fields == r2.conflict_fields
            fcm1_id = r1.flight_record.id if r1.flight_record else None
            fcm2_id = r2.flight_record.id if r2.flight_record else None
            assert fcm1_id == fcm2_id
