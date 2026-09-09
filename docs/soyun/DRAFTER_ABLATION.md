# DRAFTER_ABLATION — replacing the speculative drafter (mpc / repeat-last / hybrid)

**Date:** 2026-09-08 · **Author:** soyun · **Branch:** `soyun/spec-abr`
**Run:** `results/soyun/drafter_ab_20260908/` · **Baseline:** `results/soyun/baseline6_20260902/` A1 all-off
**GPU:** NVIDIA GeForce RTX 3090, 24 GB, driver 570.172.08 — **new instance**
(BASELINE6 / SWEEP_SPEC ran on driver 595.58.03). Absolute latency is not
comparable across instances, so `run_wrapped.py` correctly refuses a speedup
against `baseline6_20260902/a1_all_off`. **A fresh `a1_all_off` (k=0, all
selectors off, trace-num 100) is run on this instance as `drafter_ab_20260908/
a1_all_off` and is the speedup reference for every ablation phase.** This is the
one addition to `run_drafter_ablation.sh`'s recipe (the script assumed the
BASELINE6 instance); it is the same A1 config, re-measured where it can be a
valid latency baseline.

관련: [[SWEEP_SPEC]] · [[BASELINE6]] · [[HANDOFF]] · [[NEEDS_UPSTREAM]] (#5 신규)

## 결론 — **[drafter 교체로 speedup 1.0 돌파, 단 조건부]**

파라미터로는 못 넘던 **speedup 1.0 을 넘었고 1.24× 선도 넘었다.** `repeat-last`
drafter (직전 행동을 k번 반복) 가 LLM 의 다음 행동을 step-1 에서 **88 %** 맞혀
(mpc 는 13 %), 재사용률 q 를 7 % → **38 %** 로 밀어 올린다:

| drafter (k=3) | speedup (vs 이 인스턴스 A1) | q | QoE Δ | rebuffering |
|---|---:|---:|---:|---:|
| mpc (대조군) | 0.974× | 7 % | +0.8 % | 7.5 s (≈A1) |
| **repeat-last** | **1.419×** | 38 % | −1.5 % | 23.8 s (3.7× A1) |
| **hybrid** | **1.413×** | 37 % | −1.8 % | 26.9 s (4.2× A1) |
| repeat-last + Temporal/Token selector (M6) | **2.102×** | 38 % | −3.9 % | 30.4 s |

**"조건부"인 이유: rebuffering 이 유의하게 증가한다** (A1 6.4 s → 18–37 s).
안전 지표(§S)로 보면 queue 로 처리된 결정이 LLM 결정보다 rebuffer 를 **더 자주**
유발하진 않지만(발생률 게이트 통과), 한 번 나면 크고 총량이 사전 임계를 넘는다
(총량 게이트 실패). 위험은 전적으로 **버퍼가 마른 뒤 실행되는 소수의 queue
엔트리**(draft 는 몇 chunk 전 버퍼가 넉넉할 때 됨) 때문이다. 배치 전 필수 후속은
§S.7.

단가 모형(§Task2, [[SWEEP_SPEC]] §12): q→speedup 모형은 살아있으나 **본전 q 는
인스턴스 상수**(구 14.63 %, 신 ~11 %)이고 **k=5 부터 fallback 항이 필요**하다
(zero-search drafter 는 draft 를 거를 수 없어 fallback 지분이 21 %까지 오른다).

---

## 0. 실행 경로 동결 (Task 0)

- **Freeze commit:** `0d137ce5d03359bb2ba89621c696218ed402c5bb`
  (`feat(soyun): instrument all drafters in decision_trace + queue_safety.py`).
  Every run below records this in its `manifest_phase.json` `git_commit`. The
  execution-path files (`run_wrapped.py`, `decision_trace.py`, `drafter_select.py`,
  `adaptive_bitrate_streaming/plm_special/speculative/*`) are not touched again
  until the ablation is finished; if a change becomes necessary the run stops
  and it is reported (SWEEP_SPEC §2 shows the audit cost of a mid-run change).
- **Pre-run changes folded into the freeze commit** (both soyun-owned, both under
  `abr_spec/`, no team file touched):
  1. `abr_spec/decision_trace.py` — patch `BaseDraftGenerator.generate`/`.observe`
     instead of `RobustMPCDraftGenerator.*`, so the per-decision trace instruments
     `repeat-last` and `hybrid` too (they inherit `generate` from the base class,
     which the old patch never reached — verified empirically: draft actions,
     proposal CPU and hybrid's per-decision route were all `null` for those
     drafters). `mpc` is unaffected: `RobustMPCDraftGenerator` does not override
     `generate`, so the patched callable is the identical function object.
  2. `abr_spec/breakeven.py` — guard the empty-`verify` / no-serve cases instead
     of crashing on `max()` of an empty sequence.
  - Regression gate: `test_mpc_draft.py` + `test_speculative_acceptance.py` +
    `abr_spec/tests/test_drafters.py` → **40 passed**; the tolerance-0
    `MPCRefactorRegressionTest` battery (60 randomised cases vs the frozen
    pre-refactor generator) is inside that suite.
  - End-to-end gate: `m1a_mpc_k3_sample` must reproduce SWEEP_SPEC's `s0`
    (QoE 0.95637 / q 7.36 % / acceptance 7.91 %) — see §3.

- **k axis is capped at 5 by the execution path.** `run_plm.py:298`
  (`0 <= --speculative-draft-steps <= 5`, read-only team file) and
  `mpc_draft.py:190` (`1 <= max_horizon <= 5`, frozen). k=8 — the point of the
  "zero-search drafter beats the 6^k wall" argument — cannot run without editing
  a team file. Filed as [[NEEDS_UPSTREAM]] #5. **This ablation runs k ∈ {3, 5}.**

## 1. Determinism 검증 (Task 0.2)

각 drafter 를 **trace-num 5 / seed 1 / sample 모드 / k=3** 로 **2회** 돌려
(`results/soyun/determinism_20260908/det_{mpc,repeat,hybrid}_{a,b}/`) 대조.

| drafter | 행동 bit-identical? | QoE (a=b) | q (a=b) | acceptance (a=b) | fallback 총/buf/st | lat mean drift | decisions.jsonl 서명 |
|---|---|---|---|---|---|---|---|
| mpc | **예** | 1.184681 | 0.042553 (10/235) | 0.079125 | 23/21/2 | +1.18 % | a==b (`b7606351…`) |
| repeat-last | **예** | 1.160000 | 0.297872 (70/235) | 0.781350 | 59/50/9 | +1.63 % | a==b (`f5350431…`) |
| hybrid | **예** | 1.094894 | 0.289362 (68/235) | 0.704615 | 56/44/12 | +1.90 % | a==b (`0ad1a07a…`) |

- **행동은 세 drafter 모두 완전 재현.** `selector_metrics.json` 의 QoE·bitrate·
  rebuffer·smoothness·acceptance 와 12개 speculative counter 가 a·b 에서 전부
  동일하고, `decisions.jsonl` 235줄을 timing 필드(latency/cpu/rollout ms)만 제거한
  뒤 SHA-256 을 뜨면 drafter 별로 a·b 서명이 일치한다 — 즉 **모든 결정의 모든
  비-timing 필드가 비트 단위로 같다.**
- **`sample` 모드에서도 seed 고정이 재현을 보장한다.** 샘플링은
  `rl_policy._sample → random.choices` 이고 `run_plm.set_random_seed` /
  `test.test_on_env` 가 run 시작마다 재시드하므로 stochastic 추출이 결정론적이다
  (HANDOFF §2.2).
- latency 만 +1.2~1.9 % (mean) 움직였다. `torch.backends.cudnn.benchmark=True`
  (run_plm.py:501, 수정 불가)로 인한 커널 재선택·클럭 변동이며 궤적·counter 가
  전부 일치하므로 코드가 아니라 타이밍이다 (SWEEP_SPEC §3-0 의 s2_k2 재실행과
  동일 패턴). p95 는 235 표본 꼬리라 hybrid 에서 +10 % 까지 튀지만 mean/p50 은
  안정적이다. **이 실험의 speedup 은 절대 ms 가 아니라 같은 인스턴스의 A1 대비
  비율로만 인용한다** (§0, §2).

## 2. Drafter × k 결과 (Task 1) — **speedup 1.0 돌파 (조건부)**

집계: `results/soyun/drafter_ab_20260908/analysis/drafter_ablation_table.{csv,md}`.
speedup 는 **이 인스턴스의 A1 (80.627 ms)** 대비. 전 phase trace-num 100 / seed 1 /
sample (m1b 만 greedy, BASELINE6 E 연속성용) / tolerance 1.0-0.25-0.01 고정.

| phase | drafter | k | QoE | ΔQoE % | **speedup** | q | accept | draft 1-step | prefix 평균 | rebuf tot (s) | Δrebuf (s) | fb 총/buf/st |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| m1a | mpc | 3 | 0.95637 | **+0.81** | 0.974× | 7.36 % | 7.9 % | 16.3 % | 0.232 | 7.48 | +1.09 | 353/315/38 |
| m1b | mpc | 3 (greedy) | 0.91904 | −3.13 | 0.961× | 6.28 % | 6.1 % | 12.8 % | 0.180 | 0.09 | −6.31 | 268/236/32 |
| **m2** | **repeat-last** | **3** | 0.93424 | −1.53 | **1.419×** | 37.77 % | 78.4 % | **88.0 %** | **2.301** | 23.85 | **+17.45** | 900/759/141 |
| **m3** | **hybrid** | **3** | 0.93191 | −1.77 | **1.413×** | 37.28 % | 73.0 % | 83.2 % | 2.142 | 26.87 | +20.48 | 847/686/161 |
| **m4** | **repeat-last** | **5** | 0.91111 | −3.96 | **1.306×** | 41.91 % | 69.5 % | 87.2 % | 3.314 | 37.12 | +30.73 | 1000/840/160 |
| **m5** | **hybrid** | **5** | 0.93001 | −1.97 | **1.326×** | 41.85 % | 65.9 % | 82.7 % | 3.148 | 18.51 | +12.11 | 971/833/138 |

### 2.1 판정 기준 대조 (사전 고정)

| 기준 | 결과 |
|---|---|
| **speedup > 1.0** (파라미터 스윕이 못 넘은 선) | **넘었다.** zero-search drafter 4종 모두 1.31×–1.42×. mpc 는 여전히 <1.0 (0.96–0.97×). |
| **1.24× 선** (q=31.43 %, BASELINE6) | **넘었다.** m2/m3 는 speedup 으로도 q(37 %)로도 통과. m4/m5 는 speedup 1.31/1.33× 로 통과하나 q(42 %)가 이 인스턴스의 k=5 필요치(§Task2)에 아슬아슬. |
| **QoE 유지** (A1 0.94872 대비 ±1 %) | **미달.** 최선이 m2 −1.53 %, m5 −1.97 %, m4 −3.96 %. mpc-sample(m1a) 만 +0.81 %. zero-search drafter 는 speedup 을 위해 QoE 를 1.5–2 % 내준다. |
| **rebuffering 유의 증가 없음** | **증가.** 총 rebuffering 이 A1 6.39 s → **18.5–37.1 s (2.9×–5.8×)**. 사전 임계(> 0.64 s) 를 크게 초과. |

→ **결론: "조건부 성공."** speedup 은 파라미터로 못 넘던 1.0 을 확실히 넘었고
1.24× 도 통과했지만, **rebuffering 이 유의하게 증가**하므로 Task 1.3 규정대로
조건부로만 기록한다. 안전 지표 분석은 §S 결과, hybrid 대조는 §2.3.

### 2.2 왜 되는가 — draft 일치율

`repeat-last` draft 는 LLM 의 다음 행동을 **step-1 에서 88.0 % (m2)** 맞힌다
(m1b 의 mpc 12.8 % 대비). accepted-prefix 평균은 m2 **2.301 / 3**, m4 **3.314 / 5**
(mpc 는 0.18). 이는 BASELINE6 §3.4 의 사후 추정(LLM 자기상관 92.5 % → repeat-last
가상 일치율 93.3 %)을 **실측으로 확인**한 것이다. sample 모드라 자기상관이 86–89 %
로 greedy(92 %)보다 낮지만 repeat-last 가 여전히 압도한다.

버퍼 구간별 (draft 1-step, verify step 기준):

| 구간 | m2 repeat k3 | m3 hybrid k3 | m1a mpc k3 |
|---|---:|---:|---:|
| < 5 s | 97.2 % | 43.4 %\* | 42.6 % |
| 5–10 s | 90.2 % | 95.8 % | 18.2 % |
| 10–20 s | 86.8 % | 87.9 %\* | 22.2 % |
| ≥ 20 s | 87.5 % | 84.3 %\* | 14.4 % |

\* hybrid 는 이 구간에서 일부 결정을 mpc 로 라우팅하므로 "draft 1-step" 이 mpc 와
repeat 의 혼합이다. hybrid 의 route 분해: **draft 시도의 13.8 % (m3) / 15.5 % (m5)
가 mpc 로**, 나머지는 repeat-last (`draft_route` 필드, freeze 패치로 신규 계측).
`< 5 s` 에서 hybrid 가 43 % 로 떨어지는 것은 그 구간을 통째로 mpc 에 넘기기 때문 —
순수 repeat-last 였다면 그 구간도 ~95 % 였다. hybrid 는 **위험 구간의 일치율을
포기하고 안전을 산다** (§2.3).

### 2.3 fallback 폐기 사유별 분해 (SWEEP_SPEC §5 형식)

| phase | fb 총 | buffer | state | q | 해석 |
|---|---:|---:|---:|---:|---|
| m1a mpc k3 | 353 | 315 | 38 | 7.4 % | draft 가 자주 틀려 queue 진입 자체가 적음 |
| m2 repeat k3 | 900 | 759 | 141 | 37.8 % | draft 는 자주 맞지만(prefix 2.3) 그 궤적이 buffer 예측과 어긋나 **buffer fallback 이 3.5×** 폭증. 그럼에도 q 는 5× |
| m3 hybrid k3 | 847 | 686 | 161 | 37.3 % | m2 와 유사, buffer fallback 약간 감소(mpc 라우팅분) |
| m4 repeat k5 | 1000 | 840 | 160 | 41.9 % | k 가 길어 궤적 이탈 누적, fallback 최다 |
| m5 hybrid k5 | 971 | 833 | 138 | 41.9 % | — |

**핵심:** zero-search drafter 는 **일치율(draft==LLM)은 높지만 buffer fallback 이
급증**한다. draft 행동이 맞아도 그 행동이 만드는 buffer 궤적이 실제와 tolerance
1.0 s 를 벗어나면 queue 가 폐기된다. SWEEP_SPEC §5 에서 "행동이 틀려서" 폐기됐던
것과 달리, 여기서는 **행동은 맞는데 buffer 예측 모델(simulate_actions 의 4 s 고정
재생성 가정)이 부정확**해서 폐기된다. tolerance 를 여기서 다시 볼 가치가 생겼다
(SWEEP_SPEC §6 이 예견) — 단 이번 실험은 tolerance 고정이므로 후속 과제.

## 3. mpc 회귀 대조 (Task 0.3) — **PASS**

`m1a_mpc_k3_sample` (freeze `0d137ce`, 이 인스턴스) vs SWEEP_SPEC `s0`
(`3964752`, 구 인스턴스):

| 지표 | s0 (구) | m1a (신, freeze) | 판정 |
|---|---:|---:|---|
| QoE | 0.956366 | **0.956366** | 완전 일치 |
| q (queue-serve) | 0.073617 (346) | **0.073617 (346)** | 완전 일치 |
| acceptance_rate | 0.079084 | **0.079084** | 완전 일치 |
| target_plm_calls | 4354 | **4354** | 완전 일치 |
| fallback 총/buffer/state | 353/315/38 | **353/315/38** | 완전 일치 |
| bitrate / rebuf_tot / smooth | 1.029968 / 7.48389 / 0.066755 | **동일** | 완전 일치 |

`decision_trace.py` 의 `BaseDraftGenerator` 패치는 mpc 행동을 비트 하나도 바꾸지
않았다 (latency 만 다르고 s0 는 구 인스턴스라 비교 안 함). 회귀 게이트 통과.

### A1 기준선 (이 인스턴스)

`drafter_ab_20260908/a1_all_off` (k=0, selector off, trace-num 100):
QoE **0.948716** · bitrate 1.016553 · rebuf_tot 6.39172 · smooth 0.061989 —
**BASELINE6 A1 과 QoE·bitrate·rebuffer 완전 동일** (궤적은 인스턴스 무관).
latency mean **80.627 ms** / p50 84.84 / p95 105.63 — 이 캠페인의 모든
speedup·break-even 계산의 분모 (BASELINE6 A1 의 50.329 ms 가 아님). 이 인스턴스는
절대 latency 가 ~1.6× 느리므로 speedup 비율 자체도 SWEEP_SPEC 과 직접 비교 불가 —
같은 인스턴스 안 drafter 간 비교만 유효하다.

---

## S. 안전 지표 설계 — queue 결정 직후 window 의 rebuffering

**왜 이 지표인가.** `queue_serve` 결정은 LLM 호출 없이 이전에 draft 된 행동을 그대로
실행한다. draft 가 틀렸을 때의 피해는 그 chunk 하나가 아니라 **뒤따르는 몇 chunk 의
rebuffering** 으로 번질 수 있다 (버퍼가 한 번 마르면 회복에 시간이 걸리므로). q 가
6 % 대였던 파라미터 스윕에서는 이 표면적이 작았지만, repeat-last/hybrid 는 q 를
30 %+ 로 올릴 것으로 예측되므로 (BASELINE6 §3.5) 이 지표가 **이번 실험의 핵심
안전 게이트**다.

### S.1 Window 정의

- 결정을 `(trace_idx, t)` 로 식별하고 한 trace 안에서 `t` 오름차순으로 정렬한다.
- `stage == "queue_serve"` 인 결정 D 마다, **post-window** = D 자신(offset 0)부터
  같은 trace 의 이후 결정 offset 1..W 까지. **W = k** (그 run 의 draft 길이) 로
  잡는다 — speculation 이 커밋한 horizon 과 정확히 일치시킨다. trace 경계
  (`end_of_video_after == true`) 를 넘지 않는다.
- 한 chunk 의 rebuffering 은 `rebuffer_after_s` 에 있다. `decision_trace.py` 는
  결정 레코드를 다음 `get_video_chunk` 결과가 올 때까지 pending 으로 들고 있다가
  flush 하므로, `rebuffer_after_s` 는 **그 결정이 고른 chunk 를 받을 때 실제로 생긴
  rebuffering** 이다 (귀속이 이미 결정 단위로 되어 있다).

### S.2 귀속 규칙 (세 가지 관점, 모두 보고)

| 지표 | 정의 | 무엇을 답하나 |
|---|---|---|
| **A. 직접** | `mean(rebuffer_after_s)` over `queue_serve` 결정 (offset 0) vs. over LLM-served 결정 (`draft_verify`/`fallback`/`plain`) | queue 로 처리된 chunk 자체가 LLM chunk 보다 더 rebuffer 하나 |
| **B. 지연** | `queue_serve` 뒤 offset 1..W 결정들의 `mean(rebuffer_after_s)` vs. 전체 평균 | draft 오류의 피해가 다음 chunk 들로 번지나 |
| **C. window 발생률** | `[0..W]` window 안에 rebuffer event(`rebuffered == true`)가 1건 이상인 `queue_serve` 결정의 비율 | "위험한" queue serve 가 얼마나 흔한가 |

### S.3 교란 통제

`queue_serve` 는 draft 가 수용될 만큼 **상태가 안정적일 때** 우선 일어난다 — 즉
버퍼가 높고 throughput 이 안정적인 구간에 몰린다. 따라서 A/B 를 그냥 비교하면
queue serve 가 **실제보다 안전해 보이는** 방향으로 편향된다. 통제:

1. **버퍼 구간별로** (`<5s / 5–10s / 10–20s / ≥20s`, BASELINE6 와 동일 구간)
   A/B/C 를 쪼개 보고한다. 같은 버퍼 구간 안에서 queue vs LLM 을 비교한다.
2. **drafter 간 대조.** m1a (mpc, q≈7 %) 의 queue-serve window rebuffering 을
   기준선으로 두고 repeat-last/hybrid 가 같은 지표에서 유의하게 나빠지는지 본다.
   mpc control 자체가 "안전하다고 이미 인정된" 참조점이다.
3. **A1 반사실 없음.** BASELINE6 는 A1 에 per-decision trace 를 남기지 않았고
   원본 jsonl 은 인스턴스와 함께 사라졌다 (derived/ 에 distill 만 존재). 따라서
   "LLM 을 불렀다면" 반사실은 만들 수 없고, 통제 1·2 로 대신한다.

### S.4 판정

- queue-serve window(A·B·C 어느 것이든)의 rebuffering 이 **같은 버퍼 구간의
  LLM-served 기준 대비, 그리고 mpc control 대비** 유의하게 높으면 → speedup 이
  나와도 **"조건부 성공"** 으로만 기록하고 hybrid 와 대조한다 (Task 1.3).
- "유의"의 기준: 절대 rebuffering 이 워낙 작으므로 (BASELINE6 E: 총 0.085 s),
  **event 발생률(C)** 과 **총 rebuffering 초** 를 함께 본다. C 가 mpc control 의
  2배를 넘거나 총 rebuffering 이 A1(6.4 s)의 10 % (0.64 s)를 넘으면 유의로 본다.
  이 임계는 사전 고정이며 사후 조정하지 않는다.

### S.5 구현

`abr_spec/queue_safety.py` (신규, 소유 abr_spec/, post-hoc 전용, GPU 불필요):
`decisions.jsonl` 을 읽어 A/B/C × 버퍼구간 표와 drafter 간 대조표를 CSV+JSON 으로
낸다. 실행 경로가 아니므로 동결 대상이 아니지만, 분석 단계에서만 쓰고
`decisions.jsonl` 수치만 취한다 (추정 금지).
`window_union_rebuffer_s` 는 **겹치는 window 를 (trace_idx, t) 로 dedup 한 합집합**
위에서 계산한다 (q≈40 % 에서 W=5 window 가 크게 겹쳐 단순 합산은 run 총량을
초과했다).

### S.6 결과 — **안전성 판정: 조건부 (incidence 통과 / 총량 초과)**

`results/soyun/drafter_ab_20260908/analysis/queue_safety.{csv,json}`.

| phase | q | **C. window 발생률** | C vs mpc | window 합집합 rebuf (s) | (run 총 rebuf 대비) | A. queue 직접 (s) | A. LLM 직접 (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| m1a mpc k3 | 7.4 % | 0.578 % | 1.00× (ref) | 0.085 | 1 % | 0.0000 | 0.0017 |
| m2 repeat k3 | 37.8 % | **0.338 %** | 0.58× | 8.77 | 37 % | 0.0018 | 0.0071 |
| m3 hybrid k3 | 37.3 % | **0.228 %** | 0.39× | 12.9 | 48 % | **0.0000** | 0.0091 |
| m4 repeat k5 | 41.9 % | **0.254 %** | 0.44× | 16.7 | 45 % | 0.00003 | 0.0136 |
| m5 hybrid k5 | 41.9 % | **0.559 %** | 0.97× | 17.7 | 95 % | **0.0054** | 0.0029 |

**(1) 발생률(C) 기준으로는 queue serve 가 더 위험하지 않다.** 사전 임계
"C > mpc control 의 2×" 를 넘은 drafter는 없다 (최대 m5 0.97×). queue 로 처리된
결정의 window 에서 rebuffer event 가 나는 비율은 오히려 mpc control 보다 **낮다**
(m2 0.58×, m3 0.39×). draft 가 자주 맞으므로(§2.2) queue 엔트리도 대체로 옳다.

**(2) 그러나 총 rebuffering 은 사전 임계(> 0.64 s)를 크게 초과한다.** queue window
합집합의 rebuffering 이 8.8–17.7 s 로, run 전체 rebuffering 의 **37–95 %** 를
차지한다. 즉 rebuffering event 자체는 드물지만 **한 번 나면 크다** (버퍼가 마르면
회복에 여러 chunk 가 걸리므로).

**(3) 버퍼 구간이 원인을 가른다.** 거의 모든 queue-serve rebuffering 이
**`< 5 s` 구간**에 몰린다:

| phase · 구간 | queue serve 수 | A. queue 직접 (s/chunk) | C 발생률 |
|---|---:|---:|---:|
| m2 repeat k3 · <5s | 5 | **0.339** | 20 % |
| m3 hybrid k3 · <5s | 3 | **0.000** | 0 % |
| m4 repeat k5 · <5s | 2 | 0.028 | 50 % |
| **m5 hybrid k5 · <5s** | **7** | **1.462** | 71 % |
| (모든 phase · ≥20s) | 1300–1500 | ~0.000 | <0.2 % |

`≥ 20 s` 구간(전체 queue serve 의 76 %)에서는 queue 직접 rebuffering 이 **0** 이다.
위험은 전적으로 **버퍼가 마른 상태에서 실행되는 소수의 queue 엔트리** 때문이다 —
그 엔트리는 몇 chunk 전 버퍼가 넉넉했을 때 draft 된 것이고, 그 사이 버퍼가 drain
됐다. **hybrid 의 route-time 버퍼 검사는 이걸 못 막는다** (draft 시점엔 버퍼가
높았으니까). m5(hybrid k5)에서 `<5s` queue serve 7건의 평균 chunk rebuffering 이
**1.46 s** 인 것이 이 실패 모드의 가장 선명한 증거다.

**(4) hybrid 대조 (Task 1.3).** hybrid k3(m3)는 **모든 버퍼 구간에서 queue 직접
rebuffering 이 0** 이다 — k=3 에서는 hybrid 의 라우팅이 queue 엔트리를 위험 구간
밖으로 유지한다. 대신 window 안 LLM-served chunk 의 rebuffering(<5s 에서 9.5 s)은
남아 총량은 repeat k3(m2)보다 오히려 크다(26.9 vs 23.8 s). k=5 로 가면 hybrid 의
보호가 깨진다(m5 의 1.46 s spike). 즉 **hybrid 는 k 를 짧게 유지할 때만 queue
안전 이점이 있고, 그 이점은 총 QoE·rebuffering 을 되돌리진 못한다.**

### S.7 안전성 최종 판정

- **incidence 게이트: 통과.** queue serve 가 LLM 호출보다 rebuffer 를 더 자주
  유발하지 않는다 (C ≤ 0.97× mpc, 사전 임계 2× 미달).
- **총량 게이트: 실패.** 총 rebuffering 이 A1 의 2.9–5.8×, 사전 임계(0.64 s) 초과.
- → **"조건부 성공"** 확정. speedup > 1.24× 는 달성했으나 안전 기준 미달.
  실무 배치 전 필수 후속: (a) queue 엔트리에 **실행 시점 버퍼 재검사** 추가
  (draft 시점이 아니라), (b) `<5s` 버퍼에서는 queue serve 금지, (c) buffer
  tolerance 재조정 (§2.3). 이들은 `plm_special/speculative/` 및 rl_policy 변경이
  필요하므로 팀 리드 승인 후 별도 실험.

## 4. Temporal+Token 결합 경로 (Task 3) — **드라이버가 선택기 위에 얹혀 이득 큼**

speedup > 1.0 을 달성했으므로 Task 3 을 진행했다. 최선 drafter = **repeat-last k=3**
(speedup 최고 1.419×, zero-search 중 QoE 최고). BASELINE6 condition D
(`event-aware` temporal + `intra-timestep` token, k=0) 를 그 위에 얹었다
(`m6_best_plus_selectors`). 비교 기준을 위해 D 를 이 인스턴스에서 단독으로도 다시
측정했다 (`d_temporal_token`).

| 구성 | speedup (vs 이 A1) | QoE | rebuf tot (s) | 비고 |
|---|---:|---:|---:|---|
| A1 all-off | 1.000× | 0.94872 | 6.39 | 기준 |
| D — selector only (k=0) | 1.382× | 0.89590 | 50.44 | BASELINE6 D 재측정 (구 인스턴스 1.845×) |
| m2 — repeat-last k3 only | 1.419× | 0.93424 | 23.85 | §2 |
| **m6 — repeat-last k3 + D** | **2.102×** | **0.91191** | 30.41 | 결합 |

**(1) 결합 이득이 크고, 거의 곱셈적이다.** m6 2.102× 는 D 1.382× 와 m2 1.419× 의
곱(1.96×)을 약간 상회한다. selector 는 context 를 85 % 자르고 (148 → 31 토큰),
그 위에서 repeat-last 가 q 를 38 % 로 밀어 LLM 호출 자체를 줄인다 — 두 메커니즘이
직교한다. **"selector 가 이미 이득을 다 가져갔나?" 에 대한 답은 아니오.**
selector 만으로는 1.38×, drafter 를 얹으면 **2.10×** 다 (+0.72×).

**(2) selector 위에서는 drafter 가 QoE·rebuffering 을 오히려 개선한다.**
D 단독 QoE 0.896 / rebuf 50.4 s → m6 QoE **0.912** / rebuf **30.4 s**. speculative
검증(sample)이 selector 로 잘린 context 만으로 고른 행동보다 나은 행동을 채택하기
때문이다. 즉 m6 은 D 대비 **더 빠르고 + QoE 높고 + rebuffering 절반**이다.
다만 A1 대비로는 여전히 QoE −3.9 %, rebuf 4.8× 라 §S.7 의 조건부 판정은 유지된다.

**(3) m6 의 queue serve 는 가장 안전하다.** 안전 지표 C = **0.056 %** (mpc control
의 0.10×), 모든 버퍼 구간에서 queue 직접 rebuffering 0.0. selector 가 context 를
줄여 draft·verify 가 더 자주 일치하고(prefix 2.273), queue 엔트리가 위험 구간에
들어가는 경우가 거의 없다. m6 의 rebuffering 30 s 는 **selector 탓이지 speculation
탓이 아니다** (D 단독이 이미 50 s).

---

## 5. 결과물 위치

```
results/soyun/drafter_ab_20260908/
  manifest.json  summary.json
  a1_all_off/  d_temporal_token/                         (이 인스턴스 기준선)
  m1a_mpc_k3_sample/ m1b_mpc_k3_greedy/
  m2_repeat_k3/ m3_hybrid_k3/ m4_repeat_k5/ m5_hybrid_k5/
  m6_best_plus_selectors/
    {selector_metrics.json, result.json, manifest_phase.json, decisions.jsonl*}
  analysis/
    drafter_ablation_table.{csv,md}         <- §2 집계
    decision_analysis_<phase>.{json,md,csv} <- 일치율·prefix·버퍼구간
    breakeven_<phase>.json                  <- q 모형 (baseline 80.627 ms)
    queue_safety.{json,csv}                 <- §S 안전 지표
  logs/<phase>.log*
results/soyun/determinism_20260908/          <- Task 0.2 (trace-num 5, 2×3 runs)
results/soyun/derived/drafter_ab_20260908_summary.json   <- decisions.jsonl distill (tracked)
```
`*` = `.jsonl` / `.log` 은 gitignored. 수치는 전부 tracked 파일에 있다.

## 6. 재현

```bash
# 0. 인스턴스 셋업: docs/soyun/VASTAI_SETUP.md (venv + Llama + ckpt + fp16 gate)
bash abr_spec/hooks/install.sh
git checkout 0d137ce           # freeze commit

# 1. determinism (Task 0.2, ~8 min GPU)
bash abr_spec/run_determinism_check.sh     # 3 drafters x {a,b}, trace-num 5, seed 1, sample, k=3

# 2. A1 (이 인스턴스) + 6 phase ablation (~35 min GPU, ~$0.13)
python abr_spec/run_wrapped.py --run-id drafter_ab_20260908 --phase a1_all_off \
  --ckpt-name official_abr_r128 --baseline-run-id drafter_ab_20260908 --baseline-phase a1_all_off \
  -- <COMMON> --temporal-selector none --token-selector none --speculative-draft-steps 0
BASE_RID=drafter_ab_20260908 BASE_PHASE=a1_all_off RID=drafter_ab_20260908 \
  bash abr_spec/run_drafter_ablation.sh

# 3. Task 3: best drafter + selectors  (~3 min GPU)
BEST_DRAFTER=repeat-last BEST_K=3 RUNS=m6_best_plus_selectors \
  BASE_RID=drafter_ab_20260908 BASE_PHASE=a1_all_off RID=drafter_ab_20260908 \
  bash abr_spec/run_drafter_ablation.sh
# D (selector only) 대조: 위 a1_all_off 명령에서 selector 를 event-aware/intra-timestep 로

# 4. 분석 (CPU only, ~3 min)
python abr_spec/build_drafter_ablation_report.py --rid drafter_ab_20260908
for p in m1a_mpc_k3_sample m1b_mpc_k3_greedy m2_repeat_k3 m3_hybrid_k3 \
         m4_repeat_k5 m5_hybrid_k5 m6_best_plus_selectors; do
  python abr_spec/analyze_decisions.py results/soyun/drafter_ab_20260908/$p/decisions.jsonl \
    --out-dir results/soyun/drafter_ab_20260908/analysis --label $p
  python abr_spec/breakeven.py results/soyun/drafter_ab_20260908/$p/decisions.jsonl \
    --baseline-latency-ms 80.6269 \
    --out-dir results/soyun/drafter_ab_20260908/analysis --label $p
done
python abr_spec/queue_safety.py \
  $(for p in m1a_mpc_k3_sample m1b_mpc_k3_greedy m2_repeat_k3 m3_hybrid_k3 \
             m4_repeat_k5 m5_hybrid_k5 m6_best_plus_selectors; do \
      echo $p=results/soyun/drafter_ab_20260908/$p/decisions.jsonl; done) \
  --out-dir results/soyun/drafter_ab_20260908/analysis
python abr_spec/derive_decision_summary.py

# 5. 논문 그림 4종
python abr_spec/make_figures.py --out-dir results/soyun/figures
```

### 코드 동결 고지

전 phase `manifest_phase.json` 의 `git_commit` 이 `0d137ce` 다. 실행 경로
(`run_wrapped.py`, `decision_trace.py`, `drafter_select.py`,
`plm_special/speculative/*`) 는 실험 중 변경 없음. freeze 직전 변경은 §0:
`decision_trace.py`(모든 drafter 계측) + `breakeven.py`(빈 verify 가드), 둘 다
40-test + tolerance-0 회귀 통과, m1a==s0 end-to-end 확인.

## 7. 논문 그림 4종 (Task 4)

`python abr_spec/make_figures.py --out-dir results/soyun/figures` →
각 300 dpi PNG + vector PDF, 흑백 대응(hatch), 영문 캡션(`<name>.caption.txt`).
바이너리는 gitignore, `results/soyun/figures/README.md` 가 tracked 기록.

| 그림 | 내용 | 핵심 메시지 |
|---|---|---|
| fig1 | 6조건 × [QoE, speedup] 이중축, A1 선 + determinism 오차선, 1.0×·1.24× 선 | mpc <1.0, zero-search 4종 모두 1.24× 돌파, QoE −1.5~4 % |
| fig2 | q vs speedup — 단가 모형 곡선(구·신 인스턴스) + 파라미터 11점 + drafter 실측점 + 본전/1.24× q 선 | 파라미터는 q<10 %·speedup<1.0 에서 멈춤, drafter 는 q 38–42 % 로 곡선을 타고 넘음 |
| fig3 | buffer tolerance 완화 시 buffer/state fallback stacked bar | 총 fallback 불변, 구성만 이동 → gate 가 아니라 draft 가 병목 |
| fig4 | drafter 3종 × [일치율, q, speedup, ΔQoE, Δrebuffer] + 버퍼 구간별 일치율 | repeat-last 는 어디서나 ~88 %, hybrid 는 `<5s` 에서 mpc 수준(43 %)으로 라우팅 |

수치는 전부 tracked 결과 파일에서 읽으며 없는 값은 "n/a" (추정 없음).

---

# 안전 게이트 (2026-09-09) — 승인 불필요 범위 선검증

## 8. Task 0 — 처방별 변경 범위 분류

배치를 막는 것은 §S.7 의 **총량 게이트 실패**(총 rebuffering A1 6.4 s → 18–37 s).
§S.7 이 제안한 세 처방이 팀 파일 수정을 실제로 요구하는지 코드로 확인했다.

queue serve 결정은 `rl_policy.sample_speculative` 의 `if self._speculative_queue:`
브랜치(`rl_policy.py:905-930`)에 있다. `rl_policy` 는 AGENTS.md 상 **하드
read-only**. 그러나 그 브랜치는 `validate_speculative_observation(observed_state=
state, …)` 를 **모듈 전역 이름**으로 호출하고 (`rl_policy.py:12` 에서 import),
`state[1,-1]·BUFFER_NORM_FACTOR(10)` = serve 시점의 실제 버퍼(초)다. 따라서
serve 게이트는 `drafter_select.py`/`decision_trace.py`/`nan_probe.py` 와 동일한
monkeypatch 패턴으로 **abr_spec/ 에서 가로챌 수 있다** — 팀 파일·`speculative/`
무수정.

| 처방 | 구현 위치 후보 | abr_spec/ 내부 가능? | clean 구현 시 팀 파일 | 대안 |
|---|---|---|---|---|
| **1. serve 시점 버퍼 재검사** | serve 브랜치, 또는 그것이 호출하는 `validate_speculative_observation` | **가능** — `abr_spec/serve_gate.py` 가 `rl_policy.validate_speculative_observation` 참조를 래핑, 현재 버퍼 < floor 이면 `valid=False, reason='buffer'` → 기존 로직이 queue clear + LLM fallback. **프로토타입 검증**(19.9 s→통과, 3.0 s→거부) + trace-5 스모크(게이트 미발동 시 결과 완전 동일) | `acceptance.py` 에 `buffer_floor_seconds` 파라미터(soyun write-scope, 하위호환) + `rl_policy.py` 1줄 pass-through + `run_plm.py` CLI ~3줄 | monkeypatch 를 영구 배포 경로로 (fork 가 `--speculative-drafter` 를 이미 이 방식으로 주입) |
| **2. <5s 구간 queue serve 금지** | 처방 1 과 동일 지점·메커니즘 | **가능** — 처방 1 에서 `--serve-buffer-floor 5.0` | 없음 (처방 1 과 통합) | — |
| **3. buffer tolerance 재조정** | `--speculative-buffer-tolerance` (기존 CLI 인자, AGENTS.md 스윕 허용) | **가능 — 코드 0줄**, run 인자만 | 없음 | — |

**분류 결론:** 세 처방 전부 팀 파일 없이 선검증 가능.
- **Task 1**: 처방 1·2 → `abr_spec/serve_gate.py` (신규) + `run_wrapped.py`
  `--serve-buffer-floor` / `--serve-gate-check-predicted` 플래그. 처방 3 →
  `--speculative-buffer-tolerance` 강화.
- **Task 3**: Task 1 이 효과를 검증하면 first-class CLI 플래그로 승격하는 최소
  diff 를 [[CHANGE_REQUEST_SERVE_TIME_GATE]] 로 요청. monkeypatch 영구화 대안도
  함께 (승인 없이도 기능 확보됨).

### 8.1 동결 (이번 실험)

- **Freeze commit:** `6613ee26d28cae14f858a64653c640ec54e36d56` — `feat(soyun): serve_gate.py + --serve-buffer-floor`.
- freeze 직전 변경(둘 다 abr_spec/, 팀 파일 무수정): `serve_gate.py` 신규,
  `run_wrapped.py` 플래그 2개(+manifest 기록). 40-test 통과, `run_drafter_ablation.sh
  --dry-run` clean, drafter_ab 실행경로(ablation freeze `0d137ce`) 대비 diff empty
  — 즉 게이트 off (`--serve-buffer-floor 0`, 기본값) 시 경로 불변.
- 실행경로 파일(`run_wrapped.py`, `decision_trace.py`, `drafter_select.py`,
  `serve_gate.py`, `plm_special/speculative/*`)은 이 실험 중 수정 없음.
