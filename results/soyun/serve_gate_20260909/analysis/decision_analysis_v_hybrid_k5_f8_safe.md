### v_hybrid_k5_f8_safe — per-decision post-hoc analysis

`results/soyun/serve_gate_20260909/v_hybrid_k5_f8_safe/decisions.jsonl` — 4439 decisions over 100 traces; 1654 draft+verify steps, 2565 steps where the LLM actually produced an action.

| 지표 | 정의 | 값 | 분모 |
|---|---|---|---|
| 1. MPC draft 1-step 일치율 | `mpc_draft_actions[0] == llm_target_action` | 84.34 % | 1654 |
| 2. 직전 행동 반복 drafter (가상) | `last_action == llm_action` | 88.19 % | 2565 |
| 2b. 동일 기준(verify step만) | `last_action == llm_target_action` | 87.67 % | 1654 |
| 3. LLM 행동 자기상관 (인접 t) | `llm_action(t) == llm_action(t-1)` | 87.56 % | 1737 |
| 3b. LLM 호출 순서 기준 | 직전 LLM 호출의 행동과 비교 | 82.76 % | 2465 |

**Draft 위치별 일치율 (k=5)**

| draft position | n | MPC 일치율 | repeat-last 일치율 |
|---|---|---|---|
| 0 | 1654 | 84.34 % | 87.67 % |
| 1 | 1607 | 80.77 % | 81.21 % |
| 2 | 1574 | 81.19 % | 79.16 % |
| 3 | 1531 | 79.03 % | 77.79 % |
| 4 | 1498 | 74.77 % | 73.90 % |

accepted-prefix 길이 평균 — MPC **3.204** / repeat-last **3.264** (최대 5). MPC prefix 분포 {'0': 259, '1': 224, '2': 145, '3': 113, '4': 118, '5': 795}, repeat-last {'0': 204, '1': 259, '2': 161, '3': 110, '4': 112, '5': 808}.

**buffer 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| 5-10s | 103 | 80 | 93.75 % | 93.75 % | 30.00 % |
| 10-20s | 637 | 189 | 85.71 % | 87.30 % | 86.79 % |
| >=20s | 3699 | 1385 | 83.61 % | 87.36 % | 88.01 % |

**throughput 안정성(최근 6 관측 CV) 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| stable cv<0.10 | 3226 | 1035 | 88.31 % | 88.31 % | 87.56 % |
| moderate 0.10-0.30 | 954 | 452 | 88.94 % | 88.94 % | 90.10 % |
| volatile cv>=0.30 | 259 | 167 | 47.31 % | 80.24 % | 79.83 % |

**Latency 귀속 (per-decision)**

| stage | n | 비중 | latency mean ms | MPC rollout CPU ms | verify logits ms | selected tokens mean |
|---|---|---|---|---|---|---|
| draft_verify | 1654 | 37.26 % | 98.936 | 0.557 | 1.650 | 170.539 |
| fallback | 911 | 20.52 % | 81.027 | n/a | n/a | 152.247 |
| queue_serve | 1874 | 42.22 % | 1.801 | n/a | n/a | 0.000 |

전체 decision latency 합 240832 ms 중 MPC brute-force rollout CPU 시간은 921 ms (**0.38 %**), throughput predictor까지 포함해도 0.56 %.

