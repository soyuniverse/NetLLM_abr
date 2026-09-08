#!/usr/bin/env bash
# abr_spec/run_determinism_check.sh -- DRAFTER_ABLATION Task 0.2 determinism gate.
#
# soyun / speculative inference.  Runs each drafter (mpc / repeat-last / hybrid)
# twice at trace-num 5 / seed 1 / sample mode / k=3 and leaves the two traces
# under results/soyun/determinism_20260908/det_<drafter>_{a,b}/ for a byte-diff
# (see DRAFTER_ABLATION.md section 1).  A phase whose result.json is ok is skipped.
#
#   bash abr_spec/run_determinism_check.sh
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PY:-.venv/bin/python}"
RID=determinism_20260908
COMMON=(--test --fp16 --seed 1 --plm-type llama --plm-size base --rank 128
        --plm-dir ../downloaded_plms/llama/base
        --model-dir ../downloaded_plms/ft_plms/try_llama2_7b
        --trace fcc-test --trace-num 5 --video video1 --fixed-order
        --device cuda:0 --device-out cuda:0)
TAIL=(--temporal-selector none --token-selector none
      --speculative-draft-steps 3 --speculative-verification-mode sample
      --speculative-buffer-tolerance 1.0 --speculative-state-tolerance 0.25
      --speculative-return-tolerance 0.01)

for d in mpc repeat-last hybrid; do
  tag=${d/repeat-last/repeat}
  for rep in a b; do
    phase="det_${tag}_${rep}"
    if [ -f "results/soyun/$RID/$phase/result.json" ] && grep -q '"status": "ok"' "results/soyun/$RID/$phase/result.json"; then
      echo "=== $phase already ok, skip ==="; continue
    fi
    echo "=== $(date -Is) $phase START ==="
    hy=()
    [ "$d" = hybrid ] && hy=(--speculative-hybrid-buffer-threshold 5.0 --speculative-hybrid-cv-threshold 0.30)
    $PY abr_spec/run_wrapped.py --run-id $RID --phase $phase --ckpt-name official_abr_r128 \
      --baseline-run-id baseline6_20260902 --baseline-phase a1_all_off \
      --decision-trace --speculative-drafter $d "${hy[@]}" \
      -- "${COMMON[@]}" "${TAIL[@]}"
    echo "=== $(date -Is) $phase DONE ==="
  done
done
echo "ALL DETERMINISM RUNS DONE $(date -Is)"
