### v_hybrid_k5_f5_cons_reseed — per-decision post-hoc analysis

`results/soyun/serve_gate_20260909/v_hybrid_k5_f5_cons_reseed/decisions.jsonl` — 4700 decisions over 100 traces; 1788 draft+verify steps, 2750 steps where the LLM actually produced an action.

| 지표 | 정의 | 값 | 분모 |
|---|---|---|---|
| 1. MPC draft 1-step 일치율 | `mpc_draft_actions[0] == llm_target_action` | 80.70 % | 1788 |
| 2. 직전 행동 반복 drafter (가상) | `last_action == llm_action` | 87.78 % | 2750 |
| 2b. 동일 기준(verify step만) | `last_action == llm_target_action` | 87.36 % | 1788 |
| 3. LLM 행동 자기상관 (인접 t) | `llm_action(t) == llm_action(t-1)` | 87.52 % | 1907 |
| 3b. LLM 호출 순서 기준 | 직전 LLM 호출의 행동과 비교 | 83.40 % | 2650 |

**Draft 위치별 일치율 (k=5)**

| draft position | n | MPC 일치율 | repeat-last 일치율 |
|---|---|---|---|
| 0 | 1788 | 80.70 % | 87.36 % |
| 1 | 1749 | 79.36 % | 81.25 % |
| 2 | 1712 | 77.51 % | 77.63 % |
| 3 | 1669 | 74.48 % | 76.15 % |
| 4 | 1627 | 70.74 % | 73.20 % |

accepted-prefix 길이 평균 — MPC **3.100** / repeat-last **3.302** (최대 5). MPC prefix 분포 {'0': 345, '1': 205, '2': 160, '3': 120, '4': 132, '5': 826}, repeat-last {'0': 226, '1': 258, '2': 176, '3': 113, '4': 120, '5': 895}.

**buffer 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| <5s | 113 | 108 | 42.59 % | 97.22 % | 45.45 % |
| 5-10s | 252 | 113 | 90.27 % | 91.15 % | 88.79 % |
| 10-20s | 673 | 188 | 89.36 % | 89.36 % | 88.57 % |
| >=20s | 3662 | 1379 | 81.73 % | 86.00 % | 87.59 % |

**throughput 안정성(최근 6 관측 CV) 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| stable cv<0.10 | 3322 | 1029 | 86.98 % | 87.37 % | 88.16 % |
| moderate 0.10-0.30 | 991 | 474 | 88.61 % | 88.40 % | 90.23 % |
| volatile cv>=0.30 | 287 | 185 | 45.41 % | 77.84 % | 77.90 % |
| unknown | 100 | 100 | 44.00 % | 100.00 % | n/a |

**Latency 귀속 (per-decision)**

| stage | n | 비중 | latency mean ms | MPC rollout CPU ms | verify logits ms | selected tokens mean |
|---|---|---|---|---|---|---|
| draft_verify | 1788 | 38.04 % | 101.515 | 0.711 | 1.665 | 162.662 |
| fallback | 963 | 20.49 % | 84.604 | n/a | n/a | 149.007 |
| queue_serve | 1949 | 41.47 % | 1.868 | n/a | n/a | 0.000 |

전체 decision latency 합 266623 ms 중 MPC brute-force rollout CPU 시간은 1270 ms (**0.48 %**), throughput predictor까지 포함해도 0.65 %.

