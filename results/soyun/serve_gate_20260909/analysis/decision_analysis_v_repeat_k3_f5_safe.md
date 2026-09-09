### v_repeat_k3_f5_safe — per-decision post-hoc analysis

`results/soyun/serve_gate_20260909/v_repeat_k3_f5_safe/decisions.jsonl` — 4584 decisions over 100 traces; 1970 draft+verify steps, 2843 steps where the LLM actually produced an action.

| 지표 | 정의 | 값 | 분모 |
|---|---|---|---|
| 1. MPC draft 1-step 일치율 | `mpc_draft_actions[0] == llm_target_action` | 88.32 % | 1970 |
| 2. 직전 행동 반복 drafter (가상) | `last_action == llm_action` | 87.86 % | 2843 |
| 2b. 동일 기준(verify step만) | `last_action == llm_target_action` | 88.32 % | 1970 |
| 3. LLM 행동 자기상관 (인접 t) | `llm_action(t) == llm_action(t-1)` | 86.35 % | 1758 |
| 3b. LLM 호출 순서 기준 | 직전 LLM 호출의 행동과 비교 | 83.38 % | 2743 |

**Draft 위치별 일치율 (k=3)**

| draft position | n | MPC 일치율 | repeat-last 일치율 |
|---|---|---|---|
| 0 | 1970 | 88.32 % | 88.32 % |
| 1 | 1923 | 85.80 % | 85.80 % |
| 2 | 1889 | 82.80 % | 82.80 % |

accepted-prefix 길이 평균 — MPC **2.317** / repeat-last **2.317** (최대 3). MPC prefix 분포 {'0': 230, '1': 234, '2': 188, '3': 1318}, repeat-last {'0': 230, '1': 234, '2': 188, '3': 1318}.

**buffer 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| 5-10s | 241 | 136 | 94.12 % | 94.12 % | 75.00 % |
| 10-20s | 655 | 259 | 89.58 % | 89.58 % | 84.69 % |
| >=20s | 3688 | 1575 | 87.62 % | 87.62 % | 86.82 % |

**throughput 안정성(최근 6 관측 CV) 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| stable cv<0.10 | 3320 | 1343 | 89.13 % | 89.13 % | 86.39 % |
| moderate 0.10-0.30 | 992 | 476 | 88.66 % | 88.66 % | 89.08 % |
| volatile cv>=0.30 | 272 | 151 | 80.13 % | 80.13 % | 77.73 % |

**Latency 귀속 (per-decision)**

| stage | n | 비중 | latency mean ms | MPC rollout CPU ms | verify logits ms | selected tokens mean |
|---|---|---|---|---|---|---|
| draft_verify | 1970 | 42.98 % | 83.533 | 0.213 | 1.059 | 151.074 |
| fallback | 873 | 19.04 % | 75.777 | n/a | n/a | 149.378 |
| queue_serve | 1741 | 37.98 % | 1.803 | n/a | n/a | 0.000 |

전체 decision latency 합 233853 ms 중 MPC brute-force rollout CPU 시간은 420 ms (**0.18 %**), throughput predictor까지 포함해도 0.37 %.

