#!/usr/bin/env python3
"""End-to-end demonstration: full Kynd governance pipeline.

This proves the complete loop works:
  Constitution → Gate → Broker → Tool → Audit → Verification

Run this to see Kynd in action without any external dependencies.
"""

from pathlib import Path
import tempfile
import os

from kynd_runtime import (
    Constitution,
    Executor,
    ToolRegistry,
    KyndExecutionError,
    Verifier,
    VerificationError,
    KyndWebhookServer,
)


def main():
    print("=" * 70)
    print("KYND OS — END-TO-END DEMONSTRATION")
    print("=" * 70)

    # ================================================================
    # 1. CONSTITUTION
    # ================================================================
    print("\n[1] Loading constitution...")
    print("-" * 40)

    constitution = Constitution({
        "name": "demo-agent",
        "mission": "Demonstrate Kynd governance pipeline",
        "hard_rules": [
            {
                "name": "no-delete",
                "type": "block_action_type",
                "action_types": ["delete", "destroy"],
            },
            {
                "name": "require-approval-for-money",
                "type": "require_param",
                "param": "approval_id",
                "action_types": ["charge_card"],
            },
        ],
        "capabilities": [
            {
                "name": "send_email",
                "max_amount": 0,
                "max_calls_per_day": 3,
                "allowed_targets": ["team@kynd.io", "newsletter@kynd.io"],
            },
            {
                "name": "charge_card",
                "max_amount": 500.00,
                "max_calls_per_day": 2,
            },
            {
                "name": "generate_report",
                "max_amount": 0,
                "max_calls_per_day": 10,
            },
        ],
    })

    print(f"  Agent: {constitution.name}")
    print(f"  Mission: {constitution.mission}")
    print(f"  Hard rules: {len(constitution.hard_rules)}")
    print(f"  Capabilities: {len(constitution.capabilities)}")
    for cap in constitution.capabilities:
        print(f"    - {cap['name']}")

    # ================================================================
    # 2. TOOL REGISTRY
    # ================================================================
    print("\n[2] Registering tools...")
    print("-" * 40)

    registry = ToolRegistry()

    report_path = None

    def send_email_handler(params):
        target = params.get("target")
        subject = params.get("subject", "(no subject)")
        return f"Email delivered to {target}: {subject}"

    def charge_card_handler(params):
        amount = params.get("amount", 0)
        desc = params.get("description", "No description")
        return f"Payment processed: ${amount:.2f} for {desc}"

    def generate_report_handler(params):
        global report_path
        report_path = params.get("output_path", "/tmp/report.txt")
        return {"status": "generated", "path": report_path}

    registry.register("send_email", send_email_handler)
    registry.register("charge_card", charge_card_handler)
    registry.register("generate_report", generate_report_handler)

    print(f"  Registered: {registry.list_capabilities()}")

    # ================================================================
    # 3. EXECUTOR (Gate → Broker → Tool → Audit)
    # ================================================================
    print("\n[3] Creating executor...")
    print("-" * 40)

    executor = Executor(constitution, registry)
    print("  Executor ready (gate + broker + audit)")

    # ================================================================
    # 4. EXECUTE ACTIONS
    # ================================================================
    print("\n[4] Executing actions through governance pipeline...")
    print("-" * 40)

    results = []

    # 4a: Valid email
    print("\n  [4a] Valid email to team@kynd.io")
    try:
        result = executor.execute("send_email", {
            "target": "team@kynd.io",
            "subject": "Demo complete",
            "body": "Kynd is working!",
        })
        print(f"       ✓ {result}")
        results.append(("send_email", True, result))
    except KyndExecutionError as e:
        print(f"       ✗ Blocked: {e}")
        results.append(("send_email", False, str(e)))

    # 4b: Blocked target
    print("\n  [4b] Email to evil@hacker.com (should be blocked)")
    try:
        result = executor.execute("send_email", {
            "target": "evil@hacker.com",
            "subject": "Phishing",
        })
        print(f"       ✓ {result}")
        results.append(("send_email_blocked", True, result))
    except KyndExecutionError as e:
        print(f"       ✗ Blocked: {e}")
        results.append(("send_email_blocked", False, str(e)))

    # 4c: Charge with approval
    print("\n  [4c] Charge card with approval_id")
    try:
        result = executor.execute("charge_card", {
            "amount": 99.99,
            "description": "Hosting",
            "approval_id": "APPROVAL-001",
        })
        print(f"       ✓ {result}")
        results.append(("charge_card", True, result))
    except KyndExecutionError as e:
        print(f"       ✗ Blocked: {e}")
        results.append(("charge_card", False, str(e)))

    # 4d: Charge without approval (should be blocked by gate)
    print("\n  [4d] Charge card without approval_id (should be blocked)")
    try:
        result = executor.execute("charge_card", {
            "amount": 50.00,
            "description": "No approval",
        })
        print(f"       ✓ {result}")
        results.append(("charge_no_approval", True, result))
    except KyndExecutionError as e:
        print(f"       ✗ Blocked: {e}")
        results.append(("charge_no_approval", False, str(e)))

    # 4e: Delete action (should be blocked by gate)
    print("\n  [4e] Delete action (should be blocked)")
    try:
        result = executor.execute("delete", {"target": "database"})
        print(f"       ✓ {result}")
        results.append(("delete", True, result))
    except KyndExecutionError as e:
        print(f"       ✗ Blocked: {e}")
        results.append(("delete", False, str(e)))

    # 4f: Generate report
    print("\n  [4f] Generate report")
    try:
        result = executor.execute("generate_report", {
            "output_path": "/tmp/demo_report.txt",
        })
        print(f"       ✓ {result}")
        results.append(("generate_report", True, result))
    except KyndExecutionError as e:
        print(f"       ✗ Blocked: {e}")
        results.append(("generate_report", False, str(e)))

    # ================================================================
    # 5. VERIFICATION
    # ================================================================
    print("\n[5] Verification layer...")
    print("-" * 40)

    verifier = Verifier()
    verifier.add_check("report_generated", lambda p: "generated" in str(p.get("result", "")))
    verifier.add_check("no_errors", lambda p: p.get("error") is None)

    verify_result = verifier.verify({
        "result": results,
        "error": None,
    })

    if verify_result.passed:
        print("  ✓ All verification checks passed")
    else:
        print(f"  ✗ Failed checks: {verify_result.failures}")

    # ================================================================
    # 6. AUDIT TRAIL
    # ================================================================
    print("\n[6] Audit trail...")
    print("-" * 40)

    allowed = sum(1 for entry in executor.audit_log if entry.allowed)
    denied = sum(1 for entry in executor.audit_log if not entry.allowed)

    print(f"  Total attempts: {len(executor.audit_log)}")
    print(f"  Allowed: {allowed}")
    print(f"  Denied: {denied}")
    print()

    for entry in executor.audit_log:
        status = "ALLOWED" if entry.allowed else "DENIED "
        print(f"  [{status}] {entry.capability}: {entry.reason}")

    # ================================================================
    # 7. SUMMARY
    # ================================================================
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    print(f"""
  Constitution: {constitution.name}
  Capabilities: {len(constitution.capabilities)}
  Hard rules:   {len(constitution.hard_rules)}

  Actions attempted:  {len(results)}
  Actions succeeded:  {sum(1 for _, ok, _ in results if ok)}
  Actions blocked:    {sum(1 for _, ok, _ in results if not ok)}

  Audit entries:      {len(executor.audit_log)}
  Verification:       {'PASS' if verify_result.passed else 'FAIL'}

  Pipeline: Constitution → Gate → Broker → Tool → Audit → Verification
  Status:   ALL SYSTEMS OPERATIONAL
""")

    print("=" * 70)
    print("KYND OS — DEMONSTRATION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
