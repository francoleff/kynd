"""Hermes skill for Kynd governance wrapper.

This skill provides the `kynd` command pattern for Hermes scripts.
It wraps any tool call with Kynd's governance pipeline:
constitution → gate → broker → tool → audit.

Usage in a Hermes script:
    from kynd_runtime import Constitution, Executor, ToolRegistry
    
    # Load constitution
    const = Constitution.load("constitution.yaml")
    
    # Register tools
    registry = ToolRegistry()
    registry.register("send_email", send_email_handler)
    registry.register("charge_card", charge_card_handler)
    
    # Create executor
    executor = Executor(const, registry)
    
    # Use it
    result = executor.execute("send_email", {"target": "user@example.com"})
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# Skill metadata for Hermes
SKILL_NAME = "kynd-runtime"
SKILL_VERSION = "0.1.0"
SKILL_DESCRIPTION = "Kynd governance wrapper — constitution → gate → broker → tool → audit"


def get_skill_info() -> dict[str, Any]:
    """Return skill metadata."""
    return {
        "name": SKILL_NAME,
        "version": SKILL_VERSION,
        "description": SKILL_DESCRIPTION,
        "constitution_template": {
            "name": "my-agent",
            "mission": "What this agent does",
            "hard_rules": [
                {
                    "name": "no-delete",
                    "type": "block_action_type",
                    "action_types": ["delete", "destroy"],
                },
                {
                    "name": "require-approval",
                    "type": "require_param",
                    "param": "approval_id",
                    "action_types": ["charge_card", "send_email"],
                },
            ],
            "capabilities": [
                {
                    "name": "send_email",
                    "max_amount": 0,
                    "max_calls_per_day": 100,
                    "allowed_targets": ["team@kynd.io", "newsletter@kynd.io"],
                },
                {
                    "name": "charge_card",
                    "max_amount": 500.0,
                    "max_calls_per_day": 10,
                },
            ],
        },
    }
