"""Domain-critical type distinctions.

``NewType`` wrappers cost nothing at runtime — they are the identity function
when called (``ActionType("delete")`` returns the plain string ``"delete"``)
— but they make it a *static type error* to pass one domain concept where a
different one is expected. They exist here specifically to make the defect
documented as **F-1** in ``docs/engineering/ARCHITECTURE_AUDIT.md`` harder to
reintroduce:

    A hard rule of type ``block_action_type`` blocking the verb ``"delete"``
    silently failed to stop a capability named ``delete_all_customers``,
    because ``Executor.execute`` fed the CAPABILITY NAME into both the
    ``action.type`` and ``action.capability`` fields of the proposed
    ``Action`` — the two concepts were structurally identical (both ``str``)
    and easy to swap without either the type checker or a casual reader
    noticing.

With ``Action.type: ActionType`` and ``Action.capability: CapabilityName``,
writing ``Action(type=some_capability_name, capability=some_action_type)`` —
i.e. accidentally swapping the two arguments — is now a real mypy error at
every call site inside ``src/``, not just a naming convention a future
change can violate silently.

Scope, deliberately narrow (see D-6 mission: "do not type everything
blindly"):

- These types are used at the internal construction boundary where an
  ``Action`` is actually built (``Executor.execute``) and in the
  ``GovernanceGate`` / ``Broker`` interfaces that consume it.
- They are **not** forced onto the public API (``Executor.execute(capability:
  str, ...)`` still accepts a plain ``str``). Changing that signature would
  be a breaking change for every existing caller and test, for zero
  additional safety — an external caller passing a string literal doesn't
  become safer because the parameter is annotated ``CapabilityName`` instead
  of ``str``; the protection is entirely at internal call sites where a
  developer could otherwise transpose two same-shaped variables.
- ``ApprovalId`` is reserved for the *trusted, freshly-issued* side of the
  approval boundary (``SqliteStore.issue_approval``'s return value). A
  caller-supplied ``approval_id`` string arriving back from a model or a
  webhook is deliberately **kept as plain ``str``** through
  ``GovernanceGate``/``SqliteStore.validate_approval``/``consume_approval`` —
  wrapping it in ``ApprovalId`` at that point would misleadingly imply it is
  already verified, which is exactly the false confidence D-2 exists to
  prevent. See ``docs/engineering/D1_IMPLEMENTATION.md``.
"""

from __future__ import annotations

from typing import Literal, NewType

CapabilityName = NewType("CapabilityName", str)
"""A registered capability's handler identity, e.g. ``"charge_card"``,
``"delete_all_customers"``. Must match a ``ToolRegistry`` key and a
``capabilities[].name`` entry in the constitution.

Semantically distinct from :data:`ActionType` even though the gate's verb-
matching heuristic (``governance_gate._match_capability_to_action_types``)
deliberately looks for an ActionType's words *inside* a CapabilityName —
that heuristic reads a CapabilityName as data, it does not conflate the two
concepts.
"""

ActionType = NewType("ActionType", str)
"""The semantic KIND of action being proposed, e.g. ``"delete"``, ``"charge"``,
``"send"``. Hard rules of type ``block_action_type`` match against this, not
against :data:`CapabilityName`. This is the field that was silently fed a
capability name instead of an action type in the pre-D-1 defect (F-1)."""

ApprovalId = NewType("ApprovalId", str)
"""An unguessable token identifying one issued approval — the return value of
``SqliteStore.issue_approval``. Reserved for the trusted/freshly-issued side
of the boundary; see module docstring for why caller-supplied approval
strings are deliberately NOT wrapped in this type."""

IdempotencyKey = NewType("IdempotencyKey", str)
"""A caller-supplied key identifying one logical operation for dedupe
purposes, once validated to be a non-empty ``str`` at the ``Executor``
boundary. Distinct from :data:`ApprovalId` and :data:`CapabilityName` so a
future change cannot accidentally pass one where another belongs."""

ExecutionStatus = Literal["allowed", "denied", "failed"]
"""The three possible outcomes of an ``Executor.execute`` attempt, recorded
in ``ExecutionRecord.status``. A ``Literal`` rather than a bare ``str`` so a
typo like ``"alowed"`` is a static type error instead of a silent audit-log
corruption that would only be caught (if ever) by reading logs by hand."""

IdempotencyClaimStatus = Literal["new", "completed", "in_progress", "conflict", "pending", "failed"]
"""The possible ``status`` values a ``SqliteStore`` idempotency row can hold.
``new``/``completed``/``in_progress``/``conflict`` are the values
``IdemClaim.status`` (the claim *result*) can take; ``pending``/``completed``/
``failed`` are the values the durable row's own ``status`` column takes.
Both are included here so a caller checking either surface gets the same
static protection against a misspelled state name."""
