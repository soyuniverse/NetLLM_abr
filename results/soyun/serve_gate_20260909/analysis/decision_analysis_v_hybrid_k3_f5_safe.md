### v_hybrid_k3_f5_safe — per-decision post-hoc analysis

`results/soyun/serve_gate_20260909/v_hybrid_k3_f5_safe/decisions.jsonl` — 4583 decisions over 100 traces; 2009 draft+verify steps, 2857 steps where the LLM actually produced an action.

| 지표 | 정의 | 값 | 분모 |
|---|---|---|---|
| 1. MPC draft 1-step 일치율 | `mpc_draft_actions[0] == llm_target_action` | 84.97 % | 2009 |
| 2. 직전 행동 반복 drafter (가상) | `last_action == llm_action` | 87.47 % | 2857 |
| 2b. 동일 기준(verify step만) | `last_action == llm_target_action` | 87.46 % | 2009 |
| 3. LLM 행동 자기상관 (인접 t) | `llm_action(t) == llm_action(t-1)` | 86.01 % | 1773 |
| 3b. LLM 호출 순서 기준 | 직전 LLM 호출의 행동과 비교 | 83.39 % | 2757 |

**Draft 위치별 일치율 (k=3)**

| draft position | n | MPC 일치율 | repeat-last 일치율 |
|---|---|---|---|
| 0 | 2009 | 84.97 % | 87.46 % |
| 1 | 1962 | 82.26 % | 83.18 % |
| 2 | 1921 | 79.70 % | 80.37 % |

accepted-prefix 길이 평균 — MPC **2.224** / repeat-last **2.274** (최대 3). MPC prefix 분포 {'0': 302, '1': 246, '2': 160, '3': 1301}, repeat-last {'0': 252, '1': 268, '2': 166, '3': 1323}.

**buffer 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| 5-10s | 241 | 134 | 94.78 % | 94.78 % | 71.88 % |
| 10-20s | 620 | 252 | 85.32 % | 86.11 % | 80.31 % |
| >=20s | 3722 | 1623 | 84.10 % | 87.06 % | 87.02 % |

**throughput 안정성(최근 6 관측 CV) 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| stable cv<0.10 | 3307 | 1330 | 88.95 % | 88.95 % | 87.34 % |
| moderate 0.10-0.30 | 1008 | 500 | 88.20 % | 88.20 % | 88.19 % |
| volatile cv>=0.30 | 268 | 179 | 46.37 % | 74.30 % | 75.10 % |

**Latency 귀속 (per-decision)**

| stage | n | 비중 | latency mean ms | MPC rollout CPU ms | verify logits ms | selected tokens mean |
|---|---|---|---|---|---|---|
| draft_verify | 2009 | 43.84 % | 83.852 | 0.244 | 1.067 | 150.973 |
| fallback | 848 | 18.50 % | 77.065 | n/a | n/a | 150.792 |
| queue_serve | 1726 | 37.66 % | 1.831 | n/a | n/a | 0.000 |

전체 decision latency 합 236969 ms 중 MPC brute-force rollout CPU 시간은 491 ms (**0.21 %**), throughput predictor까지 포함해도 0.40 %.

