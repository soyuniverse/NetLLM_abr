### m5_ctrl_s4 — per-decision post-hoc analysis

`results/soyun/serve_gate_20260909/m5_ctrl_s4/decisions.jsonl` — 4700 decisions over 100 traces; 1797 draft+verify steps, 2766 steps where the LLM actually produced an action.

| 지표 | 정의 | 값 | 분모 |
|---|---|---|---|
| 1. MPC draft 1-step 일치율 | `mpc_draft_actions[0] == llm_target_action` | 81.30 % | 1797 |
| 2. 직전 행동 반복 drafter (가상) | `last_action == llm_action` | 87.42 % | 2766 |
| 2b. 동일 기준(verify step만) | `last_action == llm_target_action` | 87.26 % | 1797 |
| 3. LLM 행동 자기상관 (인접 t) | `llm_action(t) == llm_action(t-1)` | 86.50 % | 1904 |
| 3b. LLM 호출 순서 기준 | 직전 LLM 호출의 행동과 비교 | 82.48 % | 2666 |

**Draft 위치별 일치율 (k=5)**

| draft position | n | MPC 일치율 | repeat-last 일치율 |
|---|---|---|---|
| 0 | 1797 | 81.30 % | 87.26 % |
| 1 | 1751 | 78.24 % | 81.27 % |
| 2 | 1712 | 76.52 % | 77.75 % |
| 3 | 1674 | 75.03 % | 77.06 % |
| 4 | 1624 | 69.58 % | 73.83 % |

accepted-prefix 길이 평균 — MPC **3.058** / repeat-last **3.259** (최대 5). MPC prefix 분포 {'0': 336, '1': 233, '2': 159, '3': 139, '4': 122, '5': 808}, repeat-last {'0': 229, '1': 264, '2': 185, '3': 129, '4': 115, '5': 875}.

**buffer 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| <5s | 102 | 100 | 44.00 % | 100.00 % | n/a |
| 5-10s | 226 | 96 | 97.92 % | 96.88 % | 96.39 % |
| 10-20s | 698 | 208 | 82.69 % | 84.13 % | 84.04 % |
| >=20s | 3674 | 1393 | 82.63 % | 86.15 % | 86.32 % |

**throughput 안정성(최근 6 관측 CV) 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| stable cv<0.10 | 3331 | 1052 | 87.17 % | 87.17 % | 86.82 % |
| moderate 0.10-0.30 | 979 | 462 | 88.53 % | 88.53 % | 89.10 % |
| volatile cv>=0.30 | 290 | 183 | 49.73 % | 77.60 % | 78.31 % |
| unknown | 100 | 100 | 44.00 % | 100.00 % | n/a |

**Latency 귀속 (per-decision)**

| stage | n | 비중 | latency mean ms | MPC rollout CPU ms | verify logits ms | selected tokens mean |
|---|---|---|---|---|---|---|
| draft_verify | 1797 | 38.23 % | 90.199 | 0.675 | 1.698 | 162.128 |
| fallback | 969 | 20.62 % | 74.712 | n/a | n/a | 148.383 |
| queue_serve | 1934 | 41.15 % | 1.822 | n/a | n/a | 0.000 |

전체 decision latency 합 238007 ms 중 MPC brute-force rollout CPU 시간은 1213 ms (**0.51 %**), throughput predictor까지 포함해도 0.70 %.

