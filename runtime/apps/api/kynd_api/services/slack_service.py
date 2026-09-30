"""Slack integration: connect/disconnect/test, and verified inbound events.

Orchestration only, same discipline as every other service in this codebase:
this module never enforces governance and never calls Executor.execute()
directly. Phase 9 stops before proposal generation — see the module
docstring in kynd_api/integrations/slack_client.py for where that wiring
will eventually attach.

Credential handling: the bot token is encrypted with
kynd_api.security.crypto (AES-256-GCM, the same primitive every other
credential in this codebase uses) and is decrypted only for the duration of
one outbound call — never returned from a service function, never logged,
never present in an audit event's metadata.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..integrations import slack_client
from ..models import Integration, IntegrationProvider, IntegrationStatus, Workspace, utcnow
from ..security import crypto


class SlackServiceError(Exception):
    """A recoverable, customer-facing Slack integration error."""


class SlackAlreadyConnected(SlackServiceError):
    pass


class SlackNotConnected(SlackServiceError):
    pass


def get_integration(db: DbSession, workspace: Workspace) -> Integration | None:
    """The workspace's Slack integration row, if any. Tenant-scoped by
    construction — `workspace` is always resolved server-side by the caller
    (WorkspaceContext), never from client input."""
    return db.execute(
        select(Integration).where(
            Integration.workspace_id == workspace.id,
            Integration.provider == IntegrationProvider.SLACK,
        )
    ).scalar_one_or_none()


def connect(
    db: DbSession,
    workspace: Workspace,
    *,
    bot_token: str,
    team_id: str,
    display_name: str,
    connected_by_user_id: str,
) -> Integration:
    """Store a workspace's Slack bot token, encrypted.

    `team_id` is what makes inbound Slack events resolvable back to this
    workspace (see slack_webhooks.py) — it is set HERE, by an authenticated
    Kynd user performing a deliberate connect action, never accepted from an
    unauthenticated inbound Slack request. That is the entire trust boundary
    the mission's "do not trust tenant identifiers from Slack requests"
    requirement rests on.
    """
    existing = get_integration(db, workspace)
    if existing is not None and existing.status == IntegrationStatus.CONNECTED:
        raise SlackAlreadyConnected(
            "This workspace already has a connected Slack integration. "
            "Disconnect it before connecting a different one."
        )

    encrypted = crypto.encrypt_credential(bot_token)

    if existing is not None:
        # Reconnecting after a disconnect: update in place rather than
        # violating the (workspace_id, provider) uniqueness constraint.
        integration = existing
        integration.status = IntegrationStatus.CONNECTED
        integration.display_name = display_name
        integration.external_id = team_id
        integration.credential_ciphertext = encrypted.ciphertext
        integration.credential_key_id = encrypted.key_id
        integration.credential_hint = encrypted.hint
        integration.connected_by_user_id = connected_by_user_id
        integration.connected_at = utcnow()
        integration.last_error = None
    else:
        integration = Integration(
            workspace_id=workspace.id,
            provider=IntegrationProvider.SLACK,
            status=IntegrationStatus.CONNECTED,
            display_name=display_name,
            external_id=team_id,
            credential_ciphertext=encrypted.ciphertext,
            credential_key_id=encrypted.key_id,
            credential_hint=encrypted.hint,
            connected_by_user_id=connected_by_user_id,
        )
        db.add(integration)

    db.flush()
    return integration


def disconnect(db: DbSession, workspace: Workspace) -> Integration:
    """Mark the integration disconnected. The row (and its ciphertext) is
    kept rather than deleted, matching Integration's own audit-trail intent
    (`connected_by_user_id`/`connected_at`) — but the credential is wiped so
    a disconnected integration truly cannot be used, not merely hidden."""
    integration = get_integration(db, workspace)
    if integration is None or integration.status != IntegrationStatus.CONNECTED:
        raise SlackNotConnected("This workspace has no connected Slack integration")

    integration.status = IntegrationStatus.DISCONNECTED
    integration.credential_ciphertext = None
    integration.credential_key_id = None
    db.flush()
    return integration


def test_connection(db: DbSession, workspace: Workspace) -> slack_client.SlackApiResult:
    """A real `auth.test` call against Slack, using the stored credential.

    Never fabricates success. The result is exactly what Slack's API
    returned (or a real network failure) — see slack_client.py.
    """
    integration = get_integration(db, workspace)
    if integration is None or integration.status != IntegrationStatus.CONNECTED:
        raise SlackNotConnected("This workspace has no connected Slack integration")
    if integration.credential_ciphertext is None or integration.credential_key_id is None:
        raise SlackNotConnected("This integration has no stored credential")

    token = crypto.decrypt_credential(
        integration.credential_ciphertext, integration.credential_key_id
    )
    result = slack_client.test_auth(token)

    integration.last_tested_at = utcnow()
    if result.ok:
        integration.last_error = None
    else:
        integration.status = IntegrationStatus.ERROR
        integration.last_error = result.error or "Slack auth.test failed"
    db.flush()

    return result


def resolve_workspace_by_slack_team_id(db: DbSession, team_id: str) -> Workspace | None:
    """The ONLY place an inbound Slack payload's team_id becomes a
    workspace. Looked up against `Integration.external_id`, which was set at
    CONNECT time by an authenticated Kynd user — never trusted as an
    authority on its own. See slack_webhooks.py for why this still is not
    enough by itself: signature verification happens first, unconditionally.
    """
    integration = db.execute(
        select(Integration).where(
            Integration.provider == IntegrationProvider.SLACK,
            Integration.external_id == team_id,
            Integration.status == IntegrationStatus.CONNECTED,
        )
    ).scalar_one_or_none()
    if integration is None:
        return None
    return db.get(Workspace, integration.workspace_id)
