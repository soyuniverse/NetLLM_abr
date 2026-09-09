# serve_gate_20260909 — Task 1: serve-time buffer gate (batch 1, demote-to-LLM)

Full writeup: docs/soyun/DRAFTER_ABLATION.md §9. Change request:
docs/soyun/CHANGE_REQUEST_SERVE_TIME_GATE.md.

Freeze: phases 1-3 recorded a82b933, phases 4-8 d442728; execution path
byte-identical between them (the diff is NEEDS_UPSTREAM.md + a post-hoc analysis
script). GPU: RTX 3090 driver 570.172.08 (same instance as drafter_ab_20260908);
speedup vs drafter_ab_20260908/a1_all_off (80.627 ms) BUT see §9 -- cross-session
latency drift ~10 %, so speedup is confirmed same-session in batch 2.

`abr_spec/serve_gate.py --serve-buffer-floor N` refuses a queued speculative
action when the observed buffer < N s -> one LLM fallback call instead.

Finding: **drafter-dependent.** Hurts repeat-k3 / hybrid-k3 / repeat-k5
(rebuffering roughly doubles -- the LLM in a drained buffer destabilises the
trajectory); **helps hybrid-k5** (rebuffer 18.5 -> 7.0 s, QoE -2.0 % -> -1.3 %),
which is the one config whose unprotected <5 s queue serves were catastrophic
(1.46 s/chunk). Tighter buffer tolerance (t_repeat_k3_btol0.5) also fails.

Batch 2 (serve_gate v2: conservative / safe-mode, no LLM handoff) -> §9.6.
