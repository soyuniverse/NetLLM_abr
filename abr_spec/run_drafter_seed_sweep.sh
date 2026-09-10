#!/usr/bin/env bash
# abr_spec/run_drafter_seed_sweep.sh -- G1: drafter ablation across seeds 2-4.
#
# soyun / speculative inference.  [[RNG_CONTAMINATION_AUDIT]] §3 / [[DRAFTER_ABLATION]]
# §9.9, §9.12: the ablation's speedup/q/1-step results are contamination-robust,
# but total rebuffering / QoE are dominated by 1-2 outlier traces per seed and
# their sign is not stable at n=1.  This runs A1 + m2/m3/m4/m6 at seeds {2,3,4}
# (seed 1 reused from drafter_ab_20260908; m5 s2-4 reused from
# serve_gate_20260909/m5_ctrl_s{2,3,4}, which are byte-identical -- gate patched:false)
# so QoE/rebuffering can be reported as mean +- std (n=4).
#
# Exec path == ablation freeze 0d137ce for speculative/ + decision_trace +
# drafter_select; run_wrapped.py is +34 lines additive argparse (no behaviour
# change at the defaults, verified git diff).  Manifests record git_commit.
#
# Usage:  bash abr_spec/run_drafter_seed_sweep.sh            # all, resumes
#         RUNS="m2_s2 m2_s3" bash abr_spec/run_drafter_seed_sweep.sh
#         bash abr_spec/run_drafter_seed_sweep.sh --dry-run
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
RID="${RID:-drafter_seed_sweep_20260910}"
BASE_RID="${BASE_RID:-drafter_ab_20260908}"
BASE_PHASE="${BASE_PHASE:-a1_all_off}"
CKPT="${CKPT:-official_abr_r128}"
PY="${PY:-$REPO/.venv/bin/python}"
RUNS="${RUNS:-}"
LOGDIR="$REPO/results/soyun/$RID/logs"
mkdir -p "$LOGDIR"
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1

COMMON=(--test --fp16 --plm-type llama --plm-size base --rank 128
        --plm-dir ../downloaded_plms/llama/base
        --model-dir ../downloaded_plms/ft_plms/try_llama2_7b
        --trace fcc-test --trace-num 100 --video video1 --fixed-order
        --device cuda:0 --device-out cuda:0)
TOL=(--speculative-buffer-tolerance 1.0
     --speculative-state-tolerance 0.25
     --speculative-return-tolerance 0.01)
SEL_NONE=(--temporal-selector none --token-selector none)
SEL_D=(--temporal-selector event-aware --token-selector intra-timestep)

# base phase | drafter | wrapper extra | run_plm extra (selectors + k)
BASES=(
  "a1|mpc||${SEL_NONE[*]} --speculative-draft-steps 0"
  "m2|repeat-last||${SEL_NONE[*]} --speculative-draft-steps 3 --speculative-verification-mode sample ${TOL[*]}"
  "m3|hybrid|--speculative-hybrid-buffer-threshold 5.0 --speculative-hybrid-cv-threshold 0.30|${SEL_NONE[*]} --speculative-draft-steps 3 --speculative-verification-mode sample ${TOL[*]}"
  "m4|repeat-last||${SEL_NONE[*]} --speculative-draft-steps 5 --speculative-verification-mode sample ${TOL[*]}"
  "m6|repeat-last||${SEL_D[*]} --speculative-draft-steps 3 --speculative-verification-mode sample ${TOL[*]}"
)
SEEDS=(2 3 4)

selected() { [ -z "$RUNS" ] && return 0; printf '%s\n' $RUNS | grep -qx "$1"; }
done_already() {
  local f="$REPO/results/soyun/$RID/$1/result.json"
  [ -f "$f" ] && grep -q '"status": "ok"' "$f"
}

for entry in "${BASES[@]}"; do
  IFS='|' read -r base drafter wrap pass <<< "$entry"
  for s in "${SEEDS[@]}"; do
    name="${base}_s${s}"
    selected "$name" || continue
    done_already "$name" && { echo "SKIP $name (ok)"; continue; }
    echo "=== $name (drafter=$drafter seed=$s) ==="
    if [ "$DRY" -eq 1 ]; then
      echo "$PY abr_spec/run_wrapped.py --run-id $RID --phase $name --ckpt-name $CKPT \\"
      echo "  --baseline-run-id $BASE_RID --baseline-phase $BASE_PHASE --decision-trace \\"
      echo "  --speculative-drafter $drafter $wrap -- ${COMMON[*]} --seed $s $pass"
      continue
    fi
    # shellcheck disable=SC2086
    "$PY" abr_spec/run_wrapped.py \
      --run-id "$RID" --phase "$name" --ckpt-name "$CKPT" \
      --baseline-run-id "$BASE_RID" --baseline-phase "$BASE_PHASE" \
      --decision-trace \
      --speculative-drafter "$drafter" $wrap \
      -- "${COMMON[@]}" --seed "$s" $pass \
      2>&1 | tee "$LOGDIR/$name.log"
  done
done
echo "=== drafter seed sweep done ==="
