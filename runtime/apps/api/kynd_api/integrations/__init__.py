"""Integration adapters.

Phase 9 (Slack scaffold):
    slack_signature.py  — HMAC-SHA256 request verification (Slack's own
                           documented scheme)
    slack_client.py      — outbound Slack Web API calls, credential-agnostic

Orchestration for these lives in kynd_api/services/slack_service.py.
"""
