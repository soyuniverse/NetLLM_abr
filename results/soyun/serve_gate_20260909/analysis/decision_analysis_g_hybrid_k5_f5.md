### g_hybrid_k5_f5 — per-decision post-hoc analysis

`results/soyun/serve_gate_20260909/g_hybrid_k5_f5/decisions.jsonl` — 4700 decisions over 100 traces; 1775 draft+verify steps, 2765 steps where the LLM actually produced an action.

| 지표 | 정의 | 값 | 분모 |
|---|---|---|---|
| 1. MPC draft 1-step 일치율 | `mpc_draft_actions[0] == llm_target_action` | 83.49 % | 1775 |
| 2. 직전 행동 반복 drafter (가상) | `last_action == llm_action` | 88.50 % | 2765 |
| 2b. 동일 기준(verify step만) | `last_action == llm_target_action` | 88.51 % | 1775 |
| 3. LLM 행동 자기상관 (인접 t) | `llm_action(t) == llm_action(t-1)` | 87.73 % | 1923 |
| 3b. LLM 호출 순서 기준 | 직전 LLM 호출의 행동과 비교 | 84.09 % | 2665 |

**Draft 위치별 일치율 (k=5)**

| draft position | n | MPC 일치율 | repeat-last 일치율 |
|---|---|---|---|
| 0 | 1775 | 83.49 % | 88.51 % |
| 1 | 1729 | 79.58 % | 82.13 % |
| 2 | 1695 | 78.17 % | 79.53 % |
| 3 | 1650 | 74.61 % | 76.91 % |
| 4 | 1606 | 72.17 % | 76.46 % |

accepted-prefix 길이 평균 — MPC **3.142** / repeat-last **3.336** (최대 5). MPC prefix 분포 {'0': 293, '1': 228, '2': 161, '3': 162, '4': 114, '5': 817}, repeat-last {'0': 204, '1': 249, '2': 175, '3': 154, '4': 105, '5': 888}.

**buffer 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| <5s | 106 | 103 | 42.72 % | 100.00 % | 75.00 % |
| 5-10s | 233 | 102 | 95.10 % | 95.10 % | 90.53 % |
| 10-20s | 668 | 193 | 90.16 % | 89.12 % | 87.61 % |
| >=20s | 3693 | 1377 | 84.75 % | 87.07 % | 87.61 % |

**throughput 안정성(최근 6 관측 CV) 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| stable cv<0.10 | 3317 | 1019 | 89.60 % | 89.89 % | 90.58 % |
| moderate 0.10-0.30 | 1003 | 481 | 88.77 % | 88.77 % | 88.85 % |
| volatile cv>=0.30 | 280 | 175 | 56.00 % | 73.14 % | 75.28 % |
| unknown | 100 | 100 | 44.00 % | 100.00 % | n/a |

**Latency 귀속 (per-decision)**

| stage | n | 비중 | latency mean ms | MPC rollout CPU ms | verify logits ms | selected tokens mean |
|---|---|---|---|---|---|---|
| draft_verify | 1775 | 37.77 % | 97.098 | 0.678 | 1.688 | 161.861 |
| fallback | 990 | 21.06 % | 81.262 | n/a | n/a | 149.093 |
| queue_serve | 1935 | 41.17 % | 1.851 | n/a | n/a | 0.000 |

전체 decision latency 합 256379 ms 중 MPC brute-force rollout CPU 시간은 1203 ms (**0.47 %**), throughput predictor까지 포함해도 0.65 %.

