# SWEEP_SPEC — speculative 파라미터 스윕 (9 run + s2_k2 재실행)

**Date:** 2026-09-02 · **Author:** soyun · **Branch:** `soyun/spec-abr`
**Run:** `results/soyun/sweep_spec_20260902/` · **Baseline:** `results/soyun/baseline6_20260902/` A1 all-off
**GPU:** NVIDIA GeForce RTX 3090, 24 GB, driver 595.58.03 (전 phase 동일 인스턴스)

관련: [[BASELINE6]] · [[RECON_SPECULATIVE]] · [[HANDOFF]] · [[NEEDS_UPSTREAM]]

## 결론 — **[파라미터로는 불가능]**

내가 소유한 파라미터(draft 길이 k, verification mode, buffer/state tolerance)를
전부 동원해도 **본전(1.000×)에 도달하지 못한다.** 스윕 전체에서 관측된 최고 속도는
**0.965× (s3_k4)** 이고, 그마저 latency 측정 이상치다 — 토큰-비용 모형과 정합적인
값으로 다시 계산하면 **0.934× (s0)** 가 최고다. 본전에 필요한 queue-serve 비율
`q = 14.73 %` 에 대해 스윕 최대 `q` 는 **9.96 % (k=5)**, 모든 축의 최선 효과를
단순 합산한 상한조차 **11.9 %** 로 6.3 pp 부족하다. 1.24× 가속에 필요한 31.5 %는
**3배** 거리다.

각 축이 막히는 지점은 아래 §3~§6에 실측으로 정리했다. 요약하면 —

| 축 | 왜 막히는가 | 실측 근거 |
|---|---|---|
| k (draft 길이) | k 를 늘리면 `q` 는 오르지만(+1.62 pp/k) **필요 `q` 가 더 빨리 오른다**(+1.84 pp/k, context +7.6 토큰/k). 격차는 k=2..5 에서 −7.6~−8.5 pp 로 **좁혀지지 않는다**. 게다가 6^k brute-force CPU 가 k=5 에서 이미 latency 의 1.90 %(k=3의 7.2배), 추세상 k≈8 이면 MPC 계산만으로 LLM 호출 한 번을 넘는다 | §4 |
| verification mode | QoE 를 되찾아 주지만(−3.13 % → **+0.81 %**) `q` 는 +1.08 pp 뿐 | §3 |
| buffer tolerance | **완전 상쇄.** btol 1→8 에서 buffer fallback 236→43 인데 state fallback 32→191, 총 fallback 268→234 로 거의 불변. `q` 는 6.28 %→6.64 % 에서 **포화** | §5 |
| state tolerance | mismatch 32건(12 %)만 대상 → `q` +0.47 pp | §6 |

근본 원인은 BASELINE6 에서 이미 측정한 것 그대로다: **drafter 가 틀린다.**
MPC 의 1-step 일치율은 12.84 %, accepted-prefix 평균은 k=5 에서도 **0.366/5**.
tolerance 를 아무리 풀어도 *틀린 행동*이 queue 에 들어가 있으면 다음 관측이
어긋나고, 관측이 어긋나는 이유가 buffer 에서 state 로 이름만 바뀔 뿐이다.
→ **drafter 교체가 필요하다** (구현 완료: 커밋 `3964752`, `repeat-last` / `hybrid`).

---

## 1. 완료 확인

9개 phase 전부 `status: ok`, **실패 없음.**

| phase | status | wall | | phase | status | wall |
|---|---|---:|---|---|---|---:|
| `s0_mode_sample` | ok | 259.3 s | | `s5_buftol2` | ok | 261.0 s |
| `s1_k1` | ok | 267.9 s | | `s6_buftol4` | ok | 260.5 s |
| `s2_k2` | ok | 259.8 s | | `s7_buftol8` | ok | 260.8 s |
| `s3_k4` | ok | 248.8 s | | `s8_statetol05` | ok | 260.8 s |
| `s4_k5` | ok | 269.6 s | | `s2_k2` (재실행) | ok | 258.3 s |

## 2. 코드 동결 감사

`run_wrapped.py` 는 실행 **직전**에 `git rev-parse HEAD` 와 `git status --porcelain`
을 manifest 에 기록한다. 두 값을 phase 별로 뽑으면 어느 코드로 돌았는지가 확정된다.

| phase | manifest 기록 시각 (UTC) | HEAD | working tree | 실행 경로 코드 |
|---|---|---|---|---|
| `s0_mode_sample` | 01:24:37 | `17065bd` | clean | **리팩터 전** |
| `s1_k1` | 01:28:58 | `b6ebf8e` | clean | **리팩터 전** |
| `s2_k2` (원본) | 01:33:28 | `b6ebf8e` | clean | **리팩터 전** (아래 판정) |
| `s3_k4` | 01:37:49 | `3964752` | clean | 리팩터 후 |
| `s4_k5` | 01:42:00 | `3964752` | clean | 리팩터 후 |
| `s5_buftol2` | 01:46:31 | `3964752` | clean | 리팩터 후 |
| `s6_buftol4` | 01:50:54 | `3964752` | clean | 리팩터 후 |
| `s7_buftol8` | 01:55:16 | `3964752` | clean | 리팩터 후 |
| `s8_statetol05` | 01:59:39 | `3964752` | clean | 리팩터 후 |
| `s2_k2` (재실행) | 03:19:08 | `3964752` | clean | 리팩터 후 |

**s2_k2 판정: 구코드(리팩터 전) — 확정.** 근거 3가지가 일치한다.

1. manifest 기록 시각 **01:33:28** 의 `git_status_porcelain` 은
   `?? abr_spec/tests/` 와 `?? results/soyun/sweep_spec_20260902/` **둘 다 untracked
   뿐**이었다 — `adaptive_bitrate_streaming/plm_special/speculative/` 도
   `abr_spec/run_wrapped.py` 도 수정(` M`) 상태가 아니었으므로 디스크의
   `mpc_draft.py` 는 그 시점에 커밋된 `b6ebf8e` 판본 그대로였다.
2. `mpc_draft.py` 의 파일 mtime 은 **01:34:01.117** — manifest 기록보다 **33초 뒤**.
   `run_wrapped.py` 는 manifest 를 쓴 **직후** `runpy` 로 `run_plm.py` 를 실행하고,
   `run_plm.py:33` 의 `from plm_special.speculative.mpc_draft import ...` 는 그
   시점(01:33:28~29)에 이미 끝난다. torch 는 wrapper 의 seed 블록에서 먼저
   import 되므로 이 구간에 지연 요인이 없다.
3. 프로세스 시작 시각은 `01:33:26`(`ps -o lstart`), 파일 저장은 `01:34:01`.

`s0`/`s1`/`s2` 는 리팩터 전, `s3`~`s8` 은 리팩터 후로 갈린다. **즉 k 축(k=1,2 구코드 /
k=4,5 신코드)이 코드 경계를 가로지른다** — 그래서 §3의 재실행이 필요했다.

## 3-0. s2_k2 재실행 — 회귀 배터리의 end-to-end 확인

같은 설정(k=2, greedy, btol 1.0, stol 0.25)을 현재 HEAD(`3964752`)로 재실행하고
구코드 결과(`s2_k2_precheck/`)와 대조했다.

| 지표 | 구코드 `b6ebf8e` | 신코드 `3964752` | 차이 |
|---|---:|---:|---|
| QoE | 0.933198 | 0.933198 | **완전 동일** |
| bitrate (Mbps) | 0.975851 | 0.975851 | **완전 동일** |
| rebuffer total (s) | 0.24923 | 0.24923 | **완전 동일** |
| smoothness (Mbps) | 0.042426 | 0.042426 | **완전 동일** |
| acceptance_rate | 0.071938 | 0.071938 | **완전 동일** |
| q (queue-serve 비율) | 0.050851 | 0.050851 | **완전 동일** |
| queued_actions_served | 239 | 239 | **완전 동일** |
| target_plm_calls | 4461 | 4461 | **완전 동일** |
| fallback 총/buffer/state | 211 / 183 / 28 | 211 / 183 / 28 | **완전 동일** |
| drafted / accepted / corrected | 8410 / 605 / 4095 | 8410 / 605 / 4095 | **완전 동일** |
| context tokens (mean) | 140.59 | 140.59 | **완전 동일** |
| latency mean (ms) | 54.499 | 54.182 | −0.58 % |
| latency p50 / p95 (ms) | 67.123 / 68.046 | 66.532 / 67.805 | −0.88 % / −0.35 % |

**행동은 비트 단위로 동일하고 latency 만 −0.58 % 움직였다.** 궤적·counter 가
전부 일치하므로 이 차이는 코드가 아니라 타이밍이다. 다만 −0.58 % 는 BASELINE6 의
A1↔A2 기준선 0.19 % 의 **3.1배**다 — 그 0.19 % 는 **17분 간격** back-to-back 두 run
사이의 값이고, 여기는 **1시간 46분** 간격이다. 즉 **0.19 %는 근접 실행 간 기준선이고,
시간 간격이 벌어지면 그보다 큰 드리프트가 정상**이다. 이 보고서에서 시간대가 다른
run 사이의 latency 차이는 **0.6 % 미만이면 유의하다고 쓰지 않는다.**

이는 `abr_spec/tests/test_drafters.py::MPCRefactorRegressionTest` 의 60케이스
tolerance-0 회귀 배터리를 실제 100-trace 추론으로 다시 확인한 것이기도 하다.

## 3. 표 — 전체 스윕

전체 컬럼은 `results/soyun/sweep_spec_20260902/analysis/sweep_table.csv`,
markdown 은 `.../analysis/sweep_tables.md`.

| run | k | mode | btol | stol | QoE | bitrate | rebuf tot(s) | smooth | lat mean/p50/p95 | speedup | acceptance | **q** | queued | prefix | fb 총/buf/st/ret | mpc cpu ms | ctx tok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A1 all-off | 0 | sample | — | — | 0.94872 | 1.01655 | 6.392 | 0.06199 | 50.329/57.954/59.032 | 1.000× | — | — | 0 | — | 0/0/0/0 | — | 131.3 |
| E (BASELINE6) | 3 | greedy | 1.0 | 0.25 | 0.91904 | 0.95973 | 0.085 | 0.04062 | 54.815/67.297/68.445 | 0.918× | 6.14 % | 6.28 % | 295 | 0.180 | 268/236/32/0 | 0.164 | 148.1 |
| s0_mode_sample | 3 | **sample** | 1.0 | 0.25 | **0.95637** | 1.02997 | 7.484 | 0.06676 | 54.374/67.112/69.310 | 0.926× | 7.91 % | 7.36 % | 346 | 0.232 | 353/315/38/0 | 0.169 | 147.9 |
| s1_k1 | **1** | greedy | 1.0 | 0.25 | 0.91741 | 0.95600 | 0.249 | 0.03836 | 56.203/66.737/67.275 | 0.895× | 13.89 % | **0.00 %** | 0 | 0.139 | 0/0/0/0 | 0.076 | 132.3 |
| s2_k2 (재실행) | **2** | greedy | 1.0 | 0.25 | 0.93320 | 0.97585 | 0.249 | 0.04243 | 54.182/66.532/67.805 | 0.929× | 7.19 % | 5.09 % | 239 | 0.142 | 211/183/28/0 | 0.099 | 140.6 |
| s3_k4 | **4** | greedy | 1.0 | 0.25 | 0.91515 | 0.95836 | 2.295 | 0.04112 | 52.135/61.989/67.941 | 0.965×⚠ | 6.80 % | 7.98 % | 375 | 0.263 | 359/325/34/0 | 0.382 | 154.8 |
| s4_k5 | **5** | greedy | 1.0 | 0.25 | 0.92684 | 0.96753 | 0.000 | 0.04069 | 56.578/66.882/74.920 | 0.890× | 7.65 % | **9.96 %** | 468 | 0.366 | 414/378/36/0 | 1.321 | 161.0 |
| s5_buftol2 | 3 | greedy | **2.0** | 0.25 | 0.91344 | 0.95409 | 0.545 | 0.04015 | 54.729/67.328/68.367 | 0.920× | 5.89 % | 6.57 % | 309 | 0.173 | 236/163/73/0 | 0.174 | 148.1 |
| s6_buftol4 | 3 | greedy | **4.0** | 0.25 | 0.91322 | 0.95386 | 0.545 | 0.04014 | 54.646/67.261/68.335 | 0.921× | 5.89 % | 6.64 % | 312 | 0.173 | 234/106/128/0 | 0.170 | 148.1 |
| s7_buftol8 | 3 | greedy | **8.0** | 0.25 | 0.91322 | 0.95386 | 0.545 | 0.04014 | 54.703/67.337/68.419 | 0.920× | 5.89 % | 6.64 % | 312 | 0.173 | 234/43/191/0 | 0.173 | 148.1 |
| s8_statetol05 | 3 | greedy | 1.0 | **0.5** | 0.91893 | 0.96001 | 0.085 | 0.04100 | 54.709/67.340/68.432 | 0.920× | 6.03 % | 6.74 % | 317 | 0.177 | 242/231/11/0 | 0.174 | 148.4 |

⚠ `s3_k4` 의 latency 는 이상치다 — §4 참조. `return_mismatch_fallbacks` 는 **모든
run 에서 0** 이다(스윕 제외 근거가 재확인됨).

> **`acceptance_rate` 는 k 간 비교에 쓰면 안 된다.** 정의가
> `accepted_actions / drafted_actions` = `prefix 평균 / k` 라서 k 가 커지면 자동으로
> 작아진다(k=1 에서 13.89 %가 최고인 이유). k 축 비교는 **prefix 평균**과 **q** 로 한다.

## 4. 축 2 — draft 길이 k

| k | ctx tokens | prefix 평균 | acceptance | **q 실측** | **q 필요(본전)** | 격차 | q 필요(1.24×) | mpc cpu ms/dec | mpc 비중 | speedup 실측 | speedup 모형 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 132.3 | 0.139 | 13.89 % | **0.00 %** | 10.32 % | −10.32 pp | 27.97 % | 0.076 | 0.135 % | 0.895× | 0.898× |
| 2 | 140.7 | 0.142 | 7.19 % | 5.09 % | 12.64 % | −7.56 pp | 29.83 % | 0.099 | 0.179 % | 0.929× | 0.927× |
| 3 | 148.7 | 0.180 | 6.14 % | 6.28 % | 14.73 % | −8.45 pp | 31.51 % | 0.144 | 0.264 % | 0.918× | 0.919× |
| 4 | 155.8 | 0.263 | 6.80 % | 7.98 % | 16.52 % | −8.54 pp | 32.95 % | 0.323 | 0.620 % | 0.965×⚠ | 0.921× |
| 5 | 162.6 | 0.366 | 7.65 % | **9.96 %** | 18.15 % | −8.19 pp | 34.26 % | 1.074 | **1.900 %** | 0.890× | 0.927× |

`q 필요` 는 그 k 의 검증 호출 단가 `c_verify(k)` 로 다시 푼 값이다:
`q_parity(k) = (c_verify(k) − 50.329) / (c_verify(k) − 0.832)`.
`c_verify(k)` 는 10개 run 의 (verify context 토큰 → verify 호출 latency) 회귀
`c_verify = 33.023 + 0.1739·tokens` 로 구했다. k=4·k=5 를 제외한 8개 run 의
잔차 최대는 **0.31 ms(0.5 %)** 로 매우 타이트하다. 반면 **k=4 는 −3.34 ms(−5.9 %),
k=5 는 +2.30 ms(+3.8 %)** 로 벗어난다 — 토큰이 더 많은 k=4 가 k=3 보다 빠를 수는
없으므로 이 둘은 측정 이상치(`torch.backends.cudnn.benchmark=True` 로 인한 시퀀스
길이별 커널 재선택 / 클럭 변동)로 판정한다. **따라서 k 축의 결론은 latency 가 아니라
`q`(정확한 카운트, 타이밍 노이즈 무관)로 낸다.**

**(1) q 는 k 에 대해 단조 증가하고, 측정 범위(k≤5)에서 포화하지 않는다.**
0.00 → 5.09 → 6.28 → 7.98 → 9.96 %. 증가폭은 오히려 커진다(+1.19, +1.70, +1.98 pp).

**(2) k=1 은 구조적으로 q=0 이다.** `build_acceptance_plan` 의 결과 길이는 k=1 일 때
수용/정정 어느 쪽이든 1 이고, 그 하나를 즉시 pop 해서 실행하므로 queue 에 남는 게
없다. `target_plm_calls = 4700`(전부), `fallback = 0` 이 이를 뒷받침한다.
**k=1 은 draft block 비용만 내고 절감은 0 인 순손실 설정이다** (0.895×).

**(3) 손익분기 k 는 존재하지 않는다.** k=2..5 구간에서
`q` 는 **+1.62 pp/k**, `q 필요` 는 **+1.84 pp/k** 로 **요구가 공급보다 빨리 자란다**
(k 당 context +7.6 토큰 × 0.1739 ms/토큰 = 검증 단가 +1.33 ms/k). 격차는
−7.56 / −8.45 / −8.54 / −8.19 pp 로 **1 pp 폭 안에서 평평하고 닫히지 않는다.**
k=4→5 에서 0.35 pp 좁아진 것을 그대로 외삽해도 격차 8.19 pp 를 메우려면 **k≈28**
이 필요하다 *(추정 — 측정 범위의 5배 이상 외삽이므로 신뢰하지 말 것)*.

**(4) k=5 에서 6^k brute-force 는 이미 유의미하다.** decision 당 MPC CPU 는
0.076 → 0.099 → 0.144 → 0.323 → **1.074 ms**, latency 비중은 0.135 % → **1.900 %**
로 **k=3(0.264 %) 대비 7.2배**다. 단계당 배율은 1.28 → 1.49 → 2.24 → 3.33 으로
가팔라진다. 이 추세를 외삽하면 *(추정)* k=7 에서 약 12 ms, **k=8 에서 약 39 ms** —
LLM 호출 한 번(≈59 ms)에 육박하고 k=9 면 이를 넘는다. 즉 **코드 상한 5 가 없더라도
k 축은 본전(k≈28)에 닿기 훨씬 전에 MPC 계산 자체가 예산을 다 먹고 붕괴한다.**

> 참고: 코드 상한은 `RobustMPCDraftGenerator.__init__` 의
> `1 <= max_horizon <= 5` ([mpc_draft.py](../../adaptive_bitrate_streaming/plm_special/speculative/mpc_draft.py)).
> 위 (3)(4) 는 그 상한을 풀어도 결론이 같음을 보인 것이다.

## 5. 축 3 — buffer tolerance

| btol (s) | q | speedup | QoE | rebuffer total (s) | fb 총 | fb buffer | fb state |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1.0 (E) | 6.28 % | 0.918× | 0.91904 | 0.085 | 268 | 236 | 32 |
| 2.0 | 6.57 % | 0.920× | 0.91344 | 0.545 | 236 | 163 | 73 |
| 4.0 | 6.64 % | 0.921× | 0.91322 | 0.545 | 234 | 106 | 128 |
| 8.0 | 6.64 % | 0.920× | 0.91322 | 0.545 | 234 | **43** | **191** |

**(1) 본전에 못 간다.** `q` 는 6.28 → 6.64 % 에서 **포화**한다(btol 4 와 8 이 QoE·
bitrate·rebuffer·q 까지 완전히 동일 — 4.0 이상은 아무 것도 바꾸지 않는다).
필요한 14.73 % 의 **45 %** 수준이고, 남은 8.1 pp 를 이 축으로 벌 방법은 없다.

**(2) buffer fallback 감소분은 state fallback 증가로 상쇄된다 — 확인됨.**
btol 1→8 에서 buffer fallback 은 **236 → 43 (−193)**, state fallback 은
**32 → 191 (+159)**, 총 fallback 은 **268 → 234 (−34)** 뿐이다. **82 % 상쇄.**
btol 4→8 구간만 보면 buffer −63 / state +63 / 총합 234 로 **100 % 상쇄**다.
해석: queue 엔트리가 틀린 이유는 buffer 예측 오차가 아니라 **행동 자체가 틀려서
궤적 전체가 어긋난 것**이다. buffer 문턱을 열면 같은 엔트리가 throughput 등
다른 행에서 걸릴 뿐이다.

**(3) 파레토 — 사는 게 거의 없고 값은 치른다.**

```
QoE  0.9190 ┤ ● E (btol 1.0)
     0.9140 ┤            ● s5 (2.0)
     0.9132 ┤                 ●● s6/s7 (4.0, 8.0)   <- 여기서 정지
            └────┬─────┬─────┬─────┬──────
              6.3   6.5   6.6   ...  14.73 %(본전)  q
```
+0.36 pp 의 `q` 를 얻는 대가로 QoE −0.00582(−0.63 %), 총 rebuffering
0.085 s → 0.545 s (6.4배). 절대량은 여전히 A1(6.392 s)의 1/12 수준이라 작지만,
**얻는 것이 필요량의 4 %뿐**이라 거래 자체가 성립하지 않는다.

## 6. 축 3b — state tolerance (s8)

| stol | q | speedup | QoE | rebuffer total | fb 총 | fb buffer | fb state |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.25 (E) | 6.28 % | 0.918× | 0.91904 | 0.085 | 268 | 236 | 32 |
| 0.50 | 6.74 % | 0.920× | 0.91893 | 0.085 | 242 | 231 | 11 |

**축으로서 가치 거의 없음.** state mismatch 32건은 전체 fallback 의 12 % 이고,
그나마 `validate_speculative_observation` 이 **buffer → state → return 순으로 검사**
하므로 state tolerance 는 buffer 문턱을 통과한 결정에만 작동한다. 문턱을 2배로
열어도 state fallback 은 32 → 11 (−21), 총 fallback 268 → 242, `q` 는 **+0.47 pp**.
QoE 는 사실상 불변(−0.0001)이라 **공짜이긴 하지만 필요량의 6 %**다. 기본값 유지를
권고하되, drafter 교체 후 다시 볼 가치는 있다(그때는 queue 엔트리가 맞을 확률이
높아 tolerance 가 실제로 병목이 될 수 있다).

## 7. 축 1 — verification mode (confound 분리)

s0 은 E 와 모든 것이 같고 `--speculative-verification-mode sample` 만 다르다.
A1 은 100 % sampling 이므로 **s0 과 A1 은 행동 선택 방식이 동일한 조건**이다.

| | A1 all-off | s0 (spec + sample) | E (spec + greedy) |
|---|---:|---:|---:|
| QoE | 0.94872 | **0.95637** | 0.91904 |
| vs A1 | — | **+0.81 %** | −3.13 % |
| bitrate (Mbps) | 1.01655 | 1.02997 | 0.95973 |
| rebuffer total (s) | 6.392 | 7.484 | 0.085 |
| smoothness (Mbps) | 0.06199 | 0.06676 | 0.04062 |
| speedup | 1.000× | 0.926× | 0.918× |

**BASELINE6 의 −3.13 % 분해** (`QoE = bitrate − 4.3·rebuffer − smoothness`, 잔차 ~1e-16):

| 성분 | ΔQoE | = Δbitrate | + Δ(−4.3·rebuf) | + Δ(−smooth) |
|---|---:|---:|---:|---:|
| **speculation 몫** (s0 − A1) | **+0.00765 (+0.81 %)** | +0.01341 | −0.00100 | −0.00477 |
| **verification-mode 몫** (E − s0) | **−0.03733 (−3.90 %)** | −0.07023 | +0.00677 | +0.02614 |
| 합계 (E − A1) | −0.02968 (−3.13 %) | −0.05682 | +0.00577 | +0.02137 |

**BASELINE6 의 QoE 하락은 전부 verification mode 탓이고, speculation 자체는 QoE 를
깎지 않았다.** greedy 는 argmax 라 분포의 꼬리를 버리고 낮은 bitrate 로 쏠린다
(bitrate −0.070, 그 대가로 smoothness/rebuffer 가 좋아지지만 −4.3·rebuf 가치가
작아 순손실). BASELINE6 §3.2 에서 confound 로 표시해 둔 우려가 **실측으로 확인**됐고,
그 방향도 예상대로였다.

⚠ **acceptance 차이는 해석을 유보한다.** s0 의 acceptance 7.91 % / `q` 7.36 % 는
E 의 6.14 % / 6.28 % 보다 높지만, `sample` 모드에서는 검증 경로의 target action 자체가
확률적 추출이라 **run 간 분산이 greedy(결정론적)보다 크다. 이 스윕은 seed 1 단일
run 이므로 분산을 측정하지 않았다.** 따라서 "sample 이 q 를 1.08 pp 올린다"는
**주장하지 않는다.** 이 결론이 분산에 좌우되는 자리가 아니기도 하다 — §8에서 보듯
1.08 pp 를 다 인정해도 본전에 6.3 pp 부족하다. 분산이 필요해지면 seed 2·3·4 로
s0 과 A1 을 각각 반복(총 6 run, 약 26분)하면 되지만 **지금은 제안만 하고 실행하지
않았다.**

**권고: 이후 실험의 기본 verification mode 는 `sample`.** 근거 — (a) QoE 가
A1 대비 −3.13 % 에서 +0.81 % 로 회복되고(유효 비교), (b) 속도는 0.918× → 0.926× 로
나빠지지 않으며, (c) upstream/README 기본값과 일치해 비교 기준이 단순해진다.
greedy 는 "결정론적 재현이 필요한 회귀 테스트"용으로만 남긴다.

## 8. 파라미터 공간에서 도달 가능한 최대치

| | 값 | 설정 |
|---|---|---|
| 최대 `q` | **9.96 %** | s4_k5 (k=5, greedy) — 본전 필요치 18.15 % 의 55 % |
| 최대 speedup (실측) | **0.965×** | s3_k4 — 단 latency 이상치(§4), 신뢰 불가 |
| 최대 speedup (모형 정합) | **0.934×** | s0 (k=3, sample) |
| 그때의 QoE | **0.95637 (A1 대비 +0.81 %)** | s0 |
| 최고 QoE | 0.95637 | s0 |

**모든 축의 최선 효과를 단순 합산한 상한** *(추정 — 축 간 독립을 가정한 낙관적 상한)*:

```
k=5 의 q                9.96 pp
+ sample 모드          +1.08 pp   (분산 미측정, 낙관적으로 전액 인정)
+ buffer tolerance     +0.36 pp
+ state tolerance      +0.47 pp
= 상한                 11.87 %
필요(k=5 단가 기준)     18.15 %   -> 6.28 pp 부족
필요(k=3 단가 기준)     14.73 %   -> 2.86 pp 부족
1.24x 필요(k=5)         34.26 %   -> 22.4 pp 부족 (약 2.9배)
```

**어느 조합으로도 1.000× 를 넘지 못한다.** speculative 설정 11개 run 중 1.000× 이상은
하나도 없고, 모형 정합 speedup 은 전부 **0.898× ~ 0.934×** 밴드 안에 있다.

## 9. 교차 run — **불필요**

§8의 합산 상한이 이미 본전에 미달하므로 교차 run 은 결론을 바꿀 수 없다.
가장 유망한 조합인 `k=5 + sample + btol 4` 조차 낙관적 상한 11.9 % 로 k=5 의
필요치 18.15 % 에 6.3 pp 못 미친다. 축 간 상호작용이 초가법적(super-additive)이라
해도 필요치의 **1.5배 이상**을 만들어내야 하는데, 각 축의 실측 효과(+1.08 / +0.36 /
+0.47 pp)가 모두 1 pp 안팎이라 그럴 여지가 없다.

굳이 상한을 *계산*이 아니라 *측정*으로 못박고 싶다면 아래 1건이면 충분하다.
**권고하지 않으며 실행하지 않았다** (약 4.6분, ~$0.02):

```bash
RUNS="s9_k5_sample_btol4" bash abr_spec/run_sweep_spec.sh   # SWEEP 에 항목 추가 필요
# 또는 직접:
python abr_spec/run_wrapped.py --run-id sweep_spec_20260902 --phase s9_k5_sample_btol4 \
  --ckpt-name official_abr_r128 --baseline-run-id baseline6_20260902 \
  --baseline-phase a1_all_off --decision-trace \
  -- --test --fp16 --seed 1 --plm-type llama --plm-size base --rank 128 \
     --plm-dir ../downloaded_plms/llama/base \
     --model-dir ../downloaded_plms/ft_plms/try_llama2_7b \
     --trace fcc-test --trace-num 100 --video video1 --fixed-order \
     --device cuda:0 --device-out cuda:0 \
     --temporal-selector none --token-selector none \
     --speculative-draft-steps 5 --speculative-verification-mode sample \
     --speculative-buffer-tolerance 4.0
```
예상 *(추정)*: `q ≈ 11 %`, speedup ≈ 0.93×. 결론은 바뀌지 않는다.

**대신 다음에 돌릴 가치가 있는 것은 drafter 교체다** (커밋 `3964752` 로 구현 완료,
미실행). BASELINE6 의 사후 추정으로는 repeat-last 가 `q ≈ 35 %` → **1.31×**.
승인 시 실행할 커맨드는 §10에 적어 둔다.

## 10. 재현

```bash
# 스윕 (9 run, ~39분)
tmux new -s sweepspec -d
RID=sweep_spec_20260902 bash abr_spec/run_sweep_spec.sh
RUNS="s2_k2" bash abr_spec/run_sweep_spec.sh          # 단일 phase 재실행

# 집계 + 표
python abr_spec/build_sweep_report.py \
  --sweep-dir results/soyun/sweep_spec_20260902 \
  --baseline-dir results/soyun/baseline6_20260902 \
  --out-dir results/soyun/sweep_spec_20260902/analysis

# (승인 후) drafter 교체 실험 — 아직 실행하지 않음
python abr_spec/run_wrapped.py --run-id drafter_ab_<date> --phase repeat_last_k3 \
  --ckpt-name official_abr_r128 --baseline-run-id baseline6_20260902 \
  --baseline-phase a1_all_off --decision-trace \
  --speculative-drafter repeat-last -- <$COMMON> \
     --temporal-selector none --token-selector none \
     --speculative-draft-steps 3 --speculative-verification-mode sample
```

### 코드 동결 고지 (재현성)

**스윕 도중 실행 경로의 코드가 변경되었다.** `s0`/`s1`/`s2`(원본)는 리팩터 전
(`17065bd` / `b6ebf8e`), `s3`~`s8` 은 리팩터 후(`3964752`)로 실행됐다(§2 표).
**mpc 경로의 동일성은 두 가지로 확인했다.**

1. `abr_spec/tests/test_drafters.py::MPCRefactorRegressionTest` — 무작위 60케이스에
   대해 `actions / states / returns / timesteps / predicted_buffers /
   predicted_rewards / predicted_rebuffers / predicted_bandwidth` 를
   **tolerance 0** 으로 동결 사본(`abr_spec/tests/_reference_mpc_draft.py`)과 비교,
   전부 일치. predictor 히스토리 25스텝 진화도 일치.
2. **`s2_k2` 를 신코드로 재실행** — QoE·bitrate·rebuffer·smoothness·acceptance·
   `q`·queued·target_plm_calls·fallback 분해·drafted/accepted/corrected·context
   토큰이 **전부 완전 동일**, latency 만 −0.58 %(§3-0).

또한 `--speculative-drafter` 의 기본값은 `mpc` 이며 이 경우 `drafter_select` 는
**패치를 설치하지 않는다** — 스윕 전 run 은 upstream 구성 경로를 그대로 탔다.

## 11. 결과물 위치

```
results/soyun/sweep_spec_20260902/
  manifest.json  summary.json
  s0_mode_sample/ s1_k1/ s2_k2/ s2_k2_precheck/ s3_k4/ s4_k5/
  s5_buftol2/ s6_buftol4/ s7_buftol8/ s8_statetol05/
    {selector_metrics.json, result.json, manifest_phase.json, decisions.jsonl*}
  analysis/{sweep_table.csv, sweep_rows.json, sweep_tables.md}
  logs/<phase>.log*                      (* gitignored: .jsonl / .log)
```

---

## 12. 단가 모형 갱신 — drafter 실측점 추가 (2026-09-08)

**추가된 데이터:** [[DRAFTER_ABLATION]] 의 6 run (`drafter_ab_20260908`), 새 인스턴스
(RTX 3090, driver 570.172.08). 새 인스턴스는 절대 latency 가 BASELINE6/SWEEP 대비
~1.6× 느리므로 이 캠페인은 **자체 A1 (`a1_all_off`, latency mean 80.627 ms)** 을
분모로 쓴다. 아래 모형 파라미터도 그 A1 로 다시 푼 것이다.

### 12.1 모형의 구조는 유지되나 파라미터가 인스턴스마다 이동한다

§3.5 / §4 의 손익분기 모형:

```
mean_latency(q) = (1 − q)·c_verify + q·c_serve
q_parity        = (c_verify − c_plain) / (c_verify − c_serve)
```

| | c_plain | c_verify(k3) | c_serve | **q_parity(k3)** | q_1.24x(k3) |
|---|---:|---:|---:|---:|---:|
| BASELINE6 / SWEEP (구 인스턴스) | 50.329 | 58.808 | 0.832 | **14.63 %** | 31.43 % |
| drafter_ab (신 인스턴스, mpc m1a) | 80.627 | 89.30 | 1.77 | **9.91 %** | 27.74 % |
| drafter_ab (신, repeat-last m2) | 80.627 | 90.91 | 1.77 | **11.54 %** | 29.04 % |

context surcharge (`c_verify − c_plain`) 는 8.5 → 10.3 ms 로 비슷하지만 분모
(`c_verify − c_serve`) 가 58 → 89 ms 로 커져서 **q_parity 가 오히려 낮아졌다.**
즉 "본전 q = 14.63 %" 는 구 인스턴스 상수이고, 이 인스턴스에서는 **~11 %** 다.
**모형의 형태(q 에 대한 선형)는 두 인스턴스·세 drafter 에서 동일하게 성립한다.**

### 12.2 k=3 에서는 실측점이 모형 위에 정확히 앉는다

| run | q 실측 | speedup 모형(2-bucket) | speedup 실측 | 오차 |
|---|---:|---:|---:|---:|
| m1a mpc k3 sample | 7.36 % | 0.973× | 0.974× | +0.1 % |
| m2 repeat-last k3 | 37.77 % | 1.408× | 1.419× | +0.8 % |
| m3 hybrid k3 | 37.28 % | 1.404× | 1.413× | +0.6 % |

drafter 를 바꿔도(탐색비용 0) k=3 단가 모형은 그대로다. repeat-last 는 q 를
6 %→38 % 로 밀어 올려 **모형 곡선을 따라 speedup 1.0 과 1.24× 를 모두 넘겼다** —
파라미터로는 못 넘던 선이다.

### 12.3 k=5 에서 모형이 어긋난다 — fallback 지분이 원인 (**발견**)

| run | q 실측 | fb 지분 | 2-bucket 모형 | **3-bucket 모형** | 실측 |
|---|---:|---:|---:|---:|---:|
| m4 repeat-last k5 | 41.9 % | 21 % | 1.228× | **1.309×** | 1.306× |
| m5 hybrid k5 | 41.9 % | 21 % | 1.255× | **1.330×** | 1.326× |

2-bucket 모형(§3.5, 검증 호출 vs queue 재사용)은 **k=5 에서 speedup 을 5–6 %
과소 예측**한다. 원인: 모형이 모든 비-serve 결정을 `c_verify` 로 계산하는데,
**fallback 결정은 `c_fall`(88–93 ms) ≈ `c_plain` 수준**이지 `c_verify`(110–112 ms)
가 아니다. fallback 지분이 6–8 %(mpc, SWEEP 전체)일 때는 이 오차가 묻히지만,
**zero-search drafter 는 항상 draft 하므로**(repeat-last 는 사양상 거를 수 없다)
draft 의 절대량이 늘고 그중 buffer tolerance 를 못 넘는 비율이 21 %까지 오른다.

**→ 갱신된 단가 모형 (3-bucket):**

```
mean_latency = (n_verify·c_verify + n_fallback·c_fall + n_serve·c_serve) / N
c_fall ≈ c_plain + (draft embed + verify context) 왕복 1회 ≈ 88–93 ms (실측)
```

이 형태는 6 run 전부를 **오차 ≤ 0.4 %** 로 재현한다 (m4 1.309 vs 1.306,
m5 1.330 vs 1.326). SWEEP_SPEC 의 9 run 은 fallback 지분이 낮아 2-bucket 으로도
충분했지만, **drafter 를 바꾸는 순간 fallback 항이 필수**가 된다. 이것이
"탐색비용 0 으로 인한 단가 구조 변화" 의 정체다 — 탐색비용이 사라진 게 아니라
**draft 빈도가 올라 fallback 이 새 지배항이 됐다.**

### 12.4 결론

- q vs speedup 모형은 **살아있다.** drafter 를 바꿔도 q 만 알면 speedup 이 예측된다.
- 단 **본전 q 는 인스턴스 상수**(구 14.63 %, 신 ~11 %)이고, **k=5 부터는
  fallback 항을 넣은 3-bucket 형태**를 써야 한다.
- repeat-last 는 q 를 5× 밀어 올려 모형 곡선을 타고 1.24× 선을 넘겼다 —
  파라미터 스윕이 6.3 pp 부족했던 그 선이다 ([[DRAFTER_ABLATION]] §2).

### 12.5 serve-time 게이트 도입 후 — 모형은 성립, 단 게이트가 새 결정 유형을 만들면 항 추가

[[DRAFTER_ABLATION]] §9 의 serve-time 버퍼 게이트는 queue 엔트리를 fallback 또는
보수 서브로 강등하므로 결정 유형 구성을 바꾼다. 3-bucket 모형이 그 변화도
흡수하는지 확인했다.

| config | 게이트 mode | trip 수 | 3-bucket 예측 | 실측 | 오차 |
|---|---|---:|---:|---:|---:|
| m5_ctrl (hybrid k5, 게이트 없음) | — | — | 1.527× | 1.522× | +0.3 % |
| v_hybrid_k5_f5_cons | conservative | **3** | 1.503× | 1.499× | **+0.3 %** |
| v_hybrid_k5_f5_safe | safe-mode | **115** | 1.498× | 1.529× | **−2.0 %** |
| v_hybrid_k3_f8_safe | safe-mode | 252 | 1.533× | 1.611× | **−4.9 %** |

- **`conservative` mode: 3-bucket 그대로 성립** (오차 ≤ 0.4 %). trip 이 3개뿐이라
  강등된 결정을 `c_fall` 로 잘못 계산해도 4700 중 3개라 무시된다. 즉
  **최소 개입 게이트는 단가 모형에 보이지 않는다.**
- **`safe-mode`: 4번째 항 필요.** 버퍼 < floor 인 모든 결정을 `low_buffer_safe`
  로 서브하면 (≈ `c_serve`, LLM·PLM 없음) 115–260건이 생긴다. 이들을 `c_fall`
  로 계산하면 모형이 2–5 % 과소예측한다 (실제는 훨씬 싸다). 정확한 형태:

  ```
  mean_latency = (n_verify·c_verify + n_fallback·c_fall
                  + n_serve·c_serve + n_safe·c_serve) / N
  ```

  `low_buffer_safe` 서브는 queue serve 와 같은 비용(≈ 2 ms)이므로 사실상
  `n_serve` 에 합쳐도 된다.
- **결론:** 모형은 게이트 도입 후에도 유효하다. 게이트가 **기존 결정 유형으로만
  강등**하면(conservative·fallback) 항 추가 불필요, **새 fast-path 결정 유형을
  만들면**(safe-mode) 그 유형을 `c_serve` 급으로 한 항 더 넣으면 된다. drafter
  교체 때 fallback 항이 필수가 된 것(§12.3)과 같은 패턴 — **모형의 골격은
  유지되고 지배항만 바뀐다.**
