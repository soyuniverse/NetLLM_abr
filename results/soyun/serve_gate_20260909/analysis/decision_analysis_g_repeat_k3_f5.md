### g_repeat_k3_f5 — per-decision post-hoc analysis

`results/soyun/serve_gate_20260909/g_repeat_k3_f5/decisions.jsonl` — 4700 decisions over 100 traces; 2027 draft+verify steps, 2921 steps where the LLM actually produced an action.

| 지표 | 정의 | 값 | 분모 |
|---|---|---|---|
| 1. MPC draft 1-step 일치율 | `mpc_draft_actions[0] == llm_target_action` | 87.81 % | 2027 |
| 2. 직전 행동 반복 drafter (가상) | `last_action == llm_action` | 87.61 % | 2921 |
| 2b. 동일 기준(verify step만) | `last_action == llm_target_action` | 87.81 % | 2027 |
| 3. LLM 행동 자기상관 (인접 t) | `llm_action(t) == llm_action(t-1)` | 85.56 % | 1807 |
| 3b. LLM 호출 순서 기준 | 직전 LLM 호출의 행동과 비교 | 83.37 % | 2821 |

**Draft 위치별 일치율 (k=3)**

| draft position | n | MPC 일치율 | repeat-last 일치율 |
|---|---|---|---|
| 0 | 2027 | 87.81 % | 87.81 % |
| 1 | 1980 | 84.09 % | 84.09 % |
| 2 | 1941 | 81.40 % | 81.40 % |

accepted-prefix 길이 평균 — MPC **2.286** / repeat-last **2.286** (최대 3). MPC prefix 분포 {'0': 247, '1': 251, '2': 205, '3': 1324}, repeat-last {'0': 247, '1': 251, '2': 205, '3': 1324}.

**buffer 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| <5s | 126 | 115 | 95.65 % | 95.65 % | 69.57 % |
| 5-10s | 246 | 53 | 79.25 % | 79.25 % | 76.09 % |
| 10-20s | 662 | 276 | 89.13 % | 89.13 % | 85.05 % |
| >=20s | 3666 | 1583 | 87.30 % | 87.30 % | 86.15 % |

**throughput 안정성(최근 6 관측 CV) 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| stable cv<0.10 | 3341 | 1293 | 88.55 % | 88.55 % | 84.58 % |
| moderate 0.10-0.30 | 969 | 474 | 88.61 % | 88.61 % | 89.94 % |
| volatile cv>=0.30 | 290 | 160 | 71.88 % | 71.88 % | 75.66 % |
| unknown | 100 | 100 | 100.00 % | 100.00 % | n/a |

**Latency 귀속 (per-decision)**

| stage | n | 비중 | latency mean ms | MPC rollout CPU ms | verify logits ms | selected tokens mean |
|---|---|---|---|---|---|---|
| draft_verify | 2027 | 43.13 % | 80.088 | 0.209 | 1.060 | 148.787 |
| fallback | 894 | 19.02 % | 71.701 | n/a | n/a | 147.949 |
| queue_serve | 1779 | 37.85 % | 1.831 | n/a | n/a | 0.000 |

전체 decision latency 합 229696 ms 중 MPC brute-force rollout CPU 시간은 424 ms (**0.18 %**), throughput predictor까지 포함해도 0.39 %.

