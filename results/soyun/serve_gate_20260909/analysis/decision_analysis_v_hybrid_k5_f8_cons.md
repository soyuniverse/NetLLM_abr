### v_hybrid_k5_f8_cons — per-decision post-hoc analysis

`results/soyun/serve_gate_20260909/v_hybrid_k5_f8_cons/decisions.jsonl` — 4700 decisions over 100 traces; 1792 draft+verify steps, 2755 steps where the LLM actually produced an action.

| 지표 | 정의 | 값 | 분모 |
|---|---|---|---|
| 1. MPC draft 1-step 일치율 | `mpc_draft_actions[0] == llm_target_action` | 82.65 % | 1792 |
| 2. 직전 행동 반복 drafter (가상) | `last_action == llm_action` | 87.80 % | 2755 |
| 2b. 동일 기준(verify step만) | `last_action == llm_target_action` | 87.44 % | 1792 |
| 3. LLM 행동 자기상관 (인접 t) | `llm_action(t) == llm_action(t-1)` | 86.77 % | 1905 |
| 3b. LLM 호출 순서 기준 | 직전 LLM 호출의 행동과 비교 | 83.13 % | 2655 |

**Draft 위치별 일치율 (k=5)**

| draft position | n | MPC 일치율 | repeat-last 일치율 |
|---|---|---|---|
| 0 | 1792 | 82.65 % | 87.44 % |
| 1 | 1751 | 78.07 % | 81.04 % |
| 2 | 1718 | 77.59 % | 78.52 % |
| 3 | 1679 | 73.44 % | 75.40 % |
| 4 | 1635 | 70.95 % | 75.23 % |

accepted-prefix 길이 평균 — MPC **3.111** / repeat-last **3.300** (최대 5). MPC prefix 분포 {'0': 311, '1': 243, '2': 145, '3': 155, '4': 113, '5': 825}, repeat-last {'0': 225, '1': 251, '2': 175, '3': 144, '4': 104, '5': 893}.

**buffer 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| <5s | 118 | 108 | 46.30 % | 93.52 % | 14.29 % |
| 5-10s | 235 | 117 | 97.44 % | 97.44 % | 94.62 % |
| 10-20s | 646 | 180 | 85.00 % | 86.67 % | 85.78 % |
| >=20s | 3701 | 1387 | 83.92 % | 86.23 % | 87.08 % |

**throughput 안정성(최근 6 관측 CV) 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| stable cv<0.10 | 3316 | 1041 | 88.38 % | 88.28 % | 88.29 % |
| moderate 0.10-0.30 | 1002 | 476 | 88.45 % | 88.03 % | 88.75 % |
| volatile cv>=0.30 | 282 | 175 | 54.86 % | 73.71 % | 76.21 % |
| unknown | 100 | 100 | 44.00 % | 100.00 % | n/a |

**Latency 귀속 (per-decision)**

| stage | n | 비중 | latency mean ms | MPC rollout CPU ms | verify logits ms | selected tokens mean |
|---|---|---|---|---|---|---|
| draft_verify | 1792 | 38.13 % | 94.320 | 0.688 | 1.645 | 161.375 |
| fallback | 1008 | 21.45 % | 75.486 | n/a | n/a | 145.140 |
| queue_serve | 1900 | 40.43 % | 1.861 | n/a | n/a | 0.000 |

전체 decision latency 합 248646 ms 중 MPC brute-force rollout CPU 시간은 1234 ms (**0.50 %**), throughput predictor까지 포함해도 0.68 %.

