### v_hybrid_k5_f5_cons_s4 — per-decision post-hoc analysis

`results/soyun/serve_gate_20260909/v_hybrid_k5_f5_cons_s4/decisions.jsonl` — 4700 decisions over 100 traces; 1797 draft+verify steps, 2771 steps where the LLM actually produced an action.

| 지표 | 정의 | 값 | 분모 |
|---|---|---|---|
| 1. MPC draft 1-step 일치율 | `mpc_draft_actions[0] == llm_target_action` | 81.69 % | 1797 |
| 2. 직전 행동 반복 drafter (가상) | `last_action == llm_action` | 87.73 % | 2771 |
| 2b. 동일 기준(verify step만) | `last_action == llm_target_action` | 87.65 % | 1797 |
| 3. LLM 행동 자기상관 (인접 t) | `llm_action(t) == llm_action(t-1)` | 86.81 % | 1911 |
| 3b. LLM 호출 순서 기준 | 직전 LLM 호출의 행동과 비교 | 82.82 % | 2671 |

**Draft 위치별 일치율 (k=5)**

| draft position | n | MPC 일치율 | repeat-last 일치율 |
|---|---|---|---|
| 0 | 1797 | 81.69 % | 87.65 % |
| 1 | 1750 | 78.63 % | 81.66 % |
| 2 | 1712 | 77.04 % | 78.27 % |
| 3 | 1671 | 75.40 % | 77.44 % |
| 4 | 1623 | 69.87 % | 74.12 % |

accepted-prefix 길이 평균 — MPC **3.090** / repeat-last **3.290** (최대 5). MPC prefix 분포 {'0': 329, '1': 232, '2': 154, '3': 137, '4': 124, '5': 821}, repeat-last {'0': 222, '1': 263, '2': 180, '3': 127, '4': 117, '5': 888}.

**buffer 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| <5s | 102 | 100 | 44.00 % | 100.00 % | n/a |
| 5-10s | 232 | 101 | 97.03 % | 96.04 % | 95.45 % |
| 10-20s | 678 | 199 | 82.91 % | 84.42 % | 84.47 % |
| >=20s | 3688 | 1397 | 83.11 % | 86.61 % | 86.64 % |

**throughput 안정성(최근 6 관측 CV) 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| stable cv<0.10 | 3330 | 1048 | 87.40 % | 87.40 % | 86.64 % |
| moderate 0.10-0.30 | 980 | 466 | 89.48 % | 89.48 % | 90.04 % |
| volatile cv>=0.30 | 290 | 183 | 49.73 % | 77.60 % | 78.31 % |
| unknown | 100 | 100 | 44.00 % | 100.00 % | n/a |

**Latency 귀속 (per-decision)**

| stage | n | 비중 | latency mean ms | MPC rollout CPU ms | verify logits ms | selected tokens mean |
|---|---|---|---|---|---|---|
| draft_verify | 1797 | 38.23 % | 90.478 | 0.684 | 1.720 | 162.070 |
| fallback | 975 | 20.74 % | 75.217 | n/a | n/a | 148.269 |
| queue_serve | 1928 | 41.02 % | 1.887 | n/a | n/a | 0.000 |

전체 decision latency 합 239564 ms 중 MPC brute-force rollout CPU 시간은 1230 ms (**0.51 %**), throughput predictor까지 포함해도 0.71 %.

