### v_hybrid_k5_f5_fb_s4 — per-decision post-hoc analysis

`results/soyun/serve_gate_20260909/v_hybrid_k5_f5_fb_s4/decisions.jsonl` — 4700 decisions over 100 traces; 1797 draft+verify steps, 2772 steps where the LLM actually produced an action.

| 지표 | 정의 | 값 | 분모 |
|---|---|---|---|
| 1. MPC draft 1-step 일치율 | `mpc_draft_actions[0] == llm_target_action` | 81.64 % | 1797 |
| 2. 직전 행동 반복 drafter (가상) | `last_action == llm_action` | 87.70 % | 2772 |
| 2b. 동일 기준(verify step만) | `last_action == llm_target_action` | 87.59 % | 1797 |
| 3. LLM 행동 자기상관 (인접 t) | `llm_action(t) == llm_action(t-1)` | 86.83 % | 1913 |
| 3b. LLM 호출 순서 기준 | 직전 LLM 호출의 행동과 비교 | 82.82 % | 2672 |

**Draft 위치별 일치율 (k=5)**

| draft position | n | MPC 일치율 | repeat-last 일치율 |
|---|---|---|---|
| 0 | 1797 | 81.64 % | 87.59 % |
| 1 | 1750 | 78.63 % | 81.66 % |
| 2 | 1712 | 76.99 % | 78.21 % |
| 3 | 1670 | 75.33 % | 77.37 % |
| 4 | 1623 | 69.87 % | 74.12 % |

accepted-prefix 길이 평균 — MPC **3.091** / repeat-last **3.291** (최대 5). MPC prefix 분포 {'0': 330, '1': 230, '2': 154, '3': 138, '4': 123, '5': 822}, repeat-last {'0': 223, '1': 261, '2': 180, '3': 128, '4': 116, '5': 889}.

**buffer 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| <5s | 102 | 100 | 44.00 % | 100.00 % | 100.00 % |
| 5-10s | 228 | 99 | 96.97 % | 95.96 % | 95.45 % |
| 10-20s | 680 | 201 | 82.59 % | 84.08 % | 84.54 % |
| >=20s | 3690 | 1397 | 83.11 % | 86.61 % | 86.64 % |

**throughput 안정성(최근 6 관측 CV) 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| stable cv<0.10 | 3330 | 1048 | 87.31 % | 87.31 % | 86.64 % |
| moderate 0.10-0.30 | 980 | 466 | 89.48 % | 89.48 % | 90.07 % |
| volatile cv>=0.30 | 290 | 183 | 49.73 % | 77.60 % | 78.31 % |
| unknown | 100 | 100 | 44.00 % | 100.00 % | n/a |

**Latency 귀속 (per-decision)**

| stage | n | 비중 | latency mean ms | MPC rollout CPU ms | verify logits ms | selected tokens mean |
|---|---|---|---|---|---|---|
| draft_verify | 1797 | 38.23 % | 102.890 | 0.690 | 1.645 | 162.066 |
| fallback | 975 | 20.74 % | 86.141 | n/a | n/a | 148.243 |
| queue_serve | 1928 | 41.02 % | 1.851 | n/a | n/a | 0.000 |

전체 decision latency 합 272451 ms 중 MPC brute-force rollout CPU 시간은 1240 ms (**0.46 %**), throughput predictor까지 포함해도 0.62 %.

