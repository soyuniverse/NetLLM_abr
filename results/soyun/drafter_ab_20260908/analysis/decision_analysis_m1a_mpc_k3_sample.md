### m1a_mpc_k3_sample — per-decision post-hoc analysis

`results/soyun/drafter_ab_20260908/m1a_mpc_k3_sample/decisions.jsonl` — 4700 decisions over 100 traces; 4001 draft+verify steps, 4354 steps where the LLM actually produced an action.

| 지표 | 정의 | 값 | 분모 |
|---|---|---|---|
| 1. MPC draft 1-step 일치율 | `mpc_draft_actions[0] == llm_target_action` | 16.27 % | 4001 |
| 2. 직전 행동 반복 drafter (가상) | `last_action == llm_action` | 89.02 % | 4354 |
| 2b. 동일 기준(verify step만) | `last_action == llm_target_action` | 89.38 % | 4001 |
| 3. LLM 행동 자기상관 (인접 t) | `llm_action(t) == llm_action(t-1)` | 88.69 % | 3961 |
| 3b. LLM 호출 순서 기준 | 직전 LLM 호출의 행동과 비교 | 88.32 % | 4254 |

**Draft 위치별 일치율 (k=3)**

| draft position | n | MPC 일치율 | repeat-last 일치율 |
|---|---|---|---|
| 0 | 4001 | 16.27 % | 89.38 % |
| 1 | 3912 | 12.65 % | 40.98 % |
| 2 | 3834 | 14.42 % | 25.67 % |

accepted-prefix 길이 평균 — MPC **0.232** / repeat-last **1.474** (최대 3). MPC prefix 분포 {'0': 3350, '1': 461, '2': 102, '3': 88}, repeat-last {'0': 425, '1': 2041, '2': 748, '3': 787}.

**buffer 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| <5s | 112 | 108 | 42.59 % | 95.37 % | 40.00 % |
| 5-10s | 241 | 143 | 18.18 % | 97.90 % | 97.48 % |
| 10-20s | 640 | 500 | 22.20 % | 92.00 % | 91.02 % |
| >=20s | 3707 | 3250 | 14.40 % | 88.40 % | 88.16 % |

**throughput 안정성(최근 6 관측 CV) 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| stable cv<0.10 | 3304 | 2877 | 11.61 % | 90.23 % | 90.06 % |
| moderate 0.10-0.30 | 1025 | 832 | 23.08 % | 88.10 % | 87.54 % |
| volatile cv>=0.30 | 271 | 192 | 42.71 % | 76.56 % | 78.87 % |
| unknown | 100 | 100 | 43.00 % | 100.00 % | n/a |

**Latency 귀속 (per-decision)**

| stage | n | 비중 | latency mean ms | MPC rollout CPU ms | verify logits ms | selected tokens mean |
|---|---|---|---|---|---|---|
| draft_verify | 4001 | 85.13 % | 89.302 | 0.342 | 1.015 | 148.341 |
| fallback | 353 | 7.51 % | 86.178 | n/a | n/a | 143.159 |
| queue_serve | 346 | 7.36 % | 1.762 | n/a | n/a | 0.000 |

전체 decision latency 합 388327 ms 중 MPC brute-force rollout CPU 시간은 1367 ms (**0.35 %**), throughput predictor까지 포함해도 0.47 %.

