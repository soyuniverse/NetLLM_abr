### v_hybrid_k5_f5_safe — per-decision post-hoc analysis

`results/soyun/serve_gate_20260909/v_hybrid_k5_f5_safe/decisions.jsonl` — 4585 decisions over 100 traces; 1703 draft+verify steps, 2659 steps where the LLM actually produced an action.

| 지표 | 정의 | 값 | 분모 |
|---|---|---|---|
| 1. MPC draft 1-step 일치율 | `mpc_draft_actions[0] == llm_target_action` | 84.26 % | 1703 |
| 2. 직전 행동 반복 drafter (가상) | `last_action == llm_action` | 88.23 % | 2659 |
| 2b. 동일 기준(verify step만) | `last_action == llm_target_action` | 88.26 % | 1703 |
| 3. LLM 행동 자기상관 (인접 t) | `llm_action(t) == llm_action(t-1)` | 88.17 % | 1835 |
| 3b. LLM 호출 순서 기준 | 직전 LLM 호출의 행동과 비교 | 83.55 % | 2559 |

**Draft 위치별 일치율 (k=5)**

| draft position | n | MPC 일치율 | repeat-last 일치율 |
|---|---|---|---|
| 0 | 1703 | 84.26 % | 88.26 % |
| 1 | 1662 | 81.65 % | 81.11 % |
| 2 | 1620 | 80.93 % | 79.63 % |
| 3 | 1580 | 81.33 % | 79.37 % |
| 4 | 1532 | 75.46 % | 73.96 % |

accepted-prefix 길이 평균 — MPC **3.242** / repeat-last **3.319** (최대 5). MPC prefix 분포 {'0': 268, '1': 221, '2': 149, '3': 93, '4': 137, '5': 835}, repeat-last {'0': 200, '1': 266, '2': 157, '3': 96, '4': 135, '5': 849}.

**buffer 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| 5-10s | 233 | 122 | 92.62 % | 95.08 % | 73.33 % |
| 10-20s | 633 | 179 | 88.83 % | 91.62 % | 89.85 % |
| >=20s | 3719 | 1402 | 82.95 % | 87.23 % | 88.25 % |

**throughput 안정성(최근 6 관측 CV) 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| stable cv<0.10 | 3296 | 1043 | 89.17 % | 89.17 % | 89.57 % |
| moderate 0.10-0.30 | 1014 | 478 | 88.08 % | 88.08 % | 89.44 % |
| volatile cv>=0.30 | 275 | 182 | 46.15 % | 83.52 % | 80.23 % |

**Latency 귀속 (per-decision)**

| stage | n | 비중 | latency mean ms | MPC rollout CPU ms | verify logits ms | selected tokens mean |
|---|---|---|---|---|---|---|
| draft_verify | 1703 | 37.14 % | 97.757 | 0.575 | 1.683 | 167.526 |
| fallback | 956 | 20.85 % | 80.394 | n/a | n/a | 149.770 |
| queue_serve | 1926 | 42.01 % | 1.811 | n/a | n/a | 0.000 |

전체 decision latency 합 246824 ms 중 MPC brute-force rollout CPU 시간은 979 ms (**0.40 %**), throughput predictor까지 포함해도 0.58 %.

