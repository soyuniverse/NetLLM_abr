#!/usr/bin/env bash
# abr_spec/run_serve_gate.sh -- DRAFTER_ABLATION Task 1: serve-time buffer gate.
#
# soyun / speculative inference.  Every run goes through abr_spec/run_wrapped.py
# (no upstream file touched) and lands under results/soyun/$RID/<phase>/.
#
# WHY
# ---
# DRAFTER_ABLATION.md section S.7: the drafter replacement clears speedup 1.24x
# but fails the total-rebuffering gate.  Cause (S.6): a few queue entries execute
# after the buffer drained below ~5 s.  abr_spec/serve_gate.py refuses a queued
# action when the buffer is low -> one real LLM call instead.  This measures
# whether that fixes the total gate without hurting the incidence gate or the
# speedup, and traces the gate-strength <-> speedup trade-off (Task 2).
#
# FREEZE
# ------
# Execution path frozen at the serve_gate.py commit.  Do not edit run_wrapped.py,
# decision_trace.py, drafter_select.py, serve_gate.py or plm_special/speculative/
# until this finishes.
#
# Controls are the drafter_ab_20260908 phases m2/m3/m4/m5 (no re-run).
# Baseline for speedup: drafter_ab_20260908/a1_all_off (same instance, 80.627 ms).
#
#   bash abr_spec/run_serve_gate.sh --dry-run
#   tmux new -s servegate -d ; tmux send-keys -t servegate 'bash abr_spec/run_serve_gate.sh' C-m
#   RUNS="g_repeat_k3_f5" bash abr_spec/run_serve_gate.sh
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
PY="${PY:-$REPO/.venv/bin/python}"
RID="${RID:-serve_gate_20260909}"
BASE_RID="${BASE_RID:-drafter_ab_20260908}"
BASE_PHASE="${BASE_PHASE:-a1_all_off}"
CKPT="${CKPT:-official_abr_r128}"
TRACE_NUM="${TRACE_NUM:-100}"
RUNS="${RUNS:-}"
LOGDIR="$REPO/results/soyun/$RID/logs"

DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

COMMON=(--test --fp16 --seed 1 --plm-type llama --plm-size base --rank 128
        --plm-dir ../downloaded_plms/llama/base
        --model-dir ../downloaded_plms/ft_plms/try_llama2_7b
        --trace fcc-test --trace-num "$TRACE_NUM" --video video1 --fixed-order
        --device cuda:0 --device-out cuda:0)
SEL_NONE=(--temporal-selector none --token-selector none)
TOL=(--speculative-buffer-tolerance 1.0 --speculative-state-tolerance 0.25
     --speculative-return-tolerance 0.01)

# name | wrapper-extra | run_plm-extra
#   wrapper-extra: --speculative-drafter ... [--serve-buffer-floor N] [--serve-gate-check-predicted]
#   run_plm-extra: draft steps / verification mode / tolerances
PHASES=(
  # -- serve gate, floor 5 s, observed buffer -------------------------------
  "g_repeat_k3_f5|--speculative-drafter repeat-last --serve-buffer-floor 5.0|--speculative-draft-steps 3 --speculative-verification-mode sample ${TOL[*]}"
  "g_hybrid_k3_f5|--speculative-drafter hybrid --speculative-hybrid-buffer-threshold 5.0 --speculative-hybrid-cv-threshold 0.30 --serve-buffer-floor 5.0|--speculative-draft-steps 3 --speculative-verification-mode sample ${TOL[*]}"
  "g_repeat_k5_f5|--speculative-drafter repeat-last --serve-buffer-floor 5.0|--speculative-draft-steps 5 --speculative-verification-mode sample ${TOL[*]}"
  "g_hybrid_k5_f5|--speculative-drafter hybrid --speculative-hybrid-buffer-threshold 5.0 --speculative-hybrid-cv-threshold 0.30 --serve-buffer-floor 5.0|--speculative-draft-steps 5 --speculative-verification-mode sample ${TOL[*]}"
  # -- gate-strength sweep on repeat-last k3 (Task 2 trade-off curve) --------
  "g_repeat_k3_f3|--speculative-drafter repeat-last --serve-buffer-floor 3.0|--speculative-draft-steps 3 --speculative-verification-mode sample ${TOL[*]}"
  "g_repeat_k3_f8|--speculative-drafter repeat-last --serve-buffer-floor 8.0|--speculative-draft-steps 3 --speculative-verification-mode sample ${TOL[*]}"
  # -- predicted-buffer variant (gate on the queued entry's own forecast) ---
  "g_repeat_k3_f5_pred|--speculative-drafter repeat-last --serve-buffer-floor 5.0 --serve-gate-check-predicted|--speculative-draft-steps 3 --speculative-verification-mode sample ${TOL[*]}"
  # -- prescription 3: tighter buffer tolerance, no serve gate --------------
  "t_repeat_k3_btol0p5|--speculative-drafter repeat-last|--speculative-draft-steps 3 --speculative-verification-mode sample --speculative-buffer-tolerance 0.5 --speculative-state-tolerance 0.25 --speculative-return-tolerance 0.01"
)

selected() { [ -z "$RUNS" ] && return 0; printf '%s\n' $RUNS | grep -qx "$1"; }
done_already() { local f="$REPO/results/soyun/$RID/$1/result.json"; [ -f "$f" ] && grep -q '"status": "ok"' "$f"; }

if [ "$DRY" -eq 1 ]; then
  echo "DRY RUN"
  pending=$(git -C "$REPO" status --porcelain -- \
      adaptive_bitrate_streaming/plm_special/speculative abr_spec | wc -l)
  echo "frozen at $(git -C "$REPO" rev-parse --short HEAD)  (${pending} uncommitted under frozen paths -- must be 0)"
  echo "RID=$RID  baseline=$BASE_RID/$BASE_PHASE  traces=$TRACE_NUM"
  for entry in "${PHASES[@]}"; do
    name="${entry%%|*}"; rest="${entry#*|}"; wrap="${rest%%|*}"; pass="${rest#*|}"
    st="RUN"; selected "$name" || st="SKIP (not in RUNS)"; done_already "$name" && st="SKIP (ok)"
    echo "--- $name  [$st]"
    echo "  wrapper: $wrap"
    echo "  run_plm: $pass"
  done
  exit 0
fi

mkdir -p "$LOGDIR"
FAILED=(); RAN=0
echo "RID=$RID started $(date -Is)  frozen at $(git rev-parse --short HEAD)"
for entry in "${PHASES[@]}"; do
  name="${entry%%|*}"; rest="${entry#*|}"; wrap="${rest%%|*}"; pass="${rest#*|}"
  if ! selected "$name"; then echo "=== $name SKIPPED (not in RUNS) ==="; continue; fi
  if done_already "$name"; then echo "=== $name SKIPPED (ok) ==="; continue; fi
  echo "=== [$(date -Is)] $name START ==="
  rc=0
  "$PY" abr_spec/run_wrapped.py \
    --run-id "$RID" --phase "$name" --ckpt-name "$CKPT" \
    --baseline-run-id "$BASE_RID" --baseline-phase "$BASE_PHASE" \
    --decision-trace $wrap \
    -- "${COMMON[@]}" "${SEL_NONE[@]}" $pass 2>&1 | tee "$LOGDIR/$name.log" || rc=$?
  echo "=== [$(date -Is)] $name rc=$rc ==="
  [ "$rc" -ne 0 ] && FAILED+=("$name")
  RAN=$((RAN+1))
done
echo "DONE $(date -Is): $RAN run(s)"
[ "${#FAILED[@]}" -gt 0 ] && { echo "FAILURES: ${FAILED[*]}"; exit 1; }
echo "no failures"
