## 표1 — 성능 (QoE 계열, A1 기준 델타)

| 구성 | QoE (raw mean) | mean_reward | bitrate (Mbps) | rebuffer (s/chunk) | rebuffer total (s) | smoothness (Mbps) | ΔQoE % | Δbitrate % | Δrebuffer % | Δsmoothness % |
|---|---|---|---|---|---|---|---|---|---|---|
| a1_all_off | 0.94872 | 0.94872 | 1.01655 | 0.00136 | 6.392 | 0.06199 | +0.00 | +0.00 | +0.00 | +0.00 |
| b_temporal | 0.88209 | 0.88209 | 0.98297 | 0.00814 | 38.260 | 0.06587 | -7.02 | -3.30 | +498.59 | +6.26 |
| c_recent_token | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| d_temporal_token | 0.89592 | 0.89592 | 1.02279 | 0.01073 | 50.437 | 0.08072 | -5.57 | +0.61 | +689.10 | +30.22 |
| e_speculative | 0.91904 | 0.91904 | 0.95973 | 0.00002 | 0.085 | 0.04062 | -3.13 | -5.59 | -98.66 | -34.48 |
| f_all_three | 0.91110 | 0.91110 | 0.95678 | 0.00047 | 2.202 | 0.04366 | -3.96 | -5.88 | -65.54 | -29.57 |
| a2_all_off | 0.94872 | 0.94872 | 1.01655 | 0.00136 | 6.392 | 0.06199 | +0.00 | +0.00 | +0.00 | +0.00 |

## 표2 — 효율 (latency / call / speculative counters)

| 구성 | speedup vs A1 (mean) | speedup p50 | speedup p95 | latency mean (ms) | latency p50 (ms) | latency p95 (ms) | inference_calls | target_plm_calls | llm_call_reduction_ratio | acceptance_rate | drafted | accepted | corrected | queued_actions_served | fallback total | fallback: buffer | fallback: state | fallback: return | draft_generation_failures |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a1_all_off | 1.000x | 1.000x | 1.000x | 50.329 | 57.954 | 59.032 | 4700 | 4700 | 0.00000 | 0.00000 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| b_temporal | 1.750x | 2.064x | 1.769x | 28.759 | 28.081 | 33.375 | 4700 | 4700 | 0.00000 | 0.00000 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| c_recent_token | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| d_temporal_token | 1.845x | 2.099x | 2.100x | 27.279 | 27.611 | 28.108 | 4700 | 4700 | 0.00000 | 0.00000 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| e_speculative | 0.918x | 0.861x | 0.862x | 54.815 | 67.297 | 68.445 | 4700 | 4405 | 0.06277 | 0.06142 | 12145 | 746 | 4054 | 295 | 268 | 236 | 32 | 0 | 0 |
| f_all_three | 1.649x | 1.713x | 1.726x | 30.527 | 33.823 | 34.196 | 4700 | 4408 | 0.06213 | 0.06247 | 12117 | 757 | 4041 | 292 | 284 | 258 | 26 | 0 | 0 |
| a2_all_off | 0.998x | 0.998x | 0.999x | 50.424 | 58.077 | 59.120 | 4700 | 4700 | 0.00000 | 0.00000 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

