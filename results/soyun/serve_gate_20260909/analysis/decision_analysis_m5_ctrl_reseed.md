### m5_ctrl_reseed — per-decision post-hoc analysis

`results/soyun/serve_gate_20260909/m5_ctrl_reseed/decisions.jsonl` — 4700 decisions over 100 traces; 1786 draft+verify steps, 2746 steps where the LLM actually produced an action.

| 지표 | 정의 | 값 | 분모 |
|---|---|---|---|
| 1. MPC draft 1-step 일치율 | `mpc_draft_actions[0] == llm_target_action` | 80.74 % | 1786 |
| 2. 직전 행동 반복 drafter (가상) | `last_action == llm_action` | 87.80 % | 2746 |
| 2b. 동일 기준(verify step만) | `last_action == llm_target_action` | 87.40 % | 1786 |
| 3. LLM 행동 자기상관 (인접 t) | `llm_action(t) == llm_action(t-1)` | 87.49 % | 1903 |
| 3b. LLM 호출 순서 기준 | 직전 LLM 호출의 행동과 비교 | 83.33 % | 2646 |

**Draft 위치별 일치율 (k=5)**

| draft position | n | MPC 일치율 | repeat-last 일치율 |
|---|---|---|---|
| 0 | 1786 | 80.74 % | 87.40 % |
| 1 | 1748 | 79.23 % | 81.12 % |
| 2 | 1710 | 77.49 % | 77.60 % |
| 3 | 1667 | 74.45 % | 76.12 % |
| 4 | 1625 | 70.77 % | 73.23 % |

accepted-prefix 길이 평균 — MPC **3.100** / repeat-last **3.302** (최대 5). MPC prefix 분포 {'0': 344, '1': 207, '2': 159, '3': 119, '4': 131, '5': 826}, repeat-last {'0': 225, '1': 260, '2': 175, '3': 112, '4': 119, '5': 895}.

**buffer 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| <5s | 113 | 108 | 42.59 % | 97.22 % | 45.45 % |
| 5-10s | 252 | 111 | 90.09 % | 90.99 % | 88.57 % |
| 10-20s | 673 | 189 | 89.95 % | 89.95 % | 88.52 % |
| >=20s | 3662 | 1378 | 81.71 % | 85.99 % | 87.58 % |

**throughput 안정성(최근 6 관측 CV) 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| stable cv<0.10 | 3322 | 1029 | 87.07 % | 87.46 % | 88.16 % |
| moderate 0.10-0.30 | 991 | 472 | 88.56 % | 88.35 % | 90.18 % |
| volatile cv>=0.30 | 287 | 185 | 45.41 % | 77.84 % | 77.90 % |
| unknown | 100 | 100 | 44.00 % | 100.00 % | n/a |

**Latency 귀속 (per-decision)**

| stage | n | 비중 | latency mean ms | MPC rollout CPU ms | verify logits ms | selected tokens mean |
|---|---|---|---|---|---|---|
| draft_verify | 1786 | 38.00 % | 93.074 | 0.703 | 1.655 | 162.746 |
| fallback | 960 | 20.43 % | 77.545 | n/a | n/a | 149.317 |
| queue_serve | 1954 | 41.57 % | 1.780 | n/a | n/a | 0.000 |

전체 decision latency 합 244152 ms 중 MPC brute-force rollout CPU 시간은 1255 ms (**0.51 %**), throughput predictor까지 포함해도 0.70 %.

