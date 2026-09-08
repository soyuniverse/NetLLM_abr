### m6_best_plus_selectors — per-decision post-hoc analysis

`results/soyun/drafter_ab_20260908/m6_best_plus_selectors/decisions.jsonl` — 4700 decisions over 100 traces; 2045 draft+verify steps, 2924 steps where the LLM actually produced an action.

| 지표 | 정의 | 값 | 분모 |
|---|---|---|---|
| 1. MPC draft 1-step 일치율 | `mpc_draft_actions[0] == llm_target_action` | 86.16 % | 2045 |
| 2. 직전 행동 반복 drafter (가상) | `last_action == llm_action` | 86.56 % | 2924 |
| 2b. 동일 기준(verify step만) | `last_action == llm_target_action` | 86.16 % | 2045 |
| 3. LLM 행동 자기상관 (인접 t) | `llm_action(t) == llm_action(t-1)` | 84.95 % | 1821 |
| 3b. LLM 호출 순서 기준 | 직전 LLM 호출의 행동과 비교 | 82.79 % | 2824 |

**Draft 위치별 일치율 (k=3)**

| draft position | n | MPC 일치율 | repeat-last 일치율 |
|---|---|---|---|
| 0 | 2045 | 86.16 % | 86.16 % |
| 1 | 2002 | 85.11 % | 85.11 % |
| 2 | 1950 | 83.18 % | 83.18 % |

accepted-prefix 길이 평균 — MPC **2.273** / repeat-last **2.273** (최대 3). MPC prefix 분포 {'0': 283, '1': 228, '2': 181, '3': 1353}, repeat-last {'0': 283, '1': 228, '2': 181, '3': 1353}.

**buffer 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| <5s | 126 | 116 | 93.97 % | 93.97 % | 54.17 % |
| 5-10s | 231 | 44 | 84.09 % | 84.09 % | 76.32 % |
| 10-20s | 600 | 252 | 88.49 % | 88.49 % | 81.87 % |
| >=20s | 3743 | 1633 | 85.30 % | 85.30 % | 85.99 % |

**throughput 안정성(최근 6 관측 CV) 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| stable cv<0.10 | 3311 | 1296 | 85.73 % | 85.73 % | 84.31 % |
| moderate 0.10-0.30 | 1000 | 481 | 90.02 % | 90.02 % | 89.55 % |
| volatile cv>=0.30 | 289 | 168 | 70.24 % | 70.24 % | 73.45 % |
| unknown | 100 | 100 | 100.00 % | 100.00 % | n/a |

**Latency 귀속 (per-decision)**

| stage | n | 비중 | latency mean ms | MPC rollout CPU ms | verify logits ms | selected tokens mean |
|---|---|---|---|---|---|---|
| draft_verify | 2045 | 43.51 % | 61.265 | 0.202 | 1.076 | 35.529 |
| fallback | 879 | 18.70 % | 58.244 | n/a | n/a | 20.528 |
| queue_serve | 1776 | 37.79 % | 1.776 | n/a | n/a | 0.000 |

전체 decision latency 합 179639 ms 중 MPC brute-force rollout CPU 시간은 413 ms (**0.23 %**), throughput predictor까지 포함해도 0.48 %.

