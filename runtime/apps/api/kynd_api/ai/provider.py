"""The AI proposal layer's provider boundary.

This module defines the shape an "AI" produces and one deterministic
implementation. There is no live model call here — no API key exists for
one, and fabricating a successful call would violate the mission's rule
against unverified success. What exists instead is a real, swappable
interface: a future phase wires a real LLM behind `AIProvider` without
touching anything downstream of it (kynd_api/services/ai_proposal_service.py
treats every provider's output as equally untrusted).

THE rule this module exists to enforce structurally, not by convention:

    A RawProposal has no `approval_id` field. It cannot carry one — there is
    no attribute to set. Downstream code cannot "forget" to strip a forged
    approval id from AI output, because there is nowhere for one to be.

Everything a provider returns is untrusted input. ai_proposal_service.py
re-validates every field regardless of which provider produced it.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProposalContext:
    """What the caller gives the AI to reason about.

    `intent` is free text (a Slack message, an operator's instruction) — the
    AI's job is to turn it into a structured action. `hints` are optional
    structured fields the caller already knows (e.g. capability name) that
    the provider may use directly rather than re-deriving. Nothing in here
    is trusted more than anything else; see module docstring.
    """

    intent: str
    hints: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RawProposal:
    """A candidate action, as an AI provider proposes it. Untrusted.

    Deliberately has NO `approval_id` field — see module docstring. Every
    other field is re-validated by ai_proposal_service.py before it can
    become anything the product acts on.
    """

    capability: str
    action_type: str | None
    target: str | None
    amount: float | None
    params: dict[str, Any]
    reason: str


class AIProvider(abc.ABC):
    """The swappable boundary. A future phase implements this against a
    real model provider; nothing else in the codebase changes."""

    @abc.abstractmethod
    def propose(self, context: ProposalContext) -> RawProposal:
        """Turn a context into one candidate action. May raise
        `AIProviderError` if it cannot produce a proposal at all."""


class AIProviderError(Exception):
    """The provider could not produce a proposal from this context."""


class StaticAIProvider(AIProvider):
    """The one concrete provider for Phase 10.

    No model call, no network access, fully deterministic — it takes the
    structured fields the caller already supplied in `hints` and returns
    them as a RawProposal, verbatim. This is intentionally NOT "real AI
    reasoning": it exists so the proposal pipeline (validation, governance
    preview, approval routing, audit) is exercised end-to-end today, with a
    provider that can be swapped for a real model later without changing
    anything downstream of `AIProvider.propose`.
    """

    def propose(self, context: ProposalContext) -> RawProposal:
        hints = context.hints
        capability = hints.get("capability")
        if not isinstance(capability, str) or not capability:
            raise AIProviderError("No capability could be derived from this context")

        amount = hints.get("amount")
        if amount is not None and not isinstance(amount, (int, float)):
            raise AIProviderError("amount must be numeric")

        return RawProposal(
            capability=capability,
            action_type=hints.get("action_type"),
            target=hints.get("target"),
            amount=float(amount) if amount is not None else None,
            params=hints.get("params") or {},
            reason=context.intent,
        )
