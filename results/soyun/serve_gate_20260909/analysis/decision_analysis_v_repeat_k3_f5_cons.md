### v_repeat_k3_f5_cons — per-decision post-hoc analysis

`results/soyun/serve_gate_20260909/v_repeat_k3_f5_cons/decisions.jsonl` — 4700 decisions over 100 traces; 2026 draft+verify steps, 2923 steps where the LLM actually produced an action.

| 지표 | 정의 | 값 | 분모 |
|---|---|---|---|
| 1. MPC draft 1-step 일치율 | `mpc_draft_actions[0] == llm_target_action` | 87.46 % | 2026 |
| 2. 직전 행동 반복 drafter (가상) | `last_action == llm_action` | 87.75 % | 2923 |
| 2b. 동일 기준(verify step만) | `last_action == llm_target_action` | 87.46 % | 2026 |
| 3. LLM 행동 자기상관 (인접 t) | `llm_action(t) == llm_action(t-1)` | 85.51 % | 1808 |
| 3b. LLM 호출 순서 기준 | 직전 LLM 호출의 행동과 비교 | 82.82 % | 2823 |

**Draft 위치별 일치율 (k=3)**

| draft position | n | MPC 일치율 | repeat-last 일치율 |
|---|---|---|---|
| 0 | 2026 | 87.46 % | 87.46 % |
| 1 | 1987 | 84.25 % | 84.25 % |
| 2 | 1941 | 83.36 % | 83.36 % |

accepted-prefix 길이 평균 — MPC **2.291** / repeat-last **2.291** (최대 3). MPC prefix 분포 {'0': 254, '1': 244, '2': 186, '3': 1342}, repeat-last {'0': 254, '1': 244, '2': 186, '3': 1342}.

**buffer 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| <5s | 113 | 105 | 97.14 % | 97.14 % | 37.50 % |
| 5-10s | 256 | 54 | 88.89 % | 88.89 % | 82.98 % |
| 10-20s | 644 | 276 | 86.23 % | 86.23 % | 82.30 % |
| >=20s | 3687 | 1591 | 86.99 % | 86.99 % | 86.27 % |

**throughput 안정성(최근 6 관측 CV) 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| stable cv<0.10 | 3304 | 1269 | 87.71 % | 87.71 % | 84.75 % |
| moderate 0.10-0.30 | 1008 | 495 | 88.08 % | 88.08 % | 89.21 % |
| volatile cv>=0.30 | 288 | 162 | 75.93 % | 75.93 % | 76.69 % |
| unknown | 100 | 100 | 100.00 % | 100.00 % | n/a |

**Latency 귀속 (per-decision)**

| stage | n | 비중 | latency mean ms | MPC rollout CPU ms | verify logits ms | selected tokens mean |
|---|---|---|---|---|---|---|
| draft_verify | 2026 | 43.11 % | 83.522 | 0.211 | 1.096 | 148.549 |
| fallback | 901 | 19.17 % | 75.504 | n/a | n/a | 148.101 |
| queue_serve | 1773 | 37.72 % | 1.894 | n/a | n/a | 0.000 |

전체 decision latency 합 240604 ms 중 MPC brute-force rollout CPU 시간은 427 ms (**0.18 %**), throughput predictor까지 포함해도 0.37 %.

