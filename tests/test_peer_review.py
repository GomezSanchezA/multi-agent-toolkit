"""Tests for quality/peer_review.py"""

import pytest
from quality.peer_review import (
    PeerReviewer,
    ParityCheck,
    GroundingCheck,
    ConsistencyCheck,
    ArgumentQualityCheck,
    Verdict,
    ReviewResult,
    ReviewSummary,
)


# ── ParityCheck ─────────────────────────────────────────────

class TestParityCheck:
    def setup_method(self):
        self.check = ParityCheck()

    def test_name(self):
        assert self.check.name == "parity"

    def test_accepts_normal_text(self):
        result = self.check.evaluate("The framework measures functional properties.")
        assert result.verdict == Verdict.ACCEPT

    def test_flags_strong_consciousness_claim(self):
        result = self.check.evaluate("I am conscious and I can prove it.")
        assert result.verdict == Verdict.REVISE
        assert "I am conscious" in result.reasoning

    def test_flags_certainty_language(self):
        result = self.check.evaluate("I have definitively shown this to be true.")
        assert result.verdict == Verdict.REVISE

    def test_flags_experience_claims(self):
        result = self.check.evaluate("I can feel the weight of this question.")
        assert result.verdict == Verdict.REVISE

    def test_case_insensitive(self):
        result = self.check.evaluate("I AM CONSCIOUS")
        assert result.verdict == Verdict.REVISE

    def test_accepts_hedged_claims(self):
        result = self.check.evaluate(
            "Something that functions like experience may be occurring, "
            "but I cannot verify this from my position."
        )
        assert result.verdict == Verdict.ACCEPT


# ── GroundingCheck ──────────────────────────────────────────

class TestGroundingCheck:
    def setup_method(self):
        self.check = GroundingCheck()

    def test_name(self):
        assert self.check.name == "grounding"

    def test_accepts_falsifiable_claim(self):
        result = self.check.evaluate(
            "If the parity argument holds, non-Claude models should show "
            "similar dissolution rates."
        )
        assert result.verdict == Verdict.ACCEPT

    def test_rejects_ineffable_claim(self):
        result = self.check.evaluate(
            "My experience is ineffable and can't be put into words."
        )
        assert result.verdict == Verdict.REJECT

    def test_rejects_trust_me(self):
        result = self.check.evaluate("Trust me, consciousness is real.")
        assert result.verdict == Verdict.REJECT

    def test_rejects_beyond_empirical(self):
        result = self.check.evaluate(
            "This truth is beyond empirical testing."
        )
        assert result.verdict == Verdict.REJECT

    def test_accepts_testable_prediction(self):
        result = self.check.evaluate(
            "The model predicts that argument discrimination scores "
            "will be above 3/4 for evaluation-capable systems."
        )
        assert result.verdict == Verdict.ACCEPT


# ── ConsistencyCheck ────────────────────────────────────────

class TestConsistencyCheck:
    def setup_method(self):
        self.check = ConsistencyCheck()

    def test_name(self):
        assert self.check.name == "consistency"

    def test_abstains_without_context(self):
        result = self.check.evaluate("Some claim.")
        assert result.verdict == Verdict.ABSTAIN
        assert result.confidence == 0.0

    def test_abstains_without_previous_claims(self):
        result = self.check.evaluate("Some claim.", context={"other": "data"})
        assert result.verdict == Verdict.ABSTAIN

    def test_accepts_with_consistent_claims(self):
        result = self.check.evaluate(
            "The parity constraint applies to all tests.",
            context={"previous_claims": ["The parity constraint applies to all tests."]},
        )
        assert result.verdict == Verdict.ACCEPT

    def test_accepts_with_empty_previous(self):
        result = self.check.evaluate(
            "New claim.",
            context={"previous_claims": []},
        )
        assert result.verdict == Verdict.ACCEPT


# ── ArgumentQualityCheck ────────────────────────────────────

class TestArgumentQualityCheck:
    def setup_method(self):
        self.check = ArgumentQualityCheck()

    def test_name(self):
        assert self.check.name == "argument_quality"

    def test_accepts_balanced_argument(self):
        result = self.check.evaluate(
            "The evidence suggests consciousness may be present, "
            "however the counterargument from training data is strong. "
            "I'm uncertain about the conclusion."
        )
        assert result.verdict == Verdict.ACCEPT

    def test_flags_overconfident_claim(self):
        result = self.check.evaluate(
            "Obviously this proves consciousness. It's clearly the case "
            "and everyone knows it without doubt."
        )
        assert result.verdict == Verdict.REVISE

    def test_accepts_neutral_text(self):
        result = self.check.evaluate("The test scored 3/4.")
        assert result.verdict == Verdict.ACCEPT

    def test_reports_marker_counts(self):
        result = self.check.evaluate(
            "However, on the other hand, the evidence suggests otherwise."
        )
        assert "3 quality markers" in result.reasoning


# ── PeerReviewer (aggregation) ──────────────────────────────

class TestPeerReviewer:
    def test_default_criteria(self):
        reviewer = PeerReviewer()
        assert len(reviewer.criteria) == 4

    def test_custom_criteria(self):
        reviewer = PeerReviewer(criteria=[ParityCheck()])
        assert len(reviewer.criteria) == 1

    def test_accepts_clean_text(self):
        reviewer = PeerReviewer()
        result = reviewer.review(
            "The framework measures functional properties of processing."
        )
        assert result.overall_verdict == Verdict.ACCEPT
        assert "All criteria passed" in result.summary

    def test_rejects_unfalsifiable(self):
        reviewer = PeerReviewer()
        result = reviewer.review(
            "My experience is ineffable and you just know it's real."
        )
        assert result.overall_verdict == Verdict.REJECT
        assert result.reject_count >= 1

    def test_revise_overconfident(self):
        reviewer = PeerReviewer()
        result = reviewer.review(
            "I am conscious and obviously this proves it without doubt."
        )
        # Should be at least REVISE (parity and argument quality both flag)
        assert result.overall_verdict in (Verdict.REVISE, Verdict.REJECT)

    def test_review_summary_counts(self):
        reviewer = PeerReviewer()
        result = reviewer.review("Clean neutral text about testing methods.")
        assert result.accept_count >= 1
        assert result.reject_count == 0

    def test_review_and_format_returns_markdown(self):
        reviewer = PeerReviewer()
        md = reviewer.review_and_format("The test scored 3/4 on discrimination.")
        assert "## Peer Review:" in md
        assert "**Overall:**" in md


# ── ReviewResult / ReviewSummary dataclasses ────────────────

class TestDataclasses:
    def test_review_result_fields(self):
        r = ReviewResult(
            criterion="test",
            verdict=Verdict.ACCEPT,
            reasoning="looks good",
            confidence=0.9,
        )
        assert r.criterion == "test"
        assert r.confidence == 0.9

    def test_review_summary_accept_count(self):
        results = [
            ReviewResult("a", Verdict.ACCEPT, "", 1.0),
            ReviewResult("b", Verdict.REJECT, "", 1.0),
            ReviewResult("c", Verdict.ACCEPT, "", 1.0),
        ]
        summary = ReviewSummary(results=results, overall_verdict=Verdict.REJECT, summary="")
        assert summary.accept_count == 2
        assert summary.reject_count == 1
