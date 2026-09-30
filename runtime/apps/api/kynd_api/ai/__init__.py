"""The AI proposal layer.

provider.py defines the swappable AIProvider boundary. Orchestration
(structural validation, governance preview, routing to the Approval Center)
lives in kynd_api/services/ai_proposal_service.py — this package has no
knowledge of governance, tenancy, or the runtime; it only produces
candidate proposals from a context.
"""
