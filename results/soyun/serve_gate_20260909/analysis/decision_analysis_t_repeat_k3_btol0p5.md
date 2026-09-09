### t_repeat_k3_btol0p5 — per-decision post-hoc analysis

`results/soyun/serve_gate_20260909/t_repeat_k3_btol0p5/decisions.jsonl` — 4700 decisions over 100 traces; 2089 draft+verify steps, 3220 steps where the LLM actually produced an action.

| 지표 | 정의 | 값 | 분모 |
|---|---|---|---|
| 1. MPC draft 1-step 일치율 | `mpc_draft_actions[0] == llm_target_action` | 87.27 % | 2089 |
| 2. 직전 행동 반복 drafter (가상) | `last_action == llm_action` | 88.14 % | 3220 |
| 2b. 동일 기준(verify step만) | `last_action == llm_target_action` | 87.27 % | 2089 |
| 3. LLM 행동 자기상관 (인접 t) | `llm_action(t) == llm_action(t-1)` | 86.85 % | 2243 |
| 3b. LLM 호출 순서 기준 | 직전 LLM 호출의 행동과 비교 | 85.29 % | 3120 |

**Draft 위치별 일치율 (k=3)**

| draft position | n | MPC 일치율 | repeat-last 일치율 |
|---|---|---|---|
| 0 | 2089 | 87.27 % | 87.27 % |
| 1 | 2039 | 86.51 % | 86.51 % |
| 2 | 1997 | 83.32 % | 83.32 % |

accepted-prefix 길이 평균 — MPC **2.329** / repeat-last **2.329** (최대 3). MPC prefix 분포 {'0': 266, '1': 207, '2': 189, '3': 1427}, repeat-last {'0': 266, '1': 207, '2': 189, '3': 1427}.

**buffer 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| <5s | 116 | 109 | 95.41 % | 95.41 % | 46.67 % |
| 5-10s | 243 | 54 | 79.63 % | 79.63 % | 73.68 % |
| 10-20s | 596 | 251 | 88.84 % | 88.84 % | 86.82 % |
| >=20s | 3745 | 1675 | 86.75 % | 86.75 % | 87.54 % |

**throughput 안정성(최근 6 관측 CV) 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| stable cv<0.10 | 3327 | 1335 | 87.64 % | 87.64 % | 87.39 % |
| moderate 0.10-0.30 | 987 | 496 | 88.10 % | 88.10 % | 89.72 % |
| volatile cv>=0.30 | 286 | 158 | 73.42 % | 73.42 % | 75.81 % |
| unknown | 100 | 100 | 100.00 % | 100.00 % | n/a |

**Latency 귀속 (per-decision)**

| stage | n | 비중 | latency mean ms | MPC rollout CPU ms | verify logits ms | selected tokens mean |
|---|---|---|---|---|---|---|
| draft_verify | 2089 | 44.45 % | 85.164 | 0.215 | 1.095 | 149.541 |
| fallback | 1131 | 24.06 % | 77.800 | n/a | n/a | 149.041 |
| queue_serve | 1480 | 31.49 % | 1.857 | n/a | n/a | 0.000 |

전체 decision latency 합 268648 ms 중 MPC brute-force rollout CPU 시간은 450 ms (**0.17 %**), throughput predictor까지 포함해도 0.34 %.

