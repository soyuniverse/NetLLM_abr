# baseline6_20260902 — README 6-condition matrix at `--trace-num 100`

Full write-up: [`docs/soyun/BASELINE6.md`](../../../docs/soyun/BASELINE6.md).

7 phases on one RTX 3090 (driver 595.58.03), official r=128 ABR LoRA, seed 1,
fcc-test / 100 traces / video1 / fixed-order / fp16. `a1_all_off` runs first and
`a2_all_off` last so their gap gives the latency measurement-noise floor
(**+0.19 %**; the QoE metrics are bit-identical between the two).

| phase | result |
|---|---|
| `a1_all_off` | ok — 50.329 ms mean latency, QoE 0.94872 (baseline for every delta/speedup) |
| `b_temporal` | ok — **1.750×**, QoE −7.02 % |
| `c_recent_token` | **error** — `NonFiniteInferenceError` at PLM call 2527/4700, see `docs/soyun/NEEDS_UPSTREAM.md` #4 |
| `d_temporal_token` | ok — **1.845×**, QoE −5.57 % |
| `e_speculative` | ok — **0.918×**, QoE −3.13 %, acceptance 6.14 %, per-decision trace |
| `f_all_three` | ok — **1.649×**, QoE −3.96 %, per-decision trace |
| `a2_all_off` | ok — 50.424 ms (+0.19 % vs a1) |
| `c_recent_token_nanprobe` | diagnostic re-run of the failure, `nan_probe.json` |

Files: `table1_performance.csv`, `table2_efficiency.csv`, `qoe_decomposition.csv`,
`tables.md`, `summary_all.json`, `analysis/` (post-hoc on the E and F decision
traces). `decisions.jsonl` and `logs/` are gitignored (local only).
