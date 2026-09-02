### F — per-decision post-hoc analysis

`results/soyun/baseline6_20260902/f_all_three/decisions.jsonl` — 4700 decisions over 100 traces; 4124 draft+verify steps, 4408 steps where the LLM actually produced an action.

| 지표 | 정의 | 값 | 분모 |
|---|---|---|---|
| 1. MPC draft 1-step 일치율 | `mpc_draft_actions[0] == llm_target_action` | 13.19 % | 4124 |
| 2. 직전 행동 반복 drafter (가상) | `last_action == llm_action` | 91.63 % | 4408 |
| 2b. 동일 기준(verify step만) | `last_action == llm_target_action` | 92.17 % | 4124 |
| 3. LLM 행동 자기상관 (인접 t) | `llm_action(t) == llm_action(t-1)` | 91.76 % | 4053 |
| 3b. LLM 호출 순서 기준 | 직전 LLM 호출의 행동과 비교 | 91.39 % | 4308 |

**Draft 위치별 일치율 (k=3)**

| draft position | n | MPC 일치율 | repeat-last 일치율 |
|---|---|---|---|
| 0 | 4124 | 13.19 % | 92.17 % |
| 1 | 4039 | 8.05 % | 36.64 % |
| 2 | 3954 | 13.96 % | 20.76 % |

accepted-prefix 길이 평균 — MPC **0.184** / repeat-last **1.446** (최대 3). MPC prefix 분포 {'0': 3580, '1': 396, '2': 83, '3': 65}, repeat-last {'0': 323, '1': 2352, '2': 735, '3': 714}.

**buffer 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| <5s | 106 | 102 | 44.12 % | 98.04 % | 0.00 % |
| 5-10s | 226 | 135 | 20.00 % | 98.52 % | 99.09 % |
| 10-20s | 541 | 447 | 20.36 % | 91.50 % | 90.49 % |
| >=20s | 3827 | 3440 | 11.08 % | 91.83 % | 91.72 % |

**throughput 안정성(최근 6 관측 CV) 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| stable cv<0.10 | 3314 | 2981 | 9.23 % | 92.02 % | 92.42 % |
| moderate 0.10-0.30 | 993 | 833 | 17.29 % | 93.40 % | 92.55 % |
| volatile cv>=0.30 | 293 | 210 | 39.05 % | 85.71 % | 82.82 % |
| unknown | 100 | 100 | 43.00 % | 100.00 % | n/a |

**Latency 귀속 (per-decision)**

| stage | n | 비중 | latency mean ms | MPC rollout CPU ms | verify logits ms | selected tokens mean |
|---|---|---|---|---|---|---|
| draft_verify | 4124 | 87.74 % | 32.759 | 0.164 | 0.031 | 35.024 |
| fallback | 284 | 6.04 % | 27.469 | n/a | n/a | 19.743 |
| queue_serve | 292 | 6.21 % | 0.819 | n/a | n/a | 0.000 |

전체 decision latency 합 143139 ms 중 MPC brute-force rollout CPU 시간은 678 ms (**0.47 %**), throughput predictor까지 포함해도 0.63 %.

