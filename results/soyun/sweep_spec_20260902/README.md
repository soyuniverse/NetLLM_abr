# sweep_spec_20260902 — speculative parameter sweep (9 runs + 1 re-run)

Full write-up: [`docs/soyun/SWEEP_SPEC.md`](../../../docs/soyun/SWEEP_SPEC.md).

Asks whether the parameters soyun owns (draft horizon k, verification mode,
buffer/state tolerance) can lift the queue-serve share `q` from BASELINE6's
6.28 % to the 14.73 % that breaks even against A1 all-off. **They cannot.**

| run | knob | q | speedup | QoE |
|---|---|---:|---:|---:|
| `s0_mode_sample` | mode `sample` | 7.36 % | 0.926x | **0.95637** (A1 +0.81 %) |
| `s1_k1` | k=1 | **0.00 %** (structural) | 0.895x | 0.91741 |
| `s2_k2` | k=2 | 5.09 % | 0.929x | 0.93320 |
| `s3_k4` | k=4 | 7.98 % | 0.965x (latency outlier) | 0.91515 |
| `s4_k5` | k=5 | **9.96 %** (max) | 0.890x | 0.92684 |
| `s5/6/7_buftol` | btol 2 / 4 / 8 | 6.57 / 6.64 / 6.64 % | ~0.920x | 0.913 |
| `s8_statetol05` | stol 0.5 | 6.74 % | 0.920x | 0.91893 |

All 9 completed `status: ok`. `s2_k2_precheck/` is the original k=2 run, executed
on the pre-refactor code (`b6ebf8e`); `s2_k2/` is the approved re-run on the
post-refactor HEAD (`3964752`). Every behavioural metric between them is
identical to the last digit -- only latency moved (-0.58 %, a timing drift over
a 1 h 46 m gap).

Files: `analysis/{sweep_table.csv, sweep_rows.json, sweep_tables.md}`,
per-phase `selector_metrics.json` / `result.json` / `manifest_phase.json`.
`decisions.jsonl` and `logs/` are gitignored (local only).
