### g_repeat_k3_f8 — per-decision post-hoc analysis

`results/soyun/serve_gate_20260909/g_repeat_k3_f8/decisions.jsonl` — 4700 decisions over 100 traces; 2069 draft+verify steps, 3062 steps where the LLM actually produced an action.

| 지표 | 정의 | 값 | 분모 |
|---|---|---|---|
| 1. MPC draft 1-step 일치율 | `mpc_draft_actions[0] == llm_target_action` | 88.79 % | 2069 |
| 2. 직전 행동 반복 drafter (가상) | `last_action == llm_action` | 89.22 % | 3062 |
| 2b. 동일 기준(verify step만) | `last_action == llm_target_action` | 88.79 % | 2069 |
| 3. LLM 행동 자기상관 (인접 t) | `llm_action(t) == llm_action(t-1)` | 88.56 % | 2019 |
| 3b. LLM 호출 순서 기준 | 직전 LLM 호출의 행동과 비교 | 85.21 % | 2962 |

**Draft 위치별 일치율 (k=3)**

| draft position | n | MPC 일치율 | repeat-last 일치율 |
|---|---|---|---|
| 0 | 2069 | 88.79 % | 88.79 % |
| 1 | 2013 | 83.41 % | 83.41 % |
| 2 | 1980 | 83.64 % | 83.64 % |

accepted-prefix 길이 평균 — MPC **2.316** / repeat-last **2.316** (최대 3). MPC prefix 분포 {'0': 232, '1': 280, '2': 160, '3': 1397}, repeat-last {'0': 232, '1': 280, '2': 160, '3': 1397}.

**buffer 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| <5s | 123 | 115 | 93.91 % | 93.91 % | 56.52 % |
| 5-10s | 241 | 91 | 94.51 % | 94.51 % | 94.66 % |
| 10-20s | 644 | 262 | 90.08 % | 90.08 % | 87.15 % |
| >=20s | 3692 | 1601 | 87.88 % | 87.88 % | 88.45 % |

**throughput 안정성(최근 6 관측 CV) 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| stable cv<0.10 | 3347 | 1340 | 88.73 % | 88.73 % | 89.14 % |
| moderate 0.10-0.30 | 952 | 463 | 92.01 % | 92.01 % | 92.07 % |
| volatile cv>=0.30 | 301 | 166 | 73.49 % | 73.49 % | 77.03 % |
| unknown | 100 | 100 | 100.00 % | 100.00 % | n/a |

**Latency 귀속 (per-decision)**

| stage | n | 비중 | latency mean ms | MPC rollout CPU ms | verify logits ms | selected tokens mean |
|---|---|---|---|---|---|---|
| draft_verify | 2069 | 44.02 % | 83.524 | 0.209 | 1.061 | 146.436 |
| fallback | 993 | 21.13 % | 75.861 | n/a | n/a | 136.716 |
| queue_serve | 1638 | 34.85 % | 1.828 | n/a | n/a | 0.000 |

전체 decision latency 합 251137 ms 중 MPC brute-force rollout CPU 시간은 433 ms (**0.17 %**), throughput predictor까지 포함해도 0.35 %.

