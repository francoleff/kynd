# PILOT KILL SWITCH — Kynd Runtime

Two independent mechanisms, both tested for real (not merely inspected) as
part of pilot prep. Neither depends on the AI's cooperation — both operate
entirely outside anything the model can influence.

## Mechanism 1: Process termination (fastest, works even if the constitution can't be edited)

```bash
kill -TERM <pilot_process_pid>
# or, if run in a foreground terminal:
Ctrl-C
```

**Verified:** started a real Kynd-governed process, sent `SIGTERM`, process
exited cleanly (exit code -15, meaning terminated by SIGTERM) within
milliseconds. No side effect can occur after the process is gone — the only
place a real send happens is inside `Executor.execute()`, running in that
process.

**Caveat:** if a send was already past the governance checks and mid-flight
inside the handler when SIGTERM arrives, Python does not guarantee the
handler finishes or aborts cleanly — ordinary process-kill semantics, not a
Kynd-specific behavior. For a fire-and-forget SMTP call this is low risk; it
is the same risk as killing any running program mid-network-call.

## Mechanism 2: Zero the daily cap in the constitution (surgical, keeps the process running)

Edit the pilot constitution file:

```yaml
capabilities:
  - name: send_notification
    max_calls_per_day: 0        # was 5
```

**Requires a process restart to take effect** — the constitution is loaded
once at `Executor` construction (`Constitution.load(path)`), not re-read
per call. This is a real, documented limitation, not glossed over: this
mechanism is NOT instantaneous against an already-running process. Use
Mechanism 1 if the pilot process cannot be quickly restarted.

**Verified, for real, in this session:**
```
=== 2. KILL SWITCH: set max_calls_per_day: 0 and reload ===
  PASS: send correctly blocked after kill switch: Capability
  'send_notification' exceeded max calls per day (0)
  real sends after kill switch: 1 (must still be 1)

=== 3. Verify: even with a VALID pending approval, cap=0 still blocks ===
  PASS: kill switch holds even with a valid approval present:
  Capability 'send_notification' exceeded max calls per day (0)
```

A cap of 0 blocks every attempt at the broker stage, even one carrying a
genuinely valid, unexpired, unconsumed approval — the cap check and the
approval check are independent gates, and both must pass.

## Recommended operator procedure during the pilot

1. **Immediate stop needed right now:** `kill -TERM <pid>` (Mechanism 1).
2. **Stop new sends but let the process keep running/logging:** edit the
   constitution to `max_calls_per_day: 0`, then restart the process
   (Mechanism 2). Slower, but does not require finding/killing a PID and
   keeps the audit trail actively being written.
3. **Revoke one specific outstanding approval** (narrower than a full stop
   — use if only one particular pending approval is suspect):
   ```python
   store.revoke_approval(approval_id)
   ```
   Verified in the D-1 adversarial test suite (`tests/test_persistence_d1.py
   ::TestApprovalVerification::test_revoked_approval_fails`) — a revoked
   approval is rejected even if it was otherwise valid and unexpired.

None of these three mechanisms requires editing Kynd's own source code,
requires the AI's awareness or cooperation, or has any code path by which a
proposed action could bypass them.
