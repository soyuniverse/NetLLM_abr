### m2_repeat_k3 — per-decision post-hoc analysis

`results/soyun/drafter_ab_20260908/m2_repeat_k3/decisions.jsonl` — 4700 decisions over 100 traces; 2025 draft+verify steps, 2925 steps where the LLM actually produced an action.

| 지표 | 정의 | 값 | 분모 |
|---|---|---|---|
| 1. MPC draft 1-step 일치율 | `mpc_draft_actions[0] == llm_target_action` | 87.95 % | 2025 |
| 2. 직전 행동 반복 drafter (가상) | `last_action == llm_action` | 87.97 % | 2925 |
| 2b. 동일 기준(verify step만) | `last_action == llm_target_action` | 87.95 % | 2025 |
| 3. LLM 행동 자기상관 (인접 t) | `llm_action(t) == llm_action(t-1)` | 86.09 % | 1812 |
| 3b. LLM 호출 순서 기준 | 직전 LLM 호출의 행동과 비교 | 83.12 % | 2825 |

**Draft 위치별 일치율 (k=3)**

| draft position | n | MPC 일치율 | repeat-last 일치율 |
|---|---|---|---|
| 0 | 2025 | 87.95 % | 87.95 % |
| 1 | 1981 | 84.70 % | 84.70 % |
| 2 | 1937 | 82.91 % | 82.91 % |

accepted-prefix 길이 평균 — MPC **2.301** / repeat-last **2.301** (최대 3). MPC prefix 분포 {'0': 244, '1': 244, '2': 196, '3': 1341}, repeat-last {'0': 244, '1': 244, '2': 196, '3': 1341}.

**buffer 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| <5s | 115 | 106 | 97.17 % | 97.17 % | 37.50 % |
| 5-10s | 251 | 51 | 90.20 % | 90.20 % | 82.61 % |
| 10-20s | 634 | 272 | 86.76 % | 86.76 % | 84.21 % |
| >=20s | 3700 | 1596 | 87.47 % | 87.47 % | 86.70 % |

**throughput 안정성(최근 6 관측 CV) 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| stable cv<0.10 | 3307 | 1269 | 87.79 % | 87.79 % | 85.25 % |
| moderate 0.10-0.30 | 1009 | 496 | 89.11 % | 89.11 % | 89.96 % |
| volatile cv>=0.30 | 284 | 160 | 78.12 % | 78.12 % | 76.95 % |
| unknown | 100 | 100 | 100.00 % | 100.00 % | n/a |

**Latency 귀속 (per-decision)**

| stage | n | 비중 | latency mean ms | MPC rollout CPU ms | verify logits ms | selected tokens mean |
|---|---|---|---|---|---|---|
| draft_verify | 2025 | 43.09 % | 90.910 | 0.202 | 1.044 | 148.709 |
| fallback | 900 | 19.15 % | 87.886 | n/a | n/a | 148.618 |
| queue_serve | 1775 | 37.77 % | 1.766 | n/a | n/a | 0.000 |

전체 decision latency 합 266325 ms 중 MPC brute-force rollout CPU 시간은 408 ms (**0.15 %**), throughput predictor까지 포함해도 0.32 %.

