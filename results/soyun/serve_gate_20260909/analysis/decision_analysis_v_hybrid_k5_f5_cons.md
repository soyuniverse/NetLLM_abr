### v_hybrid_k5_f5_cons — per-decision post-hoc analysis

`results/soyun/serve_gate_20260909/v_hybrid_k5_f5_cons/decisions.jsonl` — 4700 decisions over 100 traces; 1762 draft+verify steps, 2734 steps where the LLM actually produced an action.

| 지표 | 정의 | 값 | 분모 |
|---|---|---|---|
| 1. MPC draft 1-step 일치율 | `mpc_draft_actions[0] == llm_target_action` | 82.75 % | 1762 |
| 2. 직전 행동 반복 drafter (가상) | `last_action == llm_action` | 88.59 % | 2734 |
| 2b. 동일 기준(verify step만) | `last_action == llm_target_action` | 88.08 % | 1762 |
| 3. LLM 행동 자기상관 (인접 t) | `llm_action(t) == llm_action(t-1)` | 87.87 % | 1888 |
| 3b. LLM 호출 순서 기준 | 직전 LLM 호출의 행동과 비교 | 84.05 % | 2634 |

**Draft 위치별 일치율 (k=5)**

| draft position | n | MPC 일치율 | repeat-last 일치율 |
|---|---|---|---|
| 0 | 1762 | 82.75 % | 88.08 % |
| 1 | 1720 | 79.13 % | 81.92 % |
| 2 | 1684 | 79.10 % | 80.82 % |
| 3 | 1646 | 74.48 % | 76.37 % |
| 4 | 1602 | 71.60 % | 76.03 % |

accepted-prefix 길이 평균 — MPC **3.157** / repeat-last **3.354** (최대 5). MPC prefix 분포 {'0': 304, '1': 221, '2': 140, '3': 153, '4': 117, '5': 827}, repeat-last {'0': 210, '1': 245, '2': 154, '3': 151, '4': 107, '5': 895}.

**buffer 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| <5s | 104 | 100 | 44.00 % | 100.00 % | n/a |
| 5-10s | 232 | 100 | 98.00 % | 98.00 % | 93.33 % |
| 10-20s | 648 | 185 | 86.49 % | 86.49 % | 87.62 % |
| >=20s | 3716 | 1377 | 83.95 % | 86.71 % | 87.59 % |

**throughput 안정성(최근 6 관측 CV) 구간별**

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---|---|---|---|---|
| stable cv<0.10 | 3332 | 1018 | 88.61 % | 88.61 % | 88.35 % |
| moderate 0.10-0.30 | 988 | 474 | 87.97 % | 87.97 % | 90.23 % |
| volatile cv>=0.30 | 280 | 170 | 55.88 % | 78.24 % | 79.15 % |
| unknown | 100 | 100 | 44.00 % | 100.00 % | n/a |

**Latency 귀속 (per-decision)**

| stage | n | 비중 | latency mean ms | MPC rollout CPU ms | verify logits ms | selected tokens mean |
|---|---|---|---|---|---|---|
| draft_verify | 1762 | 37.49 % | 96.626 | 0.671 | 1.672 | 161.753 |
| fallback | 975 | 20.74 % | 80.167 | n/a | n/a | 148.607 |
| queue_serve | 1963 | 41.77 % | 1.859 | n/a | n/a | 0.000 |

전체 decision latency 합 252066 ms 중 MPC brute-force rollout CPU 시간은 1182 ms (**0.47 %**), throughput predictor까지 포함해도 0.65 %.

