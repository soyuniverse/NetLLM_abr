### g_hybrid_k3_f5 — per-decision post-hoc analysis

`results/soyun/serve_gate_20260909/g_hybrid_k3_f5/decisions.jsonl` — 4700 decisions over 100 traces; 2100 draft+verify steps, 2959 steps where the LLM actually produced an action.

| 지표 | 정의 | 값 | 분모 |
|---|---|---|---|
| 1. MPC draft 1-step 일치율 | `mpc_draft_actions[0] == llm_target_action` | 82.95 % | 2100 |
| 2. 직전 행동 반복 drafter (가상) | `last_action == llm_action` | 88.37 % | 2959 |
| 2b. 동일 기준(verify step만) | `last_action == llm_target_action` | 88.62 % | 2100 |
| 3. LLM 행동 자기상관 (인접 t) | `llm_action(t) == llm_action(t-1)` | 86.37 % | 1864 |
| 3b. LLM 호출 순서 기준 | 직전 LLM 호출의 행동과 비교 | 84.51 % | 2859 |

**Draft 위치별 일치율 (k=3)**

| draft position | n | MPC 일치율 | repeat-last 일치율 |
|---|---|---|---|
| 0 | 2100 | 82.95 % | 88.62 % |
| 1 | 2046 | 78.45 % | 82.65 % |
| 2 | 2005 | 76.51 % | 79.45 % |

accepted-prefix 길이 평균 — MPC **2.144** / repeat-last **2.283** (최대 3). MPC prefix 분포 {'0': 358, '1': 273, '2': 178, '3': 1291}, repeat-last {'0': 239, '1': 292, '2': 204, '3': 1365}.

**buffer 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| <5s | 128 | 117 | 45.30 % | 92.31 % | 51.85 % |
| 5-10s | 244 | 117 | 96.58 % | 96.58 % | 92.31 % |
| 10-20s | 600 | 226 | 91.59 % | 92.48 % | 88.83 % |
| >=20s | 3728 | 1640 | 83.48 % | 87.26 % | 86.29 % |

**throughput 안정성(최근 6 관측 CV) 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| stable cv<0.10 | 3320 | 1322 | 89.41 % | 89.71 % | 86.88 % |
| moderate 0.10-0.30 | 988 | 492 | 87.80 % | 87.80 % | 89.19 % |
| volatile cv>=0.30 | 292 | 186 | 45.70 % | 76.88 % | 77.06 % |
| unknown | 100 | 100 | 43.00 % | 100.00 % | n/a |

**Latency 귀속 (per-decision)**

| stage | n | 비중 | latency mean ms | MPC rollout CPU ms | verify logits ms | selected tokens mean |
|---|---|---|---|---|---|---|
| draft_verify | 2100 | 44.68 % | 82.322 | 0.249 | 1.043 | 146.290 |
| fallback | 859 | 18.28 % | 76.105 | n/a | n/a | 148.225 |
| queue_serve | 1741 | 37.04 % | 1.810 | n/a | n/a | 0.000 |

전체 decision latency 합 241403 ms 중 MPC brute-force rollout CPU 시간은 523 ms (**0.22 %**), throughput predictor까지 포함해도 0.41 %.

