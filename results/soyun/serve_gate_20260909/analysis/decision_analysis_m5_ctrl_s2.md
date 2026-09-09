### m5_ctrl_s2 — per-decision post-hoc analysis

`results/soyun/serve_gate_20260909/m5_ctrl_s2/decisions.jsonl` — 4700 decisions over 100 traces; 1771 draft+verify steps, 2721 steps where the LLM actually produced an action.

| 지표 | 정의 | 값 | 분모 |
|---|---|---|---|
| 1. MPC draft 1-step 일치율 | `mpc_draft_actions[0] == llm_target_action` | 82.33 % | 1771 |
| 2. 직전 행동 반복 drafter (가상) | `last_action == llm_action` | 87.76 % | 2721 |
| 2b. 동일 기준(verify step만) | `last_action == llm_target_action` | 87.58 % | 1771 |
| 3. LLM 행동 자기상관 (인접 t) | `llm_action(t) == llm_action(t-1)` | 87.63 % | 1868 |
| 3b. LLM 호출 순서 기준 | 직전 LLM 호출의 행동과 비교 | 83.10 % | 2621 |

**Draft 위치별 일치율 (k=5)**

| draft position | n | MPC 일치율 | repeat-last 일치율 |
|---|---|---|---|
| 0 | 1771 | 82.33 % | 87.58 % |
| 1 | 1733 | 78.42 % | 81.82 % |
| 2 | 1692 | 77.72 % | 79.26 % |
| 3 | 1651 | 74.92 % | 76.98 % |
| 4 | 1612 | 71.28 % | 74.88 % |

accepted-prefix 길이 평균 — MPC **3.095** / repeat-last **3.295** (최대 5). MPC prefix 분포 {'0': 313, '1': 230, '2': 162, '3': 131, '4': 141, '5': 794}, repeat-last {'0': 220, '1': 245, '2': 188, '3': 121, '4': 134, '5': 863}.

**buffer 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| <5s | 109 | 106 | 45.28 % | 96.23 % | 33.33 % |
| 5-10s | 243 | 101 | 95.05 % | 95.05 % | 89.47 % |
| 10-20s | 611 | 174 | 87.36 % | 86.78 % | 87.86 % |
| >=20s | 3737 | 1390 | 83.60 % | 86.47 % | 87.70 % |

**throughput 안정성(최근 6 관측 CV) 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| stable cv<0.10 | 3305 | 1032 | 86.72 % | 86.63 % | 87.70 % |
| moderate 0.10-0.30 | 1019 | 473 | 90.49 % | 90.49 % | 90.36 % |
| volatile cv>=0.30 | 276 | 166 | 54.82 % | 77.71 % | 79.31 % |
| unknown | 100 | 100 | 44.00 % | 100.00 % | n/a |

**Latency 귀속 (per-decision)**

| stage | n | 비중 | latency mean ms | MPC rollout CPU ms | verify logits ms | selected tokens mean |
|---|---|---|---|---|---|---|
| draft_verify | 1771 | 37.68 % | 84.772 | 0.691 | 1.696 | 161.834 |
| fallback | 950 | 20.21 % | 70.444 | n/a | n/a | 149.147 |
| queue_serve | 1979 | 42.11 % | 1.858 | n/a | n/a | 0.000 |

전체 decision latency 합 220729 ms 중 MPC brute-force rollout CPU 시간은 1223 ms (**0.55 %**), throughput predictor까지 포함해도 0.77 %.

