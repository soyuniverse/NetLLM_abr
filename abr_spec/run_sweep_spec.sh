#!/usr/bin/env bash
# abr_spec/run_sweep_spec.sh -- speculative-parameter sweep on top of BASELINE6.
#
# soyun / speculative inference.  Every run goes through abr_spec/run_wrapped.py
# (no upstream file touched, no run_plm.py subprocess) and lands under
# results/soyun/$RID/<phase>/.  One process per phase keeps CUDA state clean.
#
# Question this sweep answers: can the parameters I own (draft horizon k,
# verification mode, buffer/state tolerance) lift the queue-serve share q from
# BASELINE6's measured 6.28 % to the 14.63 % that merely breaks even, or the
# 31.43 % that would buy the 24 % speedup?  If they cannot, this sweep is the
# evidence for saying so.
#
# BASELINE6 measurements this is built on (results/soyun/baseline6_20260902/):
#   E (k=3 greedy) = 0.918x, acceptance 6.14 %, q 6.28 %
#   cost model      mean_latency(q) = (1-q)*58.808 + q*0.832   [reproduces 0.916x]
#   break-even q = 14.63 %,  1.24x needs q = 31.43 %
#   fallbacks 268, of which 236 (88 %) are buffer mismatches, 32 state, 0 return
#   queue supply: 0.160 entries left per verify call, only 44.5 % ever consumed
#
# Axes
#   S0        confound removal: verification-mode sample (A1 is 100 % sampling,
#             so this isolates speculation's share of E's -3.13 % QoE)
#   S1-S4     draft horizon k in {1,2,4,5}, OFAT, everything else = E
#   S5-S8     tolerance, OFAT, everything else = E.  Buffer gets three points
#             because 88 % of the queue discards are buffer mismatches; state
#             gets one.  **Return tolerance is deliberately NOT swept: E and F
#             both recorded return_mismatch_fallbacks = 0, so no queue entry has
#             ever been discarded on the return check and widening it cannot
#             change q.**
#
# All runs keep --decision-trace: q, accepted-prefix length and the fallback
# reason split are only recoverable from the per-decision JSONL.
#
# Usage
#   bash abr_spec/run_sweep_spec.sh --dry-run     # print commands + ETA, run nothing
#   tmux new -s sweepspec -d
#   tmux send-keys -t sweepspec 'bash abr_spec/run_sweep_spec.sh' C-m
#   RUNS="s5_buftol2 s6_buftol4" bash abr_spec/run_sweep_spec.sh   # subset
#
# Re-running is safe: a phase whose result.json already says "status": "ok" is
# skipped, so an interrupted sweep resumes where it stopped.  A failed phase is
# recorded and the sweep continues; the script exits non-zero at the end.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

RID="${RID:-sweep_spec_$(date +%Y%m%d)}"
BASE_RID="${BASE_RID:-baseline6_20260902}"     # --baseline-run-id  == BASELINE6's A1
BASE_PHASE="${BASE_PHASE:-a1_all_off}"         # --baseline-phase   == A1
CKPT="${CKPT:-official_abr_r128}"
TRACE_NUM="${TRACE_NUM:-100}"
PY="${PY:-$REPO/.venv/bin/python}"
RUNS="${RUNS:-}"                               # optional whitelist of phase names
LOGDIR="$REPO/results/soyun/$RID/logs"

DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

# ---- $COMMON: byte-for-byte the BASELINE6 arguments ------------------------
# seed / trace / trace-num / video / fixed-order / LoRA rank / fp16 / model dir
# are all identical, otherwise nothing here is comparable to A1 or to E.
COMMON=(--test --fp16 --seed 1 --plm-type llama --plm-size base --rank 128
        --plm-dir ../downloaded_plms/llama/base
        --model-dir ../downloaded_plms/ft_plms/try_llama2_7b
        --trace fcc-test --trace-num "$TRACE_NUM" --video video1 --fixed-order
        --device cuda:0 --device-out cuda:0)

# E's configuration, which every sweep point varies exactly one knob away from.
E_ARGS=(--temporal-selector none --token-selector none
        --speculative-draft-steps 3 --speculative-verification-mode greedy)

# ---- the sweep: name | expected mean latency (ms) | args --------------------
# Expected latency drives the ETA only.  L(k) = 50.329 + 1.50*k is fitted on the
# two BASELINE6 points L(0)=50.329 (A1) and L(3)=54.815 (E).  The tolerance runs
# are quoted at E's measured latency, which is the pessimistic end: loosening a
# tolerance can only raise q, and a higher q lowers latency.
SWEEP=(
  "s0_mode_sample|54.815|--temporal-selector none --token-selector none --speculative-draft-steps 3 --speculative-verification-mode sample"
  "s1_k1|51.83|--temporal-selector none --token-selector none --speculative-draft-steps 1 --speculative-verification-mode greedy"
  "s2_k2|53.33|--temporal-selector none --token-selector none --speculative-draft-steps 2 --speculative-verification-mode greedy"
  "s3_k4|56.33|--temporal-selector none --token-selector none --speculative-draft-steps 4 --speculative-verification-mode greedy"
  "s4_k5|57.83|--temporal-selector none --token-selector none --speculative-draft-steps 5 --speculative-verification-mode greedy"
  "s5_buftol2|54.815|${E_ARGS[*]} --speculative-buffer-tolerance 2.0"
  "s6_buftol4|54.815|${E_ARGS[*]} --speculative-buffer-tolerance 4.0"
  "s7_buftol8|54.815|${E_ARGS[*]} --speculative-buffer-tolerance 8.0"
  "s8_statetol05|54.815|${E_ARGS[*]} --speculative-state-tolerance 0.5"
)

selected() {        # selected <phase>  -> 0 if it should run
  [ -z "$RUNS" ] && return 0
  printf '%s\n' $RUNS | grep -qx "$1"
}

done_already() {    # done_already <phase>  -> 0 if a previous run finished ok
  local f="$REPO/results/soyun/$RID/$1/result.json"
  [ -f "$f" ] && grep -q '"status": "ok"' "$f"
}

# ---------------------------------------------------------------- dry run ----
if [ "$DRY" -eq 1 ]; then
  echo "DRY RUN -- nothing is executed."
  echo
  echo "RID          = $RID"
  echo "baseline     = --baseline-run-id $BASE_RID --baseline-phase $BASE_PHASE"
  echo "checkpoint   = $CKPT"
  echo "python       = $PY"
  echo "logs         = results/soyun/$RID/logs/<phase>.log  (+ driver.log)"
  echo "traces       = $TRACE_NUM"
  echo
  if [ -f "$REPO/results/soyun/$BASE_RID/manifest.json" ]; then
    echo "preflight: baseline manifest found (results/soyun/$BASE_RID/manifest.json)"
  else
    echo "preflight: !! results/soyun/$BASE_RID/manifest.json MISSING -- speedup would be null"
  fi
  echo "preflight: python $([ -x "$PY" ] && echo OK || echo '!! MISSING')  $PY"
  echo
  total=0
  n=0
  for entry in "${SWEEP[@]}"; do
    name="${entry%%|*}"; rest="${entry#*|}"
    est="${rest%%|*}"; args="${rest#*|}"
    state="RUN"
    if ! selected "$name"; then state="SKIP (not in RUNS)"
    elif done_already "$name"; then state="SKIP (already ok)"
    fi
    wall=$(awk -v l="$est" 'BEGIN{printf "%.0f", 4.7*l + 3.7}')
    echo "--- $name   [$state]   est ${wall}s (mean latency ${est} ms x 4700 decisions + 3.7 s load)"
    echo "$PY abr_spec/run_wrapped.py \\"
    echo "  --run-id $RID --phase $name --ckpt-name $CKPT \\"
    echo "  --baseline-run-id $BASE_RID --baseline-phase $BASE_PHASE \\"
    echo "  --decision-trace \\"
    echo "  -- ${COMMON[*]} \\"
    echo "     $args"
    echo
    if [ "$state" = "RUN" ]; then
      total=$(awk -v t="$total" -v w="$wall" 'BEGIN{print t+w}')
      n=$((n+1))
    fi
  done
  awk -v t="$total" -v n="$n" 'BEGIN{
    printf "TOTAL: %d run(s), est %.0f s = %.1f min = %.2f h\n", n, t, t/60, t/3600
    printf "cost @ $0.228/h  ~ $%.3f   (conservative 2x ceiling ~ $%.3f)\n", 0.228*t/3600, 2*0.228*t/3600
  }'
  echo
  echo "Notes"
  echo " - return tolerance is NOT swept: BASELINE6 recorded"
  echo "   return_mismatch_fallbacks = 0 in both E and F, so no queue entry has"
  echo "   ever been discarded on the return check; widening it cannot move q."
  echo " - k is capped at 5 upstream (RobustMPCDraftGenerator requires"
  echo "   1 <= max_horizon <= 5, mpc_draft.py:66-72), so k=5 is the top of the axis."
  echo " - the MPC brute force enumerates 6^k candidates, so its CPU cost rises"
  echo "   ~6x per step (0.164 ms/decision at k=3). decisions.jsonl measures it"
  echo "   separately (mpc_rollout_cpu_ms) at every k."
  echo " - ETA model is fitted on 2 points; treat it as +-20 %."
  exit 0
fi

# ------------------------------------------------------------------- run ----
mkdir -p "$LOGDIR"
FAILED=()
RAN=0

echo "RID=$RID  BASELINE=$BASE_RID/$BASE_PHASE  TRACE_NUM=$TRACE_NUM  started $(date -Is)"

for entry in "${SWEEP[@]}"; do
  name="${entry%%|*}"; rest="${entry#*|}"; args="${rest#*|}"

  if ! selected "$name"; then
    echo "=== [$(date -Is)] phase=$name SKIPPED (not in RUNS) ==="
    continue
  fi
  if done_already "$name"; then
    echo "=== [$(date -Is)] phase=$name SKIPPED (already completed ok) ==="
    continue
  fi

  echo "=== [$(date -Is)] phase=$name START ==="
  rc=0
  "$PY" abr_spec/run_wrapped.py \
    --run-id "$RID" --phase "$name" --ckpt-name "$CKPT" \
    --baseline-run-id "$BASE_RID" --baseline-phase "$BASE_PHASE" \
    --decision-trace \
    -- "${COMMON[@]}" $args 2>&1 | tee "$LOGDIR/$name.log" || rc=$?
  echo "=== [$(date -Is)] phase=$name rc=$rc ==="
  if [ "$rc" -ne 0 ]; then
    echo "FAILED: phase $name (rc=$rc) -- continuing with the remaining phases"
    FAILED+=("$name")
  fi
  RAN=$((RAN+1))
done

echo
echo "SWEEP DONE $(date -Is): $RAN run(s) executed -> results/soyun/$RID/"
if [ "${#FAILED[@]}" -gt 0 ]; then
  echo "FAILURES: ${FAILED[*]}"
  exit 1
fi
echo "no failures"
