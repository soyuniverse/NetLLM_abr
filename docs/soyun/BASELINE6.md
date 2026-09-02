# BASELINE6 — README 6개 평가 조건 × `--trace-num 100`

**Date:** 2026-09-02 · **Author:** soyun · **Branch:** `soyun/spec-abr`
**Run:** `results/soyun/baseline6_20260902/` · **GPU:** NVIDIA GeForce RTX 3090,
24 GB, driver 595.58.03 (7개 phase 전부 동일 인스턴스·동일 GPU)

관련: [[SMOKE_OFFICIAL_CKPT]] · [[RECON_SPECULATIVE]] · [[HANDOFF]] ·
[[NEEDS_UPSTREAM]] (#4 신규)

**한 줄 요약:** Temporal/Token selector 는 **1.65–1.85×** 실측 가속을 냈고,
Speculative 는 현재 drafter(Robust-MPC) 로는 **0.92×** — 즉 손해다. 원인은
MPC brute-force 의 CPU 비용이 아니라(전체 latency 의 **0.26 %**) draft block
때문에 늘어난 **context(+16.8 % latency)** 를 acceptance 가 갚지 못하는 것이다.
사후 분석 결과 **MPC 를 튜닝해서 될 문제가 아니라 drafter 자체를 바꿔야 한다**
(MPC 1-step 일치율 12.8 % vs "직전 행동 반복" 93.3 %).

---

## 0. 실행 조건

`$COMMON` (README "모듈 설정" 과 동일, `--model-dir` 만 실제 체크포인트 위치):

```
--test --fp16 --seed 1 --plm-type llama --plm-size base --rank 128
--plm-dir ../downloaded_plms/llama/base
--model-dir ../downloaded_plms/ft_plms/try_llama2_7b
--trace fcc-test --trace-num 100 --video video1 --fixed-order
--device cuda:0 --device-out cuda:0
```

`--model-dir` 만 README 의 `data/ft_plms/try_llama2_7b` 대신
`../downloaded_plms/ft_plms/try_llama2_7b` 를 쓴다. 공식 r=128 ABR 체크포인트를
soyun-writable 경로로 옮겨둔 것이며 SHA-256 동일
([[SMOKE_OFFICIAL_CKPT]] §1). 나머지 인자는 전부 README 그대로.

실행 순서 — A 를 처음과 끝에 두 번 배치해 **측정 오차 기준선**을 만든다.

| phase | 조건 | 추가 인자 | wall |
|---|---|---|---:|
| `a1_all_off` | all-off (기준) | `none / none / k=0` | 240.1 s |
| `b_temporal` | Temporal only | `event-aware / none / k=0` | 138.7 s |
| `c_recent_token` | Recent-token only | `none / recent-timestep --selector-history-steps 5 / k=0` | **실패 82.6 s** |
| `d_temporal_token` | Temporal+Token | `event-aware / intra-timestep / k=0` | 131.8 s |
| `e_speculative` | Speculative only | `none / none / k=3 greedy` | 261.3 s |
| `f_all_three` | All three | `event-aware / intra-timestep / k=3 greedy` | 147.1 s |
| `a2_all_off` | all-off 재실행 | `none / none / k=0` | 240.5 s |

전부 tmux 세션 `baseline6` 안에서 `abr_spec/run_baseline6.sh` 로 실행했고 각
phase 로그는 `tee` 로 `results/soyun/baseline6_20260902/logs/<phase>.log` 에
남겼다. upstream 파일은 하나도 수정하지 않았다(계측은 전부 monkeypatch).

`--speculative-verification-mode greedy` 는 지시대로 E·F 에 적용했다. README
기본값은 `sample` 이므로 **§3.2 의 confound 주의**를 함께 읽을 것.

---

## 1. 표1 — 성능

| 구성 | QoE (raw mean) | bitrate (Mbps) | rebuffer (s/chunk) | rebuffer total (s) | smoothness (Mbps) | ΔQoE % | Δbitrate % | Δrebuffer % | Δsmoothness % |
|---|---|---|---|---|---|---|---|---|---|
| a1_all_off | 0.94872 | 1.01655 | 0.00136 | 6.392 | 0.06199 | +0.00 | +0.00 | +0.00 | +0.00 |
| b_temporal | 0.88209 | 0.98297 | 0.00814 | 38.260 | 0.06587 | **−7.02** | −3.30 | +498.59 | +6.26 |
| c_recent_token | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| d_temporal_token | 0.89592 | 1.02279 | 0.01073 | 50.437 | 0.08072 | **−5.57** | +0.61 | +689.10 | +30.22 |
| e_speculative | 0.91904 | 0.95973 | 0.00002 | 0.085 | 0.04062 | **−3.13** | −5.59 | −98.66 | −34.48 |
| f_all_three | 0.91110 | 0.95678 | 0.00047 | 2.202 | 0.04366 | **−3.96** | −5.88 | −65.54 | −29.57 |
| a2_all_off | 0.94872 | 1.01655 | 0.00136 | 6.392 | 0.06199 | +0.00 | +0.00 | +0.00 | +0.00 |

평가 chunk 수는 모든 성공 phase 에서 4,700 (100 trace × 47) 로 동일하다.
`mean_reward` 는 `qoe_raw_mean` 과 항상 같은 값이라 표에서 생략했다(CSV 에는 포함).

**QoE 분해** — `QoE = bitrate − 4.3·rebuffer − smoothness` 이므로 A1 대비 델타를
세 항으로 정확히 쪼갤 수 있다(잔차 ~1e-16).

| 구성 | ΔQoE | = Δbitrate | + Δ(−4.3·rebuffer) | + Δ(−smoothness) |
|---|---|---|---|---|
| b_temporal | −0.06662 | −0.03359 | **−0.02916** | −0.00388 |
| d_temporal_token | −0.05280 | +0.00623 | **−0.04030** | −0.01873 |
| e_speculative | −0.02968 | **−0.05682** | +0.00577 | +0.02137 |
| f_all_three | −0.03761 | **−0.05978** | +0.00383 | +0.01833 |

성격이 완전히 다르다. **Selector 계열(B, D)의 QoE 손실은 rebuffering** 이
지배한다(총 rebuffer 6.4 s → 38.3 s / 50.4 s). **Speculative 계열(E, F)의 손실은
bitrate** 하나에서 나오고, rebuffering 과 smoothness 는 오히려 크게 좋아진다
(E 의 총 rebuffer 6.39 s → **0.085 s**). 즉 speculative 는 "더 보수적으로 낮은
bitrate 를 고르는 정책"으로 이동했다.

---

## 2. 표2 — 효율

| 구성 | speedup vs A1 (mean) | p50 | p95 | latency mean (ms) | p50 | p95 | inference_calls | target_plm_calls | llm_call_reduction | acceptance_rate | drafted | accepted | corrected | queued_served | fallback total | fb:buffer | fb:state | fb:return |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a1_all_off | 1.000× | 1.000× | 1.000× | 50.329 | 57.954 | 59.032 | 4700 | 4700 | 0.00000 | 0.00000 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| b_temporal | **1.750×** | 2.064× | 1.769× | 28.759 | 28.081 | 33.375 | 4700 | 4700 | 0.00000 | 0.00000 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| c_recent_token | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| d_temporal_token | **1.845×** | 2.099× | 2.100× | 27.279 | 27.611 | 28.108 | 4700 | 4700 | 0.00000 | 0.00000 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| e_speculative | **0.918×** | 0.861× | 0.862× | 54.815 | 67.297 | 68.445 | 4700 | 4405 | 0.06277 | 0.06142 | 12145 | 746 | 4054 | 295 | 268 | 236 | 32 | 0 |
| f_all_three | **1.649×** | 1.713× | 1.726× | 30.527 | 33.823 | 34.196 | 4700 | 4408 | 0.06213 | 0.06247 | 12117 | 757 | 4041 | 292 | 284 | 258 | 26 | 0 |
| a2_all_off | 0.998× | 0.998× | 0.999× | 50.424 | 58.077 | 59.120 | 4700 | 4700 | 0.00000 | 0.00000 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

`draft_generation_failures` 는 E·F 모두 **0**. `return_mismatch_fallbacks` 도 0 —
queue 폐기는 사실상 전부 **buffer tolerance**(236 / 258) 때문이다.

context 길이(참고):

| 구성 | original tokens (mean) | selected tokens (mean) | token_reduction |
|---|---:|---:|---:|
| a1_all_off | 131.3 | 131.3 | 0.0000 |
| b_temporal | 131.3 | 26.6 | 0.7976 |
| d_temporal_token | 131.3 | 19.5 | 0.8513 |
| e_speculative | **148.1** | 148.1 | 0.0000 |
| f_all_three | 148.6 | 34.0 | 0.7709 |

F 의 1.649× 는 **selector 가 만든 가속이지 speculation 이 만든 가속이 아니다.**
같은 selector 를 쓰는 D(1.845×)보다 오히려 느리다 — F/D 로 보면 speculation 은
여기서도 **0.89×**.

---

## 3. 분석

### 3.1 A1 vs A2 — 측정 오차 기준선

| | A1 | A2 | drift |
|---|---:|---:|---:|
| latency mean (ms) | 50.3287 | 50.4237 | **+0.189 %** |
| latency p50 (ms) | 57.9536 | 58.0771 | +0.213 % |
| latency p95 (ms) | 59.0321 | 59.1195 | +0.148 % |

QoE·bitrate·rebuffer·smoothness 는 A1 과 A2 가 **비트 단위로 동일**했다
(`qoe_raw_mean` 0.9487160882938208 양쪽 일치). 즉 궤적은 완전히 재현되며 드리프트는
순수 latency 측정 노이즈다.

**기준선: 약 0.2 %.** 이보다 작은 latency 차이는 이 보고서에서 유의미하다고 쓰지
않는다. 표2 의 효과들(−8.2 %, +65 %, +85 %)은 이 기준선보다 **40배 이상** 크므로
전부 실재하는 차이다.

### 3.2 E 는 A1 대비 QoE 를 유지하는가 — 아니오, −3.13 %

**하락은 전부 bitrate 에서 온다** (§1 분해: Δbitrate −0.0568 이 지배, rebuffer
+0.0058 과 smoothness +0.0214 가 일부 상쇄). closed-loop 오류 전파의 전형적 형태인
"rebuffering 폭증"은 **일어나지 않았다** — 오히려 총 rebuffering 이 6.39 s →
0.085 s 로 98.7 % 줄었다. 궤적이 발산한 게 아니라 **체계적으로 보수적인 쪽으로
이동**했다.

⚠ **Confound 를 반드시 같이 읽을 것.** E 의 결정 중 88.0 % 는 greedy(argmax) 로
나온 행동이고 A1 은 100 % `_sample()`(stochastic) 이다. 즉 E 와 A1 의 QoE 차이는
"speculation 때문"과 "greedy vs sample 때문"이 섞여 있다. greedy 는 분포의 꼬리를
버리므로 낮은-bitrate 쪽으로 쏠리는 게 자연스럽다. **이 −3.13 % 를 speculation 의
품질 비용이라고 단정할 수 없다.** 분리하려면
`--speculative-verification-mode sample` 로 E 를 한 번 더 돌리면 된다(약 4.4 분,
GPU 필요).

### 3.3 Latency 손해는 draft 계산이 아니라 context 증가 때문

E 의 per-decision 4,700 레코드로 분리 측정한 결과:

| 경로 | n | 비중 | latency mean (ms) | selected tokens (mean) |
|---|---:|---:|---:|---:|
| `draft_verify` (MPC draft + 1회 PLM 검증) | 4137 | 88.0 % | **58.808** | 148.7 |
| `fallback` (queue 폐기 → 일반 추론) | 268 | 5.7 % | 51.314 | 139.1 |
| `queue_serve` (LLM 호출 없음) | 295 | 6.3 % | **0.832** | 0 |

- **MPC brute-force rollout(6³=216 후보)의 CPU 시간 = 전체 decision latency
  257,287 ms 중 679 ms, 즉 0.26 %.** throughput predictor 까지 합쳐도 0.35 %.
  decision 당 평균 **0.164 ms**. F 에서는 0.47 %.
- 반면 draft block 을 붙여 길어진 context 는 호출당 **+8.48 ms (+16.85 %)**
  (A1 의 50.33 ms → verify 58.81 ms; token 131.3 → 148.7).
- **결론: latency 손해의 원인은 context 증가다.** MPC 계산을 아무리 최적화해도
  회수할 수 있는 건 0.26 % 뿐이다. k 를 줄이면 context surcharge 는 줄지만 동시에
  draft 공급도 줄어 queue 절감분이 함께 사라진다.

### 3.4 사후 분석 1–4 (E 의 jsonl 만 사용, 재실행 없음)

4,700 decisions / 100 traces. draft+verify 4,137 회, LLM 이 실제로 행동을 낸 스텝
4,405 회.

| # | 지표 | 정의 | 값 | 분모 |
|---|---|---|---|---|
| 1 | MPC draft 1-step 일치율 | `mpc_draft_actions[0] == llm_target_action` | **12.84 %** | 4137 |
| 2 | "직전 행동 반복" drafter 가상 일치율 | `last_action == llm_action` | **92.85 %** | 4405 |
| 2b | 같은 기준(verify 스텝만) | `last_action == llm_target_action` | **93.30 %** | 4137 |
| 3 | LLM 행동 자기상관 (인접 t) | `llm_action(t) == llm_action(t−1)` | **92.46 %** | 4056 |
| 3b | LLM 호출 순서 기준 | 직전 LLM 호출 행동과 비교 | 92.38 % | 4305 |

draft 위치별로 보면 격차가 더 벌어진다.

| draft position | n | MPC 일치율 | repeat-last 일치율 |
|---|---:|---:|---:|
| 0 | 4137 | 12.84 % | **93.30 %** |
| 1 | 4044 | 8.78 % | 34.97 % |
| 2 | 3964 | 14.86 % | 22.23 % |

accepted-prefix 길이 평균 — MPC **0.180** vs repeat-last **1.457** (최대 3).
prefix 분포: MPC `{0:3606, 1:375, 2:97, 3:59}`, repeat-last
`{0:277, 1:2469, 2:616, 3:775}`. **MPC 는 87 %의 경우 첫 스텝부터 틀린다.**

#### 4. 구간별 분해 — MPC 는 언제 맞고 언제 틀리는가

buffer 구간별:

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---:|---:|---:|---:|---:|
| < 5 s | 102 | 100 | **43.00 %** | 100.00 % | n/a |
| 5–10 s | 235 | 141 | 20.57 % | 97.16 % | 93.33 % |
| 10–20 s | 593 | 472 | 19.49 % | 97.03 % | 95.79 % |
| ≥ 20 s | 3770 | 3424 | **10.72 %** | 92.44 % | 91.97 % |

throughput 안정성(최근 6 관측의 변동계수 CV) 구간별:

| 구간 | decisions | verify | 1. MPC 1-step | 2b. repeat-last | 3. LLM 자기상관 |
|---|---:|---:|---:|---:|---:|
| stable CV<0.10 | 3344 | 2989 | **9.33 %** | 93.34 % | 92.85 % |
| moderate 0.10–0.30 | 961 | 835 | 14.61 % | 94.49 % | 93.51 % |
| volatile CV≥0.30 | 295 | 213 | **40.85 %** | 84.98 % | 85.17 % |
| unknown (관측 부족) | 100 | 100 | 43.00 % | 100.00 % | n/a |

**읽는 법.** MPC 가 맞는 상황은 **버퍼가 마르거나 throughput 이 요동칠 때**,
즉 물리적 제약이 행동을 강제하는 순간뿐이다(43 %, 40.9 %). 평상시 — 버퍼 ≥20 s,
throughput 안정 — 에는 9–11 % 로 떨어진다. 그런데 E 의 결정 중 **80.2 %가 버퍼
≥20 s, 71.1 %가 CV<0.10** 이다. 즉 MPC 는 **거의 항상 평상시 구간에서 틀린다.**

이유는 목적함수가 다르기 때문이다. MPC 는 `bitrate − 4.3·rebuf − smooth` 를
horizon 안에서 탐욕적으로 최대화하므로 버퍼가 넉넉하면 곧장 최고 bitrate 로
점프하려 한다. LoRA 정책은 그렇게 하지 않고 **직전 행동을 유지**한다(자기상관
92.5 %). 이건 threshold/tolerance 로 좁힐 수 있는 격차가 아니다.

**→ 판단: MPC 를 튜닝해서 될 문제가 아니다. drafter 를 바꿔야 한다.**
`--event-*`/tolerance 스윕은 회수할 여지가 없다. 반면 "직전 행동을 k번 반복"이라는
연산량 0 짜리 drafter 가 1-step 93.3 %, prefix 1.457 로 MPC 를 압도한다. 이는
LLM 행동 자기상관 92.5 % 의 직접적 귀결이다.

### 3.5 손익분기 — acceptance 5 % / 가속 24 % 기준선 대비 현재 위치

E 의 실측 단가로 latency 모형을 세우면(`q` = queue 로 처리된 decision 비율):

```
mean_latency(q) = (1−q)·58.808 + q·0.832        # verify 호출 vs queue 재사용
```

이 모형은 관측값을 그대로 재현한다(예측 0.916× vs 실측 0.918×).

| | 값 |
|---|---:|
| 현재 acceptance_rate | **6.14 %** (인용된 손익분기 5 % 를 이미 넘었다) |
| 현재 queue-serve 비율 `q` | 6.28 % |
| **A1 과 동률(1.00×)에 필요한 `q`** | **14.63 %** (현재의 **2.33배**) |
| **24 % 가속(1.24×)에 필요한 `q`** | **31.43 %** (현재의 **5.01배**) |

**"acceptance 5 %"는 손익분기가 아니다.** acceptance 6.14 % 로 5 % 선을 넘겼는데도
실측은 0.918× 다. latency 를 사는 것은 acceptance 자체가 아니라
`q = acceptance × horizon × tolerance 생존율` 이고, 여기서 세 번째 항이 새어나간다:
verify 호출당 queue 에 남는 항목은 0.160 개뿐이고 그중 44.5 % 만 실제로 소비된다
(queue depth 1 에서 49.6 %, depth 2 에서 27.7 %). 결과적으로 절감된 LLM 호출은
4,700 중 295 (6.28 %) 이고, 이걸 context surcharge +16.85 % 가 잡아먹는다.

**drafter 교체 시 예측치** (동일 trace, 동일 tolerance 생존율 가정):

| 시나리오 | verify 당 queue 항목 | `q` | 예측 latency | 예측 speedup |
|---|---:|---:|---:|---:|
| MPC (실측) | 0.160 | 6.7 % | 54.95 ms | 0.916× (실측 0.918×) |
| repeat-last, 평탄 생존율 | 1.236 | 35.5 % | 38.24 ms | **1.316×** |
| repeat-last, depth별 생존율 | 1.236 | 35.2 % | 38.43 ms | **1.310×** |

F(selector 위에 speculative)에 같은 계산을 하면 D 기준 0.890× → **1.249×**.

즉 **drafter 만 "직전 행동 반복"으로 바꾸면 두 경로 모두 24 % 가속 기준선을
넘긴다.** ⚠ 이 예측은 (a) queue 에 저장되는 predicted_state 는 여전히 MPC rollout
이 만들고, (b) drafter 가 바뀌면 궤적 자체가 달라진다는 두 가지를 고정한 1차
추정이다. 실제 검증에는 `speculative/mpc_draft.py` 수정 + 재실행이 필요하며,
해당 디렉터리는 현재 **read-only**(AGENTS.md)이므로 팀 리드 승인이 선행되어야 한다.

### 3.6 조건 C 실패 — recent-timestep selector 에서 PLM 이 all-NaN

`c_recent_token` 은 4,700 결정 중 **2,527번째**에서
`NonFiniteInferenceError(stage='plm_hidden')` 로 중단됐다(2회 재현, 동일 지점).
`abr_spec/nan_probe.py` 로 계측한 실패 시점:

```
trace_idx 53, chunk 36, context_tokens 47
attention mask 47/47 (마스크가 전부 0 인 행 없음)
fp32 입력 absmax 5.179 / fp16 변환 후 5.180, 전부 finite
직전 호출들의 hidden absmax 50–70  (fp16 max 65504 에서 한참 아래)
→ 출력 hidden [1,47,4096] 의 192,512개 원소가 전부 NaN
```

입력은 멀쩡하고 마스크도 정상인데 **Llama fp16 forward 내부에서** 전부 NaN 이
됐다. ABR embedding 이나 attention mask 문제가 아니라, recent-timestep 이 남긴
특정 47-token window 에서 Llama-2 내부 활성값이 fp16 범위를 넘긴 것으로 보인다
(B 는 26.6 token, D 는 19.5 token 으로 4,700 결정을 모두 통과했다 — 이 조건에서만
발생).

`plm_special/models/selectors.py` 는 팀메이트 소유이자 나에게 **읽기 전용**이므로
수정하지 않았다. [[NEEDS_UPSTREAM]] **#4** 로 기록했다.

---

## 4. 재현

```bash
tmux new -s baseline6 -d
RID=baseline6_20260902 bash abr_spec/run_baseline6.sh          # 7 phases, ~22 min GPU
# 특정 phase 만: PHASES="e_speculative f_all_three" RID=... bash abr_spec/run_baseline6.sh

python abr_spec/build_baseline6_report.py --run-dir results/soyun/baseline6_20260902
python abr_spec/analyze_decisions.py \
  results/soyun/baseline6_20260902/e_speculative/decisions.jsonl \
  --out-dir results/soyun/baseline6_20260902/analysis --label E
python abr_spec/breakeven.py \
  results/soyun/baseline6_20260902/e_speculative/decisions.jsonl \
  --baseline-latency-ms 50.329 \
  --out-dir results/soyun/baseline6_20260902/analysis --label E
```

계측 도구 (전부 `abr_spec/`, upstream 무수정):

| 파일 | 역할 |
|---|---|
| `run_baseline6.sh` | 7 phase 드라이버. 한 phase 가 실패해도 나머지를 계속 진행(A2 가 마지막에 반드시 돌아야 하므로). `PHASES` 로 부분 재개 |
| `decision_trace.py` | decision 당 JSONL 1줄. `sample_speculative` / `_actions_from_verification_logits` / `RobustMPCDraftGenerator.generate`·`observe` / `Environment.get_video_chunk` 를 monkeypatch. 레코드 조립은 CUDA-sync 측정 구간 **밖**에서 하므로 latency 를 오염시키지 않는다(검증: trace-num 2 스모크에서 QoE 가 비계측 실행과 완전 일치) |
| `analyze_decisions.py` | 사후 분석 1–4, 위치별 일치율, latency 귀속 |
| `breakeven.py` | 손익분기 `q`, drafter 교체 시나리오 |
| `nan_probe.py` | 조건 C 의 NaN 발생 지점 특정 (`--probe nan_probe`) |
| `run_wrapped.py` | 기존 wrapper. `--decision-trace`, `--probe`, **`--baseline-phase`** 추가 |

> `--baseline-phase` 를 추가한 이유: 기존 `--baseline-run-id` 는 baseline manifest
> 에서 latency 가 있는 **마지막** phase 를 골랐다. 7 phase 를 한 run-id 에 넣으면
> 그게 현재 phase 자신이 되어 speedup 이 항상 1.0 이 된다. 이제 baseline phase 를
> 명시적으로 지정한다.

---

## 5. 결과물 위치

```
results/soyun/baseline6_20260902/
  manifest.json  summary.json  summary_all.json
  table1_performance.csv  table2_efficiency.csv  qoe_decomposition.csv  tables.md
  <phase>/{selector_metrics.json, result.json, manifest_phase.json}
  e_speculative/decisions.jsonl   f_all_three/decisions.jsonl   (gitignored, 4700 lines each)
  c_recent_token_nanprobe/nan_probe.json
  analysis/{decision_analysis_E,decision_buckets_E,breakeven_E}.{json,csv,md}  (+ F)
  logs/<phase>.log, logs/driver.log                                (gitignored)
```

`results/soyun/**` 는 `*.json` / `*.csv` / `*.md` 만 git 에 추적된다. `.jsonl` 원본과
`console.log` 는 로컬에만 남는다 — 표와 분석 결과는 전부 추적되는 파일에 있다.

## 6. 다음에 할 것 (제안, 미실행)

1. **팀 리드 결정 필요:** drafter 를 "직전 행동 반복(+MPC 는 상태 예측에만 사용)"
   으로 교체. 예측 1.31× / 1.25×. `plm_special/speculative/` 수정 승인 필요.
2. E 를 `--speculative-verification-mode sample` 로 1회 재실행해 §3.2 의
   greedy-vs-sample confound 를 분리 (약 4.4 분).
3. 조건 C 의 fp16 NaN — [[NEEDS_UPSTREAM]] #4, selector 소유자에게 에스컬레이션.
