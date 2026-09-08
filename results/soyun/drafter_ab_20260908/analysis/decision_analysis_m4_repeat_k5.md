### m4_repeat_k5 — per-decision post-hoc analysis

`results/soyun/drafter_ab_20260908/m4_repeat_k5/decisions.jsonl` — 4700 decisions over 100 traces; 1730 draft+verify steps, 2730 steps where the LLM actually produced an action.

| 지표 | 정의 | 값 | 분모 |
|---|---|---|---|
| 1. MPC draft 1-step 일치율 | `mpc_draft_actions[0] == llm_target_action` | 87.17 % | 1730 |
| 2. 직전 행동 반복 drafter (가상) | `last_action == llm_action` | 87.33 % | 2730 |
| 2b. 동일 기준(verify step만) | `last_action == llm_target_action` | 87.17 % | 1730 |
| 3. LLM 행동 자기상관 (인접 t) | `llm_action(t) == llm_action(t-1)` | 86.28 % | 1881 |
| 3b. LLM 호출 순서 기준 | 직전 LLM 호출의 행동과 비교 | 82.05 % | 2630 |

**Draft 위치별 일치율 (k=5)**

| draft position | n | MPC 일치율 | repeat-last 일치율 |
|---|---|---|---|
| 0 | 1730 | 87.17 % | 87.17 % |
| 1 | 1684 | 83.73 % | 83.73 % |
| 2 | 1649 | 81.56 % | 81.56 % |
| 3 | 1611 | 80.82 % | 80.82 % |
| 4 | 1571 | 76.96 % | 76.96 % |

accepted-prefix 길이 평균 — MPC **3.314** / repeat-last **3.314** (최대 5). MPC prefix 분포 {'0': 222, '1': 244, '2': 156, '3': 122, '4': 119, '5': 867}, repeat-last {'0': 222, '1': 244, '2': 156, '3': 122, '4': 119, '5': 867}.

**buffer 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| <5s | 118 | 110 | 95.45 % | 95.45 % | 46.67 % |
| 5-10s | 244 | 26 | 92.31 % | 92.31 % | 93.02 % |
| 10-20s | 691 | 229 | 88.65 % | 88.65 % | 86.16 % |
| >=20s | 3647 | 1365 | 86.15 % | 86.15 % | 86.49 % |

**throughput 안정성(최근 6 관측 CV) 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| stable cv<0.10 | 3299 | 998 | 86.17 % | 86.17 % | 86.07 % |
| moderate 0.10-0.30 | 1000 | 463 | 89.85 % | 89.85 % | 88.92 % |
| volatile cv>=0.30 | 301 | 169 | 78.11 % | 78.11 % | 79.51 % |
| unknown | 100 | 100 | 100.00 % | 100.00 % | n/a |

**Latency 귀속 (per-decision)**

| stage | n | 비중 | latency mean ms | MPC rollout CPU ms | verify logits ms | selected tokens mean |
|---|---|---|---|---|---|---|
| draft_verify | 1730 | 36.81 % | 111.740 | 0.249 | 1.690 | 166.192 |
| fallback | 1000 | 21.28 % | 92.604 | n/a | n/a | 148.520 |
| queue_serve | 1970 | 41.91 % | 1.783 | n/a | n/a | 0.000 |

전체 decision latency 합 289427 ms 중 MPC brute-force rollout CPU 시간은 431 ms (**0.15 %**), throughput predictor까지 포함해도 0.31 %.

