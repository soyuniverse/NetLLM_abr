### v_hybrid_k5_f5_fb_s2 — per-decision post-hoc analysis

`results/soyun/serve_gate_20260909/v_hybrid_k5_f5_fb_s2/decisions.jsonl` — 4700 decisions over 100 traces; 1778 draft+verify steps, 2746 steps where the LLM actually produced an action.

| 지표 | 정의 | 값 | 분모 |
|---|---|---|---|
| 1. MPC draft 1-step 일치율 | `mpc_draft_actions[0] == llm_target_action` | 82.51 % | 1778 |
| 2. 직전 행동 반복 drafter (가상) | `last_action == llm_action` | 88.42 % | 2746 |
| 2b. 동일 기준(verify step만) | `last_action == llm_target_action` | 87.85 % | 1778 |
| 3. LLM 행동 자기상관 (인접 t) | `llm_action(t) == llm_action(t-1)` | 87.90 % | 1901 |
| 3b. LLM 호출 순서 기준 | 직전 LLM 호출의 행동과 비교 | 83.94 % | 2646 |

**Draft 위치별 일치율 (k=5)**

| draft position | n | MPC 일치율 | repeat-last 일치율 |
|---|---|---|---|
| 0 | 1778 | 82.51 % | 87.85 % |
| 1 | 1732 | 79.56 % | 82.97 % |
| 2 | 1697 | 78.20 % | 80.14 % |
| 3 | 1648 | 74.70 % | 76.76 % |
| 4 | 1610 | 72.11 % | 75.47 % |

accepted-prefix 길이 평균 — MPC **3.138** / repeat-last **3.343** (최대 5). MPC prefix 분포 {'0': 311, '1': 218, '2': 158, '3': 143, '4': 124, '5': 824}, repeat-last {'0': 216, '1': 233, '2': 179, '3': 140, '4': 118, '5': 892}.

**buffer 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| <5s | 107 | 104 | 45.19 % | 97.12 % | 40.00 % |
| 5-10s | 236 | 101 | 94.06 % | 94.06 % | 90.43 % |
| 10-20s | 648 | 180 | 88.33 % | 88.89 % | 89.42 % |
| >=20s | 3709 | 1393 | 83.70 % | 86.58 % | 87.72 % |

**throughput 안정성(최근 6 관측 CV) 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| stable cv<0.10 | 3303 | 1021 | 88.34 % | 88.25 % | 89.47 % |
| moderate 0.10-0.30 | 1023 | 487 | 88.30 % | 88.30 % | 89.44 % |
| volatile cv>=0.30 | 274 | 170 | 53.53 % | 77.06 % | 78.08 % |
| unknown | 100 | 100 | 44.00 % | 100.00 % | n/a |

**Latency 귀속 (per-decision)**

| stage | n | 비중 | latency mean ms | MPC rollout CPU ms | verify logits ms | selected tokens mean |
|---|---|---|---|---|---|---|
| draft_verify | 1778 | 37.83 % | 90.517 | 0.681 | 1.733 | 161.786 |
| fallback | 968 | 20.60 % | 75.465 | n/a | n/a | 149.182 |
| queue_serve | 1954 | 41.57 % | 1.913 | n/a | n/a | 0.000 |

전체 decision latency 합 237727 ms 중 MPC brute-force rollout CPU 시간은 1211 ms (**0.51 %**), throughput predictor까지 포함해도 0.71 %.

