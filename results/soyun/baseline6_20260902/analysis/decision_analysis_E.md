### E — per-decision post-hoc analysis

`results/soyun/baseline6_20260902/e_speculative/decisions.jsonl` — 4700 decisions over 100 traces; 4137 draft+verify steps, 4405 steps where the LLM actually produced an action.

| 지표 | 정의 | 값 | 분모 |
|---|---|---|---|
| 1. MPC draft 1-step 일치율 | `mpc_draft_actions[0] == llm_target_action` | 12.84 % | 4137 |
| 2. 직전 행동 반복 drafter (가상) | `last_action == llm_action` | 92.85 % | 4405 |
| 2b. 동일 기준(verify step만) | `last_action == llm_target_action` | 93.30 % | 4137 |
| 3. LLM 행동 자기상관 (인접 t) | `llm_action(t) == llm_action(t-1)` | 92.46 % | 4056 |
| 3b. LLM 호출 순서 기준 | 직전 LLM 호출의 행동과 비교 | 92.38 % | 4305 |

**Draft 위치별 일치율 (k=3)**

| draft position | n | MPC 일치율 | repeat-last 일치율 |
|---|---|---|---|
| 0 | 4137 | 12.84 % | 93.30 % |
| 1 | 4044 | 8.78 % | 34.97 % |
| 2 | 3964 | 14.86 % | 22.23 % |

accepted-prefix 길이 평균 — MPC **0.180** / repeat-last **1.457** (최대 3). MPC prefix 분포 {'0': 3606, '1': 375, '2': 97, '3': 59}, repeat-last {'0': 277, '1': 2469, '2': 616, '3': 775}.

**buffer 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| <5s | 102 | 100 | 43.00 % | 100.00 % | n/a |
| 5-10s | 235 | 141 | 20.57 % | 97.16 % | 93.33 % |
| 10-20s | 593 | 472 | 19.49 % | 97.03 % | 95.79 % |
| >=20s | 3770 | 3424 | 10.72 % | 92.44 % | 91.97 % |

**throughput 안정성(최근 6 관측 CV) 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| stable cv<0.10 | 3344 | 2989 | 9.33 % | 93.34 % | 92.85 % |
| moderate 0.10-0.30 | 961 | 835 | 14.61 % | 94.49 % | 93.51 % |
| volatile cv>=0.30 | 295 | 213 | 40.85 % | 84.98 % | 85.17 % |
| unknown | 100 | 100 | 43.00 % | 100.00 % | n/a |

**Latency 귀속 (per-decision)**

| stage | n | 비중 | latency mean ms | MPC rollout CPU ms | verify logits ms | selected tokens mean |
|---|---|---|---|---|---|---|
| draft_verify | 4137 | 88.02 % | 58.808 | 0.164 | 0.032 | 148.662 |
| fallback | 268 | 5.70 % | 51.314 | n/a | n/a | 139.060 |
| queue_serve | 295 | 6.28 % | 0.832 | n/a | n/a | 0.000 |

전체 decision latency 합 257287 ms 중 MPC brute-force rollout CPU 시간은 679 ms (**0.26 %**), throughput predictor까지 포함해도 0.35 %.

