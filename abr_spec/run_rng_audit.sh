#!/usr/bin/env bash
# abr_spec/run_rng_audit.sh -- does RNG contamination move the drafter-ablation verdict?
#
# soyun / speculative inference.  [[TRAJECTORY_DIVERGENCE]] / [[NEEDS_UPSTREAM]] #6:
# test.py seeds the sampling RNG ONCE for all 100 traces, so any per-trace
# difference in RNG-draw count (verify calls draw k, queue serves draw 0,
# fallbacks draw 1) drifts every later trace's sampling.  The serve-gate 4/4
# turned out to be a contamination artefact (§9.11).  This re-runs the two
# anchor phases of drafter_ab_20260908 -- m1a (mpc control) and m2 (repeat-last
# k3, the "speedup 1.0x broken" headline) -- with abr_spec/reseed_per_episode.py
# so every trace starts from seed+trace_i.  If the m2-vs-m1a direction (speedup
# up, rebuffering up) survives, the ablation verdict is contamination-robust.
#
# Exec path is byte-identical to the ablation freeze 0d137ce for
# speculative/ + decision_trace.py + drafter_select.py; run_wrapped.py is +34
# lines of additive argparse (serve-gate/probe), no behaviour change at the
# defaults (verified: git diff 0d137ce HEAD).
#
# Usage:  bash abr_spec/run_rng_audit.sh            # runs both phases, resumes
#         RUNS="m2_repeat_k3_reseed" bash abr_spec/run_rng_audit.sh
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
RID="${RID:-rng_audit_20260909}"
BASE_RID="${BASE_RID:-drafter_ab_20260908}"     # same-instance A1 (driver 570), latency denominator
BASE_PHASE="${BASE_PHASE:-a1_all_off}"
CKPT="${CKPT:-official_abr_r128}"
PY="${PY:-$REPO/.venv/bin/python}"
RUNS="${RUNS:-}"
LOGDIR="$REPO/results/soyun/$RID/logs"
mkdir -p "$LOGDIR"

COMMON=(--test --fp16 --seed 1 --plm-type llama --plm-size base --rank 128
        --plm-dir ../downloaded_plms/llama/base
        --model-dir ../downloaded_plms/ft_plms/try_llama2_7b
        --trace fcc-test --trace-num 100 --video video1 --fixed-order
        --device cuda:0 --device-out cuda:0)
SEL_NONE=(--temporal-selector none --token-selector none)
TOL=(--speculative-buffer-tolerance 1.0
     --speculative-state-tolerance 0.25
     --speculative-return-tolerance 0.01)
SPEC=(--speculative-draft-steps 3 --speculative-verification-mode sample)

# name | --speculative-drafter value
PHASES=(
  "m1a_mpc_k3_reseed|mpc"
  "m2_repeat_k3_reseed|repeat-last"
)

selected() { [ -z "$RUNS" ] && return 0; printf '%s\n' $RUNS | grep -qx "$1"; }
done_already() {
  local f="$REPO/results/soyun/$RID/$1/result.json"
  [ -f "$f" ] && grep -q '"status": "ok"' "$f"
}

for entry in "${PHASES[@]}"; do
  name="${entry%%|*}"; drafter="${entry#*|}"
  selected "$name" || { echo "SKIP $name (not in RUNS)"; continue; }
  done_already "$name" && { echo "SKIP $name (already ok)"; continue; }
  echo "=== $name  (drafter=$drafter, reseed-per-episode) ==="
  "$PY" abr_spec/run_wrapped.py \
    --run-id "$RID" --phase "$name" --ckpt-name "$CKPT" \
    --baseline-run-id "$BASE_RID" --baseline-phase "$BASE_PHASE" \
    --decision-trace --probe reseed_per_episode \
    --speculative-drafter "$drafter" \
    -- "${COMMON[@]}" "${SEL_NONE[@]}" "${SPEC[@]}" "${TOL[@]}" \
    2>&1 | tee "$LOGDIR/$name.log"
done
echo "=== rng audit done ==="
