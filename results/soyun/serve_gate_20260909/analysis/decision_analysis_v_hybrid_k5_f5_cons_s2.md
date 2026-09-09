### v_hybrid_k5_f5_cons_s2 — per-decision post-hoc analysis

`results/soyun/serve_gate_20260909/v_hybrid_k5_f5_cons_s2/decisions.jsonl` — 4700 decisions over 100 traces; 1770 draft+verify steps, 2724 steps where the LLM actually produced an action.

| 지표 | 정의 | 값 | 분모 |
|---|---|---|---|
| 1. MPC draft 1-step 일치율 | `mpc_draft_actions[0] == llm_target_action` | 82.43 % | 1770 |
| 2. 직전 행동 반복 drafter (가상) | `last_action == llm_action` | 87.89 % | 2724 |
| 2b. 동일 기준(verify step만) | `last_action == llm_target_action` | 87.68 % | 1770 |
| 3. LLM 행동 자기상관 (인접 t) | `llm_action(t) == llm_action(t-1)` | 87.77 % | 1872 |
| 3b. LLM 호출 순서 기준 | 직전 LLM 호출의 행동과 비교 | 83.31 % | 2624 |

**Draft 위치별 일치율 (k=5)**

| draft position | n | MPC 일치율 | repeat-last 일치율 |
|---|---|---|---|
| 0 | 1770 | 82.43 % | 87.68 % |
| 1 | 1732 | 78.52 % | 81.93 % |
| 2 | 1691 | 78.00 % | 79.54 % |
| 3 | 1651 | 75.11 % | 77.17 % |
| 4 | 1611 | 71.26 % | 74.86 % |

accepted-prefix 길이 평균 — MPC **3.110** / repeat-last **3.310** (최대 5). MPC prefix 분포 {'0': 311, '1': 228, '2': 159, '3': 129, '4': 143, '5': 800}, repeat-last {'0': 218, '1': 243, '2': 185, '3': 119, '4': 136, '5': 869}.

**buffer 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| <5s | 109 | 106 | 45.28 % | 96.23 % | 33.33 % |
| 5-10s | 244 | 103 | 95.15 % | 95.15 % | 89.69 % |
| 10-20s | 613 | 174 | 87.36 % | 86.78 % | 88.51 % |
| >=20s | 3734 | 1387 | 83.71 % | 86.59 % | 87.77 % |

**throughput 안정성(최근 6 관측 CV) 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| stable cv<0.10 | 3305 | 1029 | 86.88 % | 86.78 % | 87.94 % |
| moderate 0.10-0.30 | 1019 | 475 | 90.53 % | 90.53 % | 90.41 % |
| volatile cv>=0.30 | 276 | 166 | 54.82 % | 77.71 % | 79.31 % |
| unknown | 100 | 100 | 44.00 % | 100.00 % | n/a |

**Latency 귀속 (per-decision)**

| stage | n | 비중 | latency mean ms | MPC rollout CPU ms | verify logits ms | selected tokens mean |
|---|---|---|---|---|---|---|
| draft_verify | 1770 | 37.66 % | 89.238 | 0.681 | 1.727 | 161.695 |
| fallback | 956 | 20.34 % | 74.193 | n/a | n/a | 148.718 |
| queue_serve | 1974 | 42.00 % | 1.893 | n/a | n/a | 0.000 |

전체 decision latency 합 232618 ms 중 MPC brute-force rollout CPU 시간은 1206 ms (**0.52 %**), throughput predictor까지 포함해도 0.72 %.

