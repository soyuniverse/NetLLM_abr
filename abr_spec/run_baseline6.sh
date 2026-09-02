#!/usr/bin/env bash
# abr_spec/run_baseline6.sh -- README's 6 evaluation conditions at --trace-num 100.
#
# soyun / speculative inference.  Every phase goes through abr_spec/run_wrapped.py
# (no upstream file is touched, no run_plm.py subprocess) and lands under
# results/soyun/$RID/<phase>/.  One process per phase keeps CUDA state clean.
#
# Order: A is run FIRST and LAST (a1_all_off / a2_all_off).  The a1-vs-a2 gap is
# the measurement-noise floor for this box; any latency difference smaller than
# it is not a real effect.  a1_all_off is the speedup reference for every phase.
#
# E and F additionally emit results/soyun/$RID/<phase>/decisions.jsonl -- one JSON
# line per ABR decision (see abr_spec/decision_trace.py).
#
#   tmux new -s baseline6 -d
#   tmux send-keys -t baseline6 'bash abr_spec/run_baseline6.sh 2>&1 | tee -a results/soyun/<RID>/logs/driver.log' C-m
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
RID="${RID:-baseline6_$(date +%Y%m%d)}"
TRACE_NUM="${TRACE_NUM:-100}"
PY="${PY:-$REPO/.venv/bin/python}"
LOGDIR="$REPO/results/soyun/$RID/logs"
BASE_PHASE=a1_all_off
mkdir -p "$LOGDIR"

# README $COMMON.  --model-dir points at downloaded_plms/ft_plms/try_llama2_7b
# (soyun-writable, gitignored) instead of README's data/ft_plms/try_llama2_7b:
# the official r=128 ABR checkpoint was relocated there, byte-identical
# (docs/soyun/SMOKE_OFFICIAL_CKPT.md sec.1).  Everything else is verbatim.
COMMON=(--test --fp16 --seed 1 --plm-type llama --plm-size base --rank 128
        --plm-dir ../downloaded_plms/llama/base
        --model-dir ../downloaded_plms/ft_plms/try_llama2_7b
        --trace fcc-test --trace-num "$TRACE_NUM" --video video1 --fixed-order
        --device cuda:0 --device-out cuda:0)

FAILED=()
# PHASES="d_temporal_token e_speculative" restricts the run to those phases
# (used to resume a matrix after a phase failed).
PHASES="${PHASES:-}"

phase() {           # phase() <phase-name> <trace|notrace> -- <run_plm args...>
  local name="$1" trace="$2"; shift 3
  if [ -n "$PHASES" ] && ! printf '%s\n' $PHASES | grep -qx "$name"; then
    echo "=== [$(date -Is)] phase=$name SKIPPED (not in PHASES) ==="
    return 0
  fi
  local wrapper=(--run-id "$RID" --phase "$name" --ckpt-name official_abr_r128
                 --baseline-run-id "$RID" --baseline-phase "$BASE_PHASE")
  [ "$trace" = trace ] && wrapper+=(--decision-trace)
  echo "=== [$(date -Is)] phase=$name trace=$trace ==="
  "$PY" abr_spec/run_wrapped.py "${wrapper[@]}" -- "${COMMON[@]}" "$@" \
    2>&1 | tee "$LOGDIR/$name.log"
  local rc=${PIPESTATUS[0]}
  echo "=== [$(date -Is)] phase=$name rc=$rc ==="
  # A failed condition must NOT cancel the rest of the matrix: A2 has to run last
  # for the a1-vs-a2 latency-noise floor to mean anything.  Failures are recorded
  # and the driver exits non-zero at the end.
  if [ "$rc" -ne 0 ]; then
    echo "FAILED: phase $name (rc=$rc) -- continuing with the remaining phases"
    FAILED+=("$name")
  fi
  return 0
}

echo "RID=$RID  TRACE_NUM=$TRACE_NUM  started $(date -Is)"

phase a1_all_off        notrace -- --temporal-selector none        --token-selector none            --speculative-draft-steps 0
phase b_temporal        notrace -- --temporal-selector event-aware --token-selector none            --speculative-draft-steps 0
phase c_recent_token    notrace -- --temporal-selector none        --token-selector recent-timestep --selector-history-steps 5 --speculative-draft-steps 0
phase d_temporal_token  notrace -- --temporal-selector event-aware --token-selector intra-timestep  --speculative-draft-steps 0
phase e_speculative     trace   -- --temporal-selector none        --token-selector none            --speculative-draft-steps 3 --speculative-verification-mode greedy
phase f_all_three       trace   -- --temporal-selector event-aware --token-selector intra-timestep  --speculative-draft-steps 3 --speculative-verification-mode greedy
phase a2_all_off        notrace -- --temporal-selector none        --token-selector none            --speculative-draft-steps 0

if [ "${#FAILED[@]}" -gt 0 ]; then
  echo "MATRIX DONE WITH FAILURES $(date -Is): ${FAILED[*]}  -> results/soyun/$RID/"
  exit 1
fi
echo "ALL PHASES DONE $(date -Is)  -> results/soyun/$RID/"
