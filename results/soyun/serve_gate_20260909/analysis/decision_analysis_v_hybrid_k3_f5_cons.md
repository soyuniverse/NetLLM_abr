### v_hybrid_k3_f5_cons — per-decision post-hoc analysis

`results/soyun/serve_gate_20260909/v_hybrid_k3_f5_cons/decisions.jsonl` — 4700 decisions over 100 traces; 2102 draft+verify steps, 2957 steps where the LLM actually produced an action.

| 지표 | 정의 | 값 | 분모 |
|---|---|---|---|
| 1. MPC draft 1-step 일치율 | `mpc_draft_actions[0] == llm_target_action` | 82.78 % | 2102 |
| 2. 직전 행동 반복 drafter (가상) | `last_action == llm_action` | 88.16 % | 2957 |
| 2b. 동일 기준(verify step만) | `last_action == llm_target_action` | 88.39 % | 2102 |
| 3. LLM 행동 자기상관 (인접 t) | `llm_action(t) == llm_action(t-1)` | 86.08 % | 1861 |
| 3b. LLM 호출 순서 기준 | 직전 LLM 호출의 행동과 비교 | 84.25 % | 2857 |

**Draft 위치별 일치율 (k=3)**

| draft position | n | MPC 일치율 | repeat-last 일치율 |
|---|---|---|---|
| 0 | 2102 | 82.78 % | 88.39 % |
| 1 | 2048 | 78.52 % | 82.62 % |
| 2 | 2005 | 76.46 % | 79.40 % |

accepted-prefix 길이 평균 — MPC **2.138** / repeat-last **2.275** (최대 3). MPC prefix 분포 {'0': 362, '1': 272, '2': 182, '3': 1286}, repeat-last {'0': 244, '1': 292, '2': 207, '3': 1359}.

**buffer 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| <5s | 128 | 117 | 45.30 % | 92.31 % | 48.00 % |
| 5-10s | 244 | 117 | 96.58 % | 96.58 % | 92.16 % |
| 10-20s | 591 | 221 | 91.86 % | 92.76 % | 88.89 % |
| >=20s | 3737 | 1647 | 83.24 % | 86.95 % | 85.99 % |

**throughput 안정성(최근 6 관측 CV) 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| stable cv<0.10 | 3322 | 1325 | 89.06 % | 89.36 % | 86.54 % |
| moderate 0.10-0.30 | 989 | 493 | 87.83 % | 87.83 % | 88.90 % |
| volatile cv>=0.30 | 289 | 184 | 45.65 % | 76.63 % | 76.81 % |
| unknown | 100 | 100 | 43.00 % | 100.00 % | n/a |

**Latency 귀속 (per-decision)**

| stage | n | 비중 | latency mean ms | MPC rollout CPU ms | verify logits ms | selected tokens mean |
|---|---|---|---|---|---|---|
| draft_verify | 2102 | 44.72 % | 81.027 | 0.254 | 1.068 | 146.272 |
| fallback | 857 | 18.23 % | 73.906 | n/a | n/a | 148.221 |
| queue_serve | 1741 | 37.04 % | 1.881 | n/a | n/a | 0.000 |

전체 decision latency 합 236931 ms 중 MPC brute-force rollout CPU 시간은 535 ms (**0.23 %**), throughput predictor까지 포함해도 0.42 %.

