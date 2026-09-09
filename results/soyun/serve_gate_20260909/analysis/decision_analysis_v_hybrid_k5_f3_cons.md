### v_hybrid_k5_f3_cons — per-decision post-hoc analysis

`results/soyun/serve_gate_20260909/v_hybrid_k5_f3_cons/decisions.jsonl` — 4700 decisions over 100 traces; 1762 draft+verify steps, 2733 steps where the LLM actually produced an action.

| 지표 | 정의 | 값 | 분모 |
|---|---|---|---|
| 1. MPC draft 1-step 일치율 | `mpc_draft_actions[0] == llm_target_action` | 82.69 % | 1762 |
| 2. 직전 행동 반복 drafter (가상) | `last_action == llm_action` | 88.51 % | 2733 |
| 2b. 동일 기준(verify step만) | `last_action == llm_target_action` | 88.02 % | 1762 |
| 3. LLM 행동 자기상관 (인접 t) | `llm_action(t) == llm_action(t-1)` | 87.69 % | 1893 |
| 3b. LLM 호출 순서 기준 | 직전 LLM 호출의 행동과 비교 | 84.05 % | 2633 |

**Draft 위치별 일치율 (k=5)**

| draft position | n | MPC 일치율 | repeat-last 일치율 |
|---|---|---|---|
| 0 | 1762 | 82.69 % | 88.02 % |
| 1 | 1722 | 79.27 % | 81.82 % |
| 2 | 1686 | 78.77 % | 80.19 % |
| 3 | 1645 | 74.29 % | 76.05 % |
| 4 | 1600 | 71.25 % | 75.75 % |

accepted-prefix 길이 평균 — MPC **3.148** / repeat-last **3.340** (최대 5). MPC prefix 분포 {'0': 305, '1': 218, '2': 146, '3': 155, '4': 119, '5': 819}, repeat-last {'0': 211, '1': 244, '2': 162, '3': 150, '4': 108, '5': 887}.

**buffer 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| <5s | 113 | 104 | 43.27 % | 99.04 % | 66.67 % |
| 5-10s | 238 | 98 | 97.96 % | 97.96 % | 92.47 % |
| 10-20s | 640 | 187 | 86.10 % | 86.10 % | 87.19 % |
| >=20s | 3709 | 1373 | 84.12 % | 86.74 % | 87.52 % |

**throughput 안정성(최근 6 관측 CV) 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| stable cv<0.10 | 3336 | 1017 | 88.59 % | 88.69 % | 88.12 % |
| moderate 0.10-0.30 | 983 | 474 | 87.76 % | 87.76 % | 90.15 % |
| volatile cv>=0.30 | 281 | 171 | 56.14 % | 77.78 % | 78.93 % |
| unknown | 100 | 100 | 44.00 % | 100.00 % | n/a |

**Latency 귀속 (per-decision)**

| stage | n | 비중 | latency mean ms | MPC rollout CPU ms | verify logits ms | selected tokens mean |
|---|---|---|---|---|---|---|
| draft_verify | 1762 | 37.49 % | 95.100 | 0.689 | 1.689 | 162.016 |
| fallback | 971 | 20.66 % | 79.225 | n/a | n/a | 149.039 |
| queue_serve | 1967 | 41.85 % | 1.895 | n/a | n/a | 0.000 |

전체 decision latency 합 248219 ms 중 MPC brute-force rollout CPU 시간은 1214 ms (**0.49 %**), throughput predictor까지 포함해도 0.68 %.

