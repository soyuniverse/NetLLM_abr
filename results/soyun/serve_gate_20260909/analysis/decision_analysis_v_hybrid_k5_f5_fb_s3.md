### v_hybrid_k5_f5_fb_s3 — per-decision post-hoc analysis

`results/soyun/serve_gate_20260909/v_hybrid_k5_f5_fb_s3/decisions.jsonl` — 4700 decisions over 100 traces; 1765 draft+verify steps, 2728 steps where the LLM actually produced an action.

| 지표 | 정의 | 값 | 분모 |
|---|---|---|---|
| 1. MPC draft 1-step 일치율 | `mpc_draft_actions[0] == llm_target_action` | 83.29 % | 1765 |
| 2. 직전 행동 반복 drafter (가상) | `last_action == llm_action` | 88.42 % | 2728 |
| 2b. 동일 기준(verify step만) | `last_action == llm_target_action` | 88.27 % | 1765 |
| 3. LLM 행동 자기상관 (인접 t) | `llm_action(t) == llm_action(t-1)` | 88.03 % | 1871 |
| 3b. LLM 호출 순서 기준 | 직전 LLM 호출의 행동과 비교 | 83.90 % | 2628 |

**Draft 위치별 일치율 (k=5)**

| draft position | n | MPC 일치율 | repeat-last 일치율 |
|---|---|---|---|
| 0 | 1765 | 83.29 % | 88.27 % |
| 1 | 1724 | 78.83 % | 81.96 % |
| 2 | 1686 | 77.16 % | 78.05 % |
| 3 | 1646 | 75.64 % | 77.46 % |
| 4 | 1596 | 69.99 % | 74.00 % |

accepted-prefix 길이 평균 — MPC **3.142** / repeat-last **3.332** (최대 5). MPC prefix 분포 {'0': 295, '1': 236, '2': 167, '3': 115, '4': 130, '5': 822}, repeat-last {'0': 207, '1': 251, '2': 187, '3': 111, '4': 122, '5': 887}.

**buffer 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| <5s | 112 | 104 | 45.19 % | 97.12 % | 45.45 % |
| 5-10s | 248 | 110 | 97.27 % | 94.55 % | 90.29 % |
| 10-20s | 692 | 204 | 87.75 % | 88.73 % | 88.94 % |
| >=20s | 3648 | 1347 | 84.41 % | 87.01 % | 88.05 % |

**throughput 안정성(최근 6 관측 CV) 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| stable cv<0.10 | 3327 | 1027 | 88.80 % | 88.70 % | 88.69 % |
| moderate 0.10-0.30 | 986 | 470 | 89.79 % | 89.79 % | 91.42 % |
| volatile cv>=0.30 | 287 | 168 | 54.76 % | 74.40 % | 76.56 % |
| unknown | 100 | 100 | 44.00 % | 100.00 % | n/a |

**Latency 귀속 (per-decision)**

| stage | n | 비중 | latency mean ms | MPC rollout CPU ms | verify logits ms | selected tokens mean |
|---|---|---|---|---|---|---|
| draft_verify | 1765 | 37.55 % | 100.387 | 0.669 | 1.687 | 161.600 |
| fallback | 963 | 20.49 % | 84.141 | n/a | n/a | 148.350 |
| queue_serve | 1972 | 41.96 % | 1.884 | n/a | n/a | 0.000 |

전체 decision latency 합 261927 ms 중 MPC brute-force rollout CPU 시간은 1180 ms (**0.45 %**), throughput predictor까지 포함해도 0.63 %.

