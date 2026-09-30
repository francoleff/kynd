# PERFORMANCE AUDIT — Kynd Runtime

Measured 2026-08-31 on macOS (Apple Silicon), CPython 3.11.15, via
`bench_tmp.py` (a temporary harness, not committed). Every number below is a
median of 5 runs of 5,000–20,000 iterations. **No figure here is an estimate.**

## Method

Benchmark the full pipeline — constitution lookup, gate, broker, tool dispatch,
audit — with a no-op handler, so the numbers reflect Kynd's own overhead and
nothing else. Real handlers do network I/O measured in milliseconds; Kynd's
overhead needs to be negligible against that.

## Results

### Pipeline throughput

| Configuration | Median |
|---|---|
| 6 capabilities, 4 rules (the shipped example's size) | **4.48 µs/op** |
| Denial path (unregistered capability) | 11.01 µs/op |

~223,000 governed calls/second on one core at the size real constitutions
actually are. Kynd's overhead is roughly **four thousand times smaller** than a
single HTTP round trip. There is no throughput problem.

The denial path is slower (11 µs) because it builds a violation message and
writes an audit entry. Denials are rare and their cost is irrelevant; more
importantly, denial is not *fast-pathed*, which is the right call — a
fail-closed system should never make refusing cheaper than checking.

### Scaling: capability lookup is O(n)

`Constitution.get_capability` linear-scans the capability list, and the
executor path calls it more than once per action.

| Capabilities | Median (worst-case lookup) |
|---|---|
| 10 | 5.11 µs |
| 100 | 10.40 µs |
| 1,000 | 64.93 µs |

Clean linear growth. **Not optimised, deliberately.** A realistic constitution
has 5–50 capabilities, where this costs under 10 µs. Converting to a dict index
would trade a measurable win of ~55 µs at a scale nobody operates at, in
exchange for a cache that must be invalidated if `_raw` is ever mutated — and
gate tests already mutate `_raw`. Optimising here would add an invalidation bug
surface to buy nothing. Revisit if a constitution ever exceeds ~200 capabilities.

### Scaling: hard rules are O(n) per action

| Hard rules | Median |
|---|---|
| 4 | 4.49 µs |
| 50 | 21.90 µs |
| 500 | 195.23 µs |

Also linear, also fine. Every rule must be evaluated on every action — that is
the semantic, not an inefficiency. A constitution with 500 hard rules is an
unreadable constitution long before it is a slow one.

### Memory under sustained load

```
50,000 executions with 100-byte payloads
heap growth: 5.11 MB
execution_log retained: 10,000 / 10,000 (bounded)
audit_log retained:     10,000 / 10,000 (bounded)
```

Growth stops at the log bound and stays flat. Before the F-12 fix this test
would have retained all 50,000 records plus every payload, growing without
limit. Verified by `TestF12BoundedLogs`.

### Startup

`import kynd_runtime` including interpreter start: **54.6 ms**. Almost entirely
interpreter boot plus PyYAML. Irrelevant for a long-lived process; worth knowing
for a per-invocation CLI pattern, which the R-1/R-2 constraints rule out anyway.

## Optimisations performed

**None.** The brief says measure first, then optimise actual bottlenecks. I
measured. There is no bottleneck. The honest recording:

```
BEFORE:      4.48 µs/op at realistic scale
AFTER:       4.48 µs/op (unchanged — no optimisation applied)
MEASUREMENT: median of 5 x 20,000 iterations, CPython 3.11.15
TRADEOFF:    none taken; optimising here would add invalidation risk for
             a win that no real workload can observe
```

The one performance-relevant change in this pass was a *correctness* fix that
also bounds memory (F-12), and a `threading.Lock` in the broker which costs
roughly 50 ns of the 4.48 µs — under 2%, for an invariant worth far more.

## Observation: denial logging volume

The benchmark ran ~100,000 denials and produced **12 MB of stderr**, one WARNING
per denial from `Executor`.

This is correct behaviour — a denied action is exactly the thing an operator
must see, and silencing it would be worse. But at high denial rates it is a
real disk-and-noise concern for anyone who has not configured log rotation.

Recorded as debt D-9. The fix is deployment-side (log level, rotation) and
possibly rate-limiting identical repeated denials, not removing the log.

## Not measured

- Python 3.10 / 3.12 — **UNVERIFIED**.
- Linux — all numbers are macOS/ARM. Expect the same shape, different constants.
- Webhook request throughput end-to-end — the server is `ThreadingHTTPServer`
  from the stdlib, which is adequate for n8n's traffic profile (a handful of
  calls per minute) and would not be for a public API. If that changes, the
  server, not the governance core, is what to replace.
