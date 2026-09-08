# drafter_ab_20260908 — drafter replacement ablation

Full writeup: `docs/soyun/DRAFTER_ABLATION.md`. Cost-model update: `docs/soyun/SWEEP_SPEC.md` §12.

Freeze commit `0d137ce`. GPU: RTX 3090 driver 570.172.08 (new instance; speedup is
vs this run's own `a1_all_off`, latency mean 80.627 ms — NOT BASELINE6's A1).

Phases: `a1_all_off` (speedup ref) · `d_temporal_token` (selector-only ref) ·
`m1a_mpc_k3_sample` (= SWEEP_SPEC s0, regression gate) · `m1b_mpc_k3_greedy`
(BASELINE6 E continuity) · `m2_repeat_k3` · `m3_hybrid_k3` · `m4_repeat_k5` ·
`m5_hybrid_k5` · `m6_best_plus_selectors` (repeat-last k3 + D selectors).

Headline: repeat-last k3 → speedup 1.419× (q 37.8 %), the first speculative
config to clear 1.0× and 1.24×; conditional on a significant rebuffering rise
(§S). M6 → 2.102×.

`analysis/` = tracked derived tables; `*/decisions.jsonl` gitignored, distilled
into `results/soyun/derived/drafter_ab_20260908_summary.json`.
