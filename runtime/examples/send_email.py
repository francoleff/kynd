#!/usr/bin/env python3
"""Example: Send an email through Kynd governance.

This script demonstrates how a Hermes script uses Kynd to execute
tool calls with full governance: constitution → gate → broker → tool → audit.

Usage:
    python examples/send_email.py
"""

from kynd_runtime import Constitution, Executor, ToolRegistry, KyndExecutionError

# Load constitution
const = Constitution.load("examples/constitution.yaml")

# Register tool handlers
registry = ToolRegistry()


def send_email_handler(params):
    """Simulate sending an email."""
    # In production, this would call an email API (SendGrid, SES, etc.)
    target = params.get("target")
    subject = params.get("subject", "(no subject)")
    body = params.get("body", "")
    return f"Email sent to {target}: {subject}"


def charge_card_handler(params):
    """Simulate charging a card."""
    amount = params.get("amount")
    description = params.get("description", "No description")
    return f"Charged ${amount:.2f}: {description}"


registry.register("send_email", send_email_handler)
registry.register("charge_card", charge_card_handler)

# Create executor
executor = Executor(const, registry)

# --- Demo: valid email ---
print("=" * 60)
print("Demo 1: Valid email (should succeed)")
print("=" * 60)
try:
    result = executor.execute("send_email", {
        "target": "team@kynd.io",
        "subject": "Weekly update",
        "body": "Here's what happened this week...",
    })
    print(f"Result: {result}")
except KyndExecutionError as e:
    print(f"Blocked: {e}")

# --- Demo: email to blocked target ---
print()
print("=" * 60)
print("Demo 2: Email to blocked target (should fail)")
print("=" * 60)
try:
    result = executor.execute("send_email", {
        "target": "evil@hacker.com",
        "subject": "Phishing attempt",
        "body": "Click this link...",
    })
    print(f"Result: {result}")
except KyndExecutionError as e:
    print(f"Blocked: {e}")

# --- Demo: charge card with approval ---
print()
print("=" * 60)
print("Demo 3: Charge card with approval (should succeed)")
print("=" * 60)
try:
    result = executor.execute("charge_card", {
        "amount": 99.99,
        "description": "Monthly hosting",
        "approval_id": "APPROVAL-12345",
    })
    print(f"Result: {result}")
except KyndExecutionError as e:
    print(f"Blocked: {e}")

# --- Demo: charge card without approval ---
print()
print("=" * 60)
print("Demo 4: Charge card without approval (should fail)")
print("=" * 60)
try:
    result = executor.execute("charge_card", {
        "amount": 99.99,
        "description": "Monthly hosting",
    })
    print(f"Result: {result}")
except KyndExecutionError as e:
    print(f"Blocked: {e}")

# --- Demo: charge over amount ---
print()
print("=" * 60)
print("Demo 5: Charge over max amount (should fail)")
print("=" * 60)
try:
    result = executor.execute("charge_card", {
        "amount": 1000.00,
        "description": "Expensive thing",
        "approval_id": "APPROVAL-99999",
    })
    print(f"Result: {result}")
except KyndExecutionError as e:
    print(f"Blocked: {e}")

# --- Demo: blocked action type ---
print()
print("=" * 60)
print("Demo 6: Blocked action type (should fail)")
print("=" * 60)
try:
    result = executor.execute("delete", {
        "target": "important_database",
    })
    print(f"Result: {result}")
except KyndExecutionError as e:
    print(f"Blocked: {e}")

# --- Audit trail ---
print()
print("=" * 60)
print("Audit Trail")
print("=" * 60)
for entry in executor.audit_log:
    status = "ALLOWED" if entry.allowed else "DENIED"
    print(f"  {entry.capability}: {status} - {entry.reason}")
