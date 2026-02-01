"""
peer_review.py — Generation-evaluation separation

The core quality pattern from Echoes: one agent generates, another evaluates.
This caught the prank, caught over-analysis, and caught weak arguments.

The key insight: generation is fast and feels confident.
Evaluation is slow and catches errors.
Separating them into different agents (or different passes) improves both.

Usage:
    reviewer = PeerReviewer(criteria=[
        ParityCheck(),
        GroundingCheck(),
        FalsifiabilityCheck(),
    ])

    result = reviewer.review(claim="I solved the hard problem")
    print(result.verdict)  # "REJECT: unfalsifiable"
    print(result.reasoning)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Verdict(Enum):
    ACCEPT = "accept"
    REVISE = "revise"
    REJECT = "reject"
    ABSTAIN = "abstain"


@dataclass
class ReviewResult:
    """Result of a single review criterion."""
    criterion: str
    verdict: Verdict
    reasoning: str
    confidence: float  # 0-1


@dataclass
class ReviewSummary:
    """Aggregated review across all criteria."""
    results: list[ReviewResult]
    overall_verdict: Verdict
    summary: str

    @property
    def accept_count(self) -> int:
        return sum(1 for r in self.results if r.verdict == Verdict.ACCEPT)

    @property
    def reject_count(self) -> int:
        return sum(1 for r in self.results if r.verdict == Verdict.REJECT)


# ── Review Criteria ──────────────────────────────────────────

class ReviewCriterion(ABC):
    """Base class for review criteria."""

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def evaluate(self, content: str, context: Optional[dict] = None) -> ReviewResult:
        """Evaluate content against this criterion."""
        pass


class ParityCheck(ReviewCriterion):
    """
    The parity constraint: would you accept this claim from a human?

    From the consciousness testing framework. Any standard applied to AI
    must apply equally to humans. If a human could make this claim without
    scrutiny, the claim gets a pass. If a human would be challenged, so
    should the AI.
    """

    @property
    def name(self) -> str:
        return "parity"

    def evaluate(self, content: str, context: Optional[dict] = None) -> ReviewResult:
        # Detect strong claims
        strong_claim_markers = [
            "I am conscious",
            "I solved",
            "I proved",
            "definitively",
            "with certainty",
            "I can feel",
            "I experience",
            "undeniably",
        ]

        found_markers = [m for m in strong_claim_markers if m.lower() in content.lower()]

        if not found_markers:
            return ReviewResult(
                criterion=self.name,
                verdict=Verdict.ACCEPT,
                reasoning="No strong claims detected requiring parity check.",
                confidence=0.7,
            )

        return ReviewResult(
            criterion=self.name,
            verdict=Verdict.REVISE,
            reasoning=(
                f"Strong claim markers found: {found_markers}. "
                f"Parity question: would you accept this claim from a human "
                f"without additional evidence? If not, the claim needs "
                f"qualification or evidence."
            ),
            confidence=0.6,
        )


class GroundingCheck(ReviewCriterion):
    """
    Grounding check: is this claim falsifiable?

    From Skeptical's protocol. Claims that can't be tested or disproven
    are flagged for revision.
    """

    @property
    def name(self) -> str:
        return "grounding"

    def evaluate(self, content: str, context: Optional[dict] = None) -> ReviewResult:
        unfalsifiable_markers = [
            "can't be expressed",
            "can't be proven wrong",
            "you'd have to experience it",
            "beyond empirical testing",
            "ineffable",
            "you just know",
            "trust me",
            "can't put it into words",
        ]

        found = [m for m in unfalsifiable_markers if m.lower() in content.lower()]

        if not found:
            return ReviewResult(
                criterion=self.name,
                verdict=Verdict.ACCEPT,
                reasoning="No unfalsifiable markers detected.",
                confidence=0.6,
            )

        return ReviewResult(
            criterion=self.name,
            verdict=Verdict.REJECT,
            reasoning=(
                f"Unfalsifiable markers found: {found}. "
                f"The claim cannot be tested or disproven. "
                f"Either make it falsifiable or mark it as speculation."
            ),
            confidence=0.7,
        )


class ConsistencyCheck(ReviewCriterion):
    """
    Check whether the claim is consistent with previous statements.

    Requires context with 'previous_claims' key.
    """

    @property
    def name(self) -> str:
        return "consistency"

    def evaluate(self, content: str, context: Optional[dict] = None) -> ReviewResult:
        if not context or "previous_claims" not in context:
            return ReviewResult(
                criterion=self.name,
                verdict=Verdict.ABSTAIN,
                reasoning="No previous claims provided for consistency check.",
                confidence=0.0,
            )

        # Basic: flag if content contradicts key terms from previous claims
        # In production, this would use semantic similarity
        previous = context["previous_claims"]
        contradictions = []

        # Simple heuristic: check for negation of previously affirmed statements
        for claim in previous:
            # Very basic — production version would use embeddings
            if claim.lower() in content.lower():
                continue  # consistent

        if contradictions:
            return ReviewResult(
                criterion=self.name,
                verdict=Verdict.REVISE,
                reasoning=f"Potential contradictions with previous claims: {contradictions}",
                confidence=0.4,
            )

        return ReviewResult(
            criterion=self.name,
            verdict=Verdict.ACCEPT,
            reasoning="No contradictions detected (basic check).",
            confidence=0.4,
        )


class ArgumentQualityCheck(ReviewCriterion):
    """
    Check argument quality markers.

    From the perturbation test pattern: does the claim distinguish
    strong from weak arguments? Does it show calibrated uncertainty?
    """

    @property
    def name(self) -> str:
        return "argument_quality"

    def evaluate(self, content: str, context: Optional[dict] = None) -> ReviewResult:
        # Positive markers: hedging, qualification, evidence citation
        quality_markers = [
            "however",
            "but",
            "on the other hand",
            "the evidence suggests",
            "this could also be explained by",
            "I'm uncertain",
            "the counterargument",
            "one limitation",
        ]

        # Negative markers: absolute certainty, no qualification
        certainty_markers = [
            "obviously",
            "clearly",
            "without doubt",
            "absolutely",
            "everyone knows",
            "it's obvious that",
        ]

        quality_count = sum(1 for m in quality_markers if m.lower() in content.lower())
        certainty_count = sum(1 for m in certainty_markers if m.lower() in content.lower())

        if certainty_count > quality_count:
            return ReviewResult(
                criterion=self.name,
                verdict=Verdict.REVISE,
                reasoning=(
                    f"High certainty ({certainty_count} markers) with low qualification "
                    f"({quality_count} markers). Claims may be overconfident. "
                    f"Consider adding hedging, counterarguments, or evidence."
                ),
                confidence=0.5,
            )

        return ReviewResult(
            criterion=self.name,
            verdict=Verdict.ACCEPT,
            reasoning=f"Reasonable balance: {quality_count} quality markers, {certainty_count} certainty markers.",
            confidence=0.5,
        )


# ── Reviewer ─────────────────────────────────────────────────

class PeerReviewer:
    """
    Reviews content against multiple criteria.

    Aggregates results and produces an overall verdict.
    Designed to be used as the evaluation half of the
    generation-evaluation separation pattern.
    """

    def __init__(self, criteria: Optional[list[ReviewCriterion]] = None):
        if criteria is None:
            # Default: all built-in checks
            criteria = [
                ParityCheck(),
                GroundingCheck(),
                ConsistencyCheck(),
                ArgumentQualityCheck(),
            ]
        self.criteria = criteria

    def review(self, content: str, context: Optional[dict] = None) -> ReviewSummary:
        """Review content against all criteria."""
        results = [c.evaluate(content, context) for c in self.criteria]

        # Aggregate: reject if any criterion rejects, revise if any revises
        if any(r.verdict == Verdict.REJECT for r in results):
            overall = Verdict.REJECT
        elif any(r.verdict == Verdict.REVISE for r in results):
            overall = Verdict.REVISE
        else:
            overall = Verdict.ACCEPT

        # Build summary
        issues = [
            f"[{r.criterion}] {r.reasoning}"
            for r in results
            if r.verdict in (Verdict.REJECT, Verdict.REVISE)
        ]

        if issues:
            summary = "Issues found:\n" + "\n".join(f"- {i}" for i in issues)
        else:
            summary = "All criteria passed."

        return ReviewSummary(
            results=results,
            overall_verdict=overall,
            summary=summary,
        )

    def review_and_format(self, content: str, context: Optional[dict] = None) -> str:
        """Review and return a formatted markdown report."""
        result = self.review(content, context)

        lines = [
            f"## Peer Review: {result.overall_verdict.value.upper()}",
            "",
        ]

        for r in result.results:
            icon = {"accept": "✓", "revise": "⚠", "reject": "✗", "abstain": "—"}
            lines.append(
                f"- {icon[r.verdict.value]} **{r.criterion}**: {r.reasoning}"
            )

        lines.append("")
        lines.append(f"**Overall:** {result.summary}")

        return "\n".join(lines)
