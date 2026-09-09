### v_repeat_k5_f5_cons — per-decision post-hoc analysis

`results/soyun/serve_gate_20260909/v_repeat_k5_f5_cons/decisions.jsonl` — 4700 decisions over 100 traces; 1728 draft+verify steps, 2738 steps where the LLM actually produced an action.

| 지표 | 정의 | 값 | 분모 |
|---|---|---|---|
| 1. MPC draft 1-step 일치율 | `mpc_draft_actions[0] == llm_target_action` | 87.62 % | 1728 |
| 2. 직전 행동 반복 drafter (가상) | `last_action == llm_action` | 87.73 % | 2738 |
| 2b. 동일 기준(verify step만) | `last_action == llm_target_action` | 87.62 % | 1728 |
| 3. LLM 행동 자기상관 (인접 t) | `llm_action(t) == llm_action(t-1)` | 86.79 % | 1885 |
| 3b. LLM 호출 순서 기준 | 직전 LLM 호출의 행동과 비교 | 82.45 % | 2638 |

**Draft 위치별 일치율 (k=5)**

| draft position | n | MPC 일치율 | repeat-last 일치율 |
|---|---|---|---|
| 0 | 1728 | 87.62 % | 87.62 % |
| 1 | 1681 | 83.94 % | 83.94 % |
| 2 | 1647 | 82.15 % | 82.15 % |
| 3 | 1610 | 81.24 % | 81.24 % |
| 4 | 1569 | 77.18 % | 77.18 % |

accepted-prefix 길이 평균 — MPC **3.348** / repeat-last **3.348** (최대 5). MPC prefix 분포 {'0': 214, '1': 242, '2': 150, '3': 124, '4': 119, '5': 879}, repeat-last {'0': 214, '1': 242, '2': 150, '3': 124, '4': 119, '5': 879}.

**buffer 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| <5s | 118 | 110 | 95.45 % | 95.45 % | 46.67 % |
| 5-10s | 242 | 27 | 92.59 % | 92.59 % | 93.18 % |
| 10-20s | 681 | 222 | 88.74 % | 88.74 % | 85.65 % |
| >=20s | 3659 | 1369 | 86.71 % | 86.71 % | 87.14 % |

**throughput 안정성(최근 6 관측 CV) 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| stable cv<0.10 | 3300 | 998 | 86.57 % | 86.57 % | 86.86 % |
| moderate 0.10-0.30 | 997 | 460 | 90.65 % | 90.65 % | 89.28 % |
| volatile cv>=0.30 | 303 | 170 | 78.24 % | 78.24 % | 79.65 % |
| unknown | 100 | 100 | 100.00 % | 100.00 % | n/a |

**Latency 귀속 (per-decision)**

| stage | n | 비중 | latency mean ms | MPC rollout CPU ms | verify logits ms | selected tokens mean |
|---|---|---|---|---|---|---|
| draft_verify | 1728 | 36.77 % | 96.470 | 0.265 | 1.656 | 165.958 |
| fallback | 1012 | 21.53 % | 79.720 | n/a | n/a | 148.377 |
| queue_serve | 1960 | 41.70 % | 1.855 | n/a | n/a | 0.000 |

전체 decision latency 합 251011 ms 중 MPC brute-force rollout CPU 시간은 457 ms (**0.18 %**), throughput predictor까지 포함해도 0.36 %.

