### m5_ctrl_s3 — per-decision post-hoc analysis

`results/soyun/serve_gate_20260909/m5_ctrl_s3/decisions.jsonl` — 4700 decisions over 100 traces; 1745 draft+verify steps, 2692 steps where the LLM actually produced an action.

| 지표 | 정의 | 값 | 분모 |
|---|---|---|---|
| 1. MPC draft 1-step 일치율 | `mpc_draft_actions[0] == llm_target_action` | 84.24 % | 1745 |
| 2. 직전 행동 반복 drafter (가상) | `last_action == llm_action` | 88.52 % | 2692 |
| 2b. 동일 기준(verify step만) | `last_action == llm_target_action` | 88.60 % | 1745 |
| 3. LLM 행동 자기상관 (인접 t) | `llm_action(t) == llm_action(t-1)` | 87.78 % | 1841 |
| 3b. LLM 호출 순서 기준 | 직전 LLM 호출의 행동과 비교 | 83.33 % | 2592 |

**Draft 위치별 일치율 (k=5)**

| draft position | n | MPC 일치율 | repeat-last 일치율 |
|---|---|---|---|
| 0 | 1745 | 84.24 % | 88.60 % |
| 1 | 1699 | 78.93 % | 82.05 % |
| 2 | 1666 | 75.81 % | 76.77 % |
| 3 | 1628 | 75.68 % | 77.46 % |
| 4 | 1584 | 70.45 % | 74.81 % |

accepted-prefix 길이 평균 — MPC **3.148** / repeat-last **3.326** (최대 5). MPC prefix 분포 {'0': 275, '1': 239, '2': 178, '3': 116, '4': 134, '5': 803}, repeat-last {'0': 199, '1': 247, '2': 198, '3': 111, '4': 122, '5': 868}.

**buffer 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| <5s | 117 | 107 | 46.73 % | 94.39 % | 33.33 % |
| 5-10s | 251 | 107 | 96.26 % | 94.39 % | 90.91 % |
| 10-20s | 684 | 201 | 90.05 % | 88.06 % | 86.06 % |
| >=20s | 3648 | 1330 | 85.41 % | 87.74 % | 88.13 % |

**throughput 안정성(최근 6 관측 CV) 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| stable cv<0.10 | 3331 | 1016 | 89.76 % | 89.47 % | 88.89 % |
| moderate 0.10-0.30 | 980 | 465 | 89.03 % | 89.03 % | 90.92 % |
| volatile cv>=0.30 | 289 | 164 | 60.98 % | 75.00 % | 75.65 % |
| unknown | 100 | 100 | 44.00 % | 100.00 % | n/a |

**Latency 귀속 (per-decision)**

| stage | n | 비중 | latency mean ms | MPC rollout CPU ms | verify logits ms | selected tokens mean |
|---|---|---|---|---|---|---|
| draft_verify | 1745 | 37.13 % | 89.864 | 0.674 | 1.640 | 161.646 |
| fallback | 947 | 20.15 % | 74.959 | n/a | n/a | 148.483 |
| queue_serve | 2008 | 42.72 % | 1.821 | n/a | n/a | 0.000 |

전체 decision latency 합 231455 ms 중 MPC brute-force rollout CPU 시간은 1177 ms (**0.51 %**), throughput predictor까지 포함해도 0.71 %.

