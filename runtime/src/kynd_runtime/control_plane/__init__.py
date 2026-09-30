"""Control Plane — the governance building blocks: constitution, gate, broker.

The single governed execution path is :class:`kynd_runtime.Executor`, which
wires these together correctly (gate → broker → approval consumption →
idempotency → tool → audit). This module exports the individual pieces for
callers who need direct access to one of them (e.g. constructing a
``GovernanceGate`` with a custom ``ApprovalStore`` implementation), but does
NOT offer its own execution facade — see D-3 in
docs/engineering/TECHNICAL_DEBT.md for why a prior facade here (``ControlPlane``)
was removed rather than fixed.
"""

from .constitution import Constitution, ConstitutionError
from .governance_gate import GovernanceGate, Action, GateResult
from .broker import Broker, BrokerResult, AuditEntry

__all__ = [
    "Constitution",
    "ConstitutionError",
    "GovernanceGate",
    "Action",
    "GateResult",
    "Broker",
    "BrokerResult",
    "AuditEntry",
]
