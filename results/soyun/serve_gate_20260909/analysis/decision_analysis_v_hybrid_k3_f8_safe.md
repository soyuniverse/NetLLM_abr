### v_hybrid_k3_f8_safe — per-decision post-hoc analysis

`results/soyun/serve_gate_20260909/v_hybrid_k3_f8_safe/decisions.jsonl` — 4448 decisions over 100 traces; 1959 draft+verify steps, 2788 steps where the LLM actually produced an action.

| 지표 | 정의 | 값 | 분모 |
|---|---|---|---|
| 1. MPC draft 1-step 일치율 | `mpc_draft_actions[0] == llm_target_action` | 84.58 % | 1959 |
| 2. 직전 행동 반복 drafter (가상) | `last_action == llm_action` | 88.20 % | 2788 |
| 2b. 동일 기준(verify step만) | `last_action == llm_target_action` | 88.62 % | 1959 |
| 3. LLM 행동 자기상관 (인접 t) | `llm_action(t) == llm_action(t-1)` | 86.88 % | 1738 |
| 3b. LLM 호출 순서 기준 | 직전 LLM 호출의 행동과 비교 | 84.41 % | 2688 |

**Draft 위치별 일치율 (k=3)**

| draft position | n | MPC 일치율 | repeat-last 일치율 |
|---|---|---|---|
| 0 | 1959 | 84.58 % | 88.62 % |
| 1 | 1918 | 81.80 % | 82.33 % |
| 2 | 1873 | 79.77 % | 80.19 % |

accepted-prefix 길이 평균 — MPC **2.222** / repeat-last **2.288** (최대 3). MPC prefix 분포 {'0': 302, '1': 222, '2': 175, '3': 1260}, repeat-last {'0': 223, '1': 271, '2': 183, '3': 1282}.

**buffer 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| 5-10s | 95 | 75 | 97.33 % | 96.00 % | 50.00 % |
| 10-20s | 624 | 248 | 86.69 % | 89.52 % | 81.98 % |
| >=20s | 3729 | 1636 | 83.68 % | 88.14 % | 87.47 % |

**throughput 안정성(최근 6 관측 CV) 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| stable cv<0.10 | 3209 | 1292 | 89.47 % | 89.47 % | 87.92 % |
| moderate 0.10-0.30 | 955 | 477 | 89.52 % | 89.52 % | 88.09 % |
| volatile cv>=0.30 | 284 | 190 | 38.95 % | 80.53 % | 80.53 % |

**Latency 귀속 (per-decision)**

| stage | n | 비중 | latency mean ms | MPC rollout CPU ms | verify logits ms | selected tokens mean |
|---|---|---|---|---|---|---|
| draft_verify | 1959 | 44.04 % | 84.807 | 0.244 | 1.084 | 153.642 |
| fallback | 829 | 18.64 % | 78.110 | n/a | n/a | 153.036 |
| queue_serve | 1660 | 37.32 % | 1.846 | n/a | n/a | 0.000 |

전체 decision latency 합 233954 ms 중 MPC brute-force rollout CPU 시간은 478 ms (**0.20 %**), throughput predictor까지 포함해도 0.39 %.

