### m3_ctrl — per-decision post-hoc analysis

`results/soyun/serve_gate_20260909/m3_ctrl/decisions.jsonl` — 4700 decisions over 100 traces; 2101 draft+verify steps, 2948 steps where the LLM actually produced an action.

| 지표 | 정의 | 값 | 분모 |
|---|---|---|---|
| 1. MPC draft 1-step 일치율 | `mpc_draft_actions[0] == llm_target_action` | 83.15 % | 2101 |
| 2. 직전 행동 반복 drafter (가상) | `last_action == llm_action` | 88.20 % | 2948 |
| 2b. 동일 기준(verify step만) | `last_action == llm_target_action` | 88.91 % | 2101 |
| 3. LLM 행동 자기상관 (인접 t) | `llm_action(t) == llm_action(t-1)` | 86.38 % | 1857 |
| 3b. LLM 호출 순서 기준 | 직전 LLM 호출의 행동과 비교 | 83.74 % | 2848 |

**Draft 위치별 일치율 (k=3)**

| draft position | n | MPC 일치율 | repeat-last 일치율 |
|---|---|---|---|
| 0 | 2101 | 83.15 % | 88.91 % |
| 1 | 2049 | 78.33 % | 82.04 % |
| 2 | 2013 | 76.90 % | 79.19 % |

accepted-prefix 길이 평균 — MPC **2.142** / repeat-last **2.283** (최대 3). MPC prefix 분포 {'0': 354, '1': 276, '2': 189, '3': 1282}, repeat-last {'0': 233, '1': 297, '2': 214, '3': 1357}.

**buffer 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| <5s | 122 | 113 | 43.36 % | 94.69 % | 55.56 % |
| 5-10s | 246 | 118 | 95.76 % | 95.76 % | 92.86 % |
| 10-20s | 659 | 257 | 87.94 % | 88.33 % | 87.91 % |
| >=20s | 3673 | 1613 | 84.25 % | 88.10 % | 86.11 % |

**throughput 안정성(최근 6 관측 CV) 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| stable cv<0.10 | 3319 | 1316 | 89.82 % | 90.05 % | 87.56 % |
| moderate 0.10-0.30 | 1004 | 504 | 87.90 % | 88.10 % | 88.32 % |
| volatile cv>=0.30 | 277 | 181 | 43.65 % | 76.80 % | 76.98 % |
| unknown | 100 | 100 | 43.00 % | 100.00 % | n/a |

**Latency 귀속 (per-decision)**

| stage | n | 비중 | latency mean ms | MPC rollout CPU ms | verify logits ms | selected tokens mean |
|---|---|---|---|---|---|---|
| draft_verify | 2101 | 44.70 % | 78.432 | 0.254 | 1.083 | 146.521 |
| fallback | 847 | 18.02 % | 69.957 | n/a | n/a | 148.979 |
| queue_serve | 1752 | 37.28 % | 1.832 | n/a | n/a | 0.000 |

전체 decision latency 합 227250 ms 중 MPC brute-force rollout CPU 시간은 533 ms (**0.23 %**), throughput predictor까지 포함해도 0.44 %.

