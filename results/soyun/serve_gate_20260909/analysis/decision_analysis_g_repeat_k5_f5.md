### g_repeat_k5_f5 — per-decision post-hoc analysis

`results/soyun/serve_gate_20260909/g_repeat_k5_f5/decisions.jsonl` — 4700 decisions over 100 traces; 1719 draft+verify steps, 2720 steps where the LLM actually produced an action.

| 지표 | 정의 | 값 | 분모 |
|---|---|---|---|
| 1. MPC draft 1-step 일치율 | `mpc_draft_actions[0] == llm_target_action` | 87.90 % | 1719 |
| 2. 직전 행동 반복 drafter (가상) | `last_action == llm_action` | 87.87 % | 2720 |
| 2b. 동일 기준(verify step만) | `last_action == llm_target_action` | 87.90 % | 1719 |
| 3. LLM 행동 자기상관 (인접 t) | `llm_action(t) == llm_action(t-1)` | 86.84 % | 1861 |
| 3b. LLM 호출 순서 기준 | 직전 LLM 호출의 행동과 비교 | 82.48 % | 2620 |

**Draft 위치별 일치율 (k=5)**

| draft position | n | MPC 일치율 | repeat-last 일치율 |
|---|---|---|---|
| 0 | 1719 | 87.90 % | 87.90 % |
| 1 | 1673 | 84.40 % | 84.40 % |
| 2 | 1641 | 81.35 % | 81.35 % |
| 3 | 1600 | 83.31 % | 83.31 % |
| 4 | 1556 | 77.19 % | 77.19 % |

accepted-prefix 길이 평균 — MPC **3.373** / repeat-last **3.373** (최대 5). MPC prefix 분포 {'0': 208, '1': 226, '2': 165, '3': 110, '4': 138, '5': 872}, repeat-last {'0': 208, '1': 226, '2': 165, '3': 110, '4': 138, '5': 872}.

**buffer 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| <5s | 119 | 111 | 94.59 % | 94.59 % | 47.06 % |
| 5-10s | 238 | 29 | 86.21 % | 86.21 % | 90.91 % |
| 10-20s | 654 | 207 | 91.79 % | 91.79 % | 87.83 % |
| >=20s | 3689 | 1372 | 86.81 % | 86.81 % | 87.03 % |

**throughput 안정성(최근 6 관측 CV) 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| stable cv<0.10 | 3309 | 992 | 87.10 % | 87.10 % | 86.46 % |
| moderate 0.10-0.30 | 999 | 467 | 89.72 % | 89.72 % | 89.64 % |
| volatile cv>=0.30 | 292 | 160 | 80.00 % | 80.00 % | 79.63 % |
| unknown | 100 | 100 | 100.00 % | 100.00 % | n/a |

**Latency 귀속 (per-decision)**

| stage | n | 비중 | latency mean ms | MPC rollout CPU ms | verify logits ms | selected tokens mean |
|---|---|---|---|---|---|---|
| draft_verify | 1719 | 36.57 % | 98.361 | 0.271 | 1.657 | 165.952 |
| fallback | 1001 | 21.30 % | 81.184 | n/a | n/a | 148.059 |
| queue_serve | 1980 | 42.13 % | 1.847 | n/a | n/a | 0.000 |

전체 decision latency 합 254005 ms 중 MPC brute-force rollout CPU 시간은 465 ms (**0.18 %**), throughput predictor까지 포함해도 0.36 %.

