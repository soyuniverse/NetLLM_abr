#!/usr/bin/env bash
# abr_spec/run_drafter_ablation.sh -- drafter replacement A/B (mpc vs repeat-last vs hybrid).
#
# soyun / speculative inference.  Every run goes through abr_spec/run_wrapped.py
# (no upstream file touched, no run_plm.py subprocess) and lands under
# results/soyun/$RID/<phase>/.  One process per phase keeps CUDA state clean.
#
# WHY THIS EXISTS
# ---------------
# SWEEP_SPEC verdict: [parameters alone cannot reach break-even].  Max reachable
# queue-serve share q = 9.96 % (k=5) against the 18.15 % that setting needs; every
# speculative run sits in 0.898x-0.934x.  The blocker is the *drafter*, not the
# thresholds: BASELINE6 measured the MPC proposal matching the LoRA policy's own
# next action 12.84 % of the time while "repeat the last action" matches 93.30 %
# (policy autocorrelation 92.46 %), mean accepted prefix 0.180 vs 1.457.
# abr_spec/breakeven.py's post-hoc estimate for a repeat-last drafter: q ~ 35 %,
# speedup ~ 1.31x.  This ablation measures that for real.
#
# CODE FREEZE
# -----------
# The execution path is frozen at commit 3964752 (pluggable drafters, refactor
# regression-tested at tolerance 0 over 60 randomised cases plus the s2_k2
# end-to-end re-run).  Do not edit plm_special/speculative/, run_wrapped.py,
# decision_trace.py or drafter_select.py until this ablation is finished --
# SWEEP_SPEC section 2 shows what a mid-run code change costs in audit work.
#
# VERIFICATION MODE = sample (decision recorded 2026-09-02)
# ---------------------------------------------------------
# s0 (k=3, sample) scored QoE 0.95637 = A1 +0.81 % at 0.926x, against E (greedy)
# 0.91904 = A1 -3.13 % at 0.918x.  BASELINE6's QoE loss was the greedy argmax,
# not speculation (split: speculation +0.00765, mode -0.03733).  sample is also
# run_plm.py's own default.  Reproducibility is preserved because sampling is
# seeded (--seed 1; rl_policy._sample -> random.choices, re-seeded per run by
# run_plm.set_random_seed and test.test_on_env).  Every run here uses sample;
# M1b keeps one greedy pair purely for continuity with BASELINE6's E.
#
# TOLERANCES ARE PINNED AT THE DEFAULTS (1.0 / 0.25 / 0.01) AND NOT SWEPT
# ----------------------------------------------------------------------
# SWEEP_SPEC section 5: loosening the buffer tolerance substitutes rather than
# fixes.  btol 1.0 -> 8.0 moved buffer fallbacks 236 -> 43 while state fallbacks
# went 32 -> 191, total fallbacks 268 -> 234 -- 82 % substitution overall and
# 100 % between btol 4 and 8, with q saturating at 6.64 %.  The queue entries
# were being discarded because the *drafted action* was wrong, so a threshold
# cannot help.  Changing them here would also confound the drafter comparison.
# return tolerance stays 0.01: return_mismatch_fallbacks was 0 in every one of
# the 12 runs measured so far.  They are passed explicitly so each run's argv
# records the tolerance it used.
#
# Usage
#   bash abr_spec/run_drafter_ablation.sh --dry-run      # commands + ETA, runs nothing
#   tmux new -s drafterab -d
#   tmux send-keys -t drafterab 'bash abr_spec/run_drafter_ablation.sh' C-m
#   RUNS="m2_repeat_k3 m3_hybrid_k3" bash abr_spec/run_drafter_ablation.sh
#   BEST_DRAFTER=repeat-last BEST_K=5 bash abr_spec/run_drafter_ablation.sh   # enables M6
#
# Re-running is safe: a phase whose result.json says "status": "ok" is skipped,
# so an interrupted ablation resumes.  A failed phase is recorded and the run
# continues; the script exits non-zero at the end.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

RID="${RID:-drafter_ab_$(date +%Y%m%d)}"
BASE_RID="${BASE_RID:-baseline6_20260902}"     # --baseline-run-id  == BASELINE6's A1
BASE_PHASE="${BASE_PHASE:-a1_all_off}"         # --baseline-phase   == A1
CKPT="${CKPT:-official_abr_r128}"
TRACE_NUM="${TRACE_NUM:-100}"
PY="${PY:-$REPO/.venv/bin/python}"
RUNS="${RUNS:-}"                               # optional whitelist of phase names
# M6 is only defined once M2-M5 name a winner.  Left unset -> M6 is a placeholder.
BEST_DRAFTER="${BEST_DRAFTER:-}"
BEST_K="${BEST_K:-}"
LOGDIR="$REPO/results/soyun/$RID/logs"

DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

# ---- $COMMON: byte-for-byte the BASELINE6 / SWEEP_SPEC arguments ------------
COMMON=(--test --fp16 --seed 1 --plm-type llama --plm-size base --rank 128
        --plm-dir ../downloaded_plms/llama/base
        --model-dir ../downloaded_plms/ft_plms/try_llama2_7b
        --trace fcc-test --trace-num "$TRACE_NUM" --video video1 --fixed-order
        --device cuda:0 --device-out cuda:0)
TOL=(--speculative-buffer-tolerance 1.0
     --speculative-state-tolerance 0.25
     --speculative-return-tolerance 0.01)
# selector configuration: M1-M5 are "speculative only" (== BASELINE6 condition E);
# M6 adds BASELINE6 condition D's selectors on top of the winning drafter.
SEL_NONE=(--temporal-selector none --token-selector none)
SEL_D=(--temporal-selector event-aware --token-selector intra-timestep)

# hybrid needs its thresholds passed; M6 only carries them if hybrid wins.
M6_HYBRID_THRESHOLDS=""
if [ "$BEST_DRAFTER" = "hybrid" ]; then
  M6_HYBRID_THRESHOLDS=" --speculative-hybrid-buffer-threshold 5.0 --speculative-hybrid-cv-threshold 0.30"
fi

# ---- the ablation: name | est mean latency (ms) | wrapper args | run_plm args
# Estimated latency drives the ETA only.  M1a/M1b are the measured s0 / E values.
# M2-M6 use the cost model  mean = (1-q-f)*c_verify(k) + f*50.329 + q*0.832
# with c_verify from SWEEP_SPEC's token fit (58.88 at k=3, 61.31 at k=5) and the
# post-hoc q ~ 35 % estimate -- i.e. they are ESTIMATES, treat as +-30 %.
ABLATION=(
  "m1a_mpc_k3_sample|54.4|--speculative-drafter mpc|${SEL_NONE[*]} --speculative-draft-steps 3 --speculative-verification-mode sample ${TOL[*]}"
  "m1b_mpc_k3_greedy|54.8|--speculative-drafter mpc|${SEL_NONE[*]} --speculative-draft-steps 3 --speculative-verification-mode greedy ${TOL[*]}"
  "m2_repeat_k3|38.5|--speculative-drafter repeat-last|${SEL_NONE[*]} --speculative-draft-steps 3 --speculative-verification-mode sample ${TOL[*]}"
  "m3_hybrid_k3|42.0|--speculative-drafter hybrid --speculative-hybrid-buffer-threshold 5.0 --speculative-hybrid-cv-threshold 0.30|${SEL_NONE[*]} --speculative-draft-steps 3 --speculative-verification-mode sample ${TOL[*]}"
  "m4_repeat_k5|38.0|--speculative-drafter repeat-last|${SEL_NONE[*]} --speculative-draft-steps 5 --speculative-verification-mode sample ${TOL[*]}"
  "m5_hybrid_k5|42.0|--speculative-drafter hybrid --speculative-hybrid-buffer-threshold 5.0 --speculative-hybrid-cv-threshold 0.30|${SEL_NONE[*]} --speculative-draft-steps 5 --speculative-verification-mode sample ${TOL[*]}"
  "m6_best_plus_selectors|24.0|--speculative-drafter ${BEST_DRAFTER:-<BEST_DRAFTER>}${M6_HYBRID_THRESHOLDS}|${SEL_D[*]} --speculative-draft-steps ${BEST_K:-<BEST_K>} --speculative-verification-mode sample ${TOL[*]}"
)

selected() {
  [ -z "$RUNS" ] && return 0
  printf '%s\n' $RUNS | grep -qx "$1"
}

done_already() {
  local f="$REPO/results/soyun/$RID/$1/result.json"
  [ -f "$f" ] && grep -q '"status": "ok"' "$f"
}

m6_ready() { [ -n "$BEST_DRAFTER" ] && [ -n "$BEST_K" ]; }

# "--a 1 --b 2" -> one "flag<TAB>value" line per knob, so two configurations can
# be diffed by flag rather than by loose token.
pairs() {
  awk '{
    for (i = 1; i <= NF; i++) {
      if ($i ~ /^--/) {
        if (i < NF && $(i+1) !~ /^--/) { print $i "\t" $(i+1); i++ }
        else { print $i "\t(set)" }
      }
    }
  }' <<< "$*"
}

# Print exactly which knobs differ from the M1a control, as flag: ctrl -> run.
knob_diff() {                      # knob_diff <ctrl args> -- <run args>
  local ctrl="$1" run="$2" out="" flag cval rval
  while IFS=$'\t' read -r flag rval; do
    [ -z "$flag" ] && continue
    cval=$(pairs "$ctrl" | awk -F'\t' -v f="$flag" '$1==f{print $2; exit}')
    if [ -z "$cval" ]; then out+="${flag}: (absent) -> ${rval}; "
    elif [ "$cval" != "$rval" ]; then out+="${flag}: ${cval} -> ${rval}; "
    fi
  done < <(pairs "$run")
  while IFS=$'\t' read -r flag cval; do
    [ -z "$flag" ] && continue
    if ! pairs "$run" | awk -F'\t' -v f="$flag" '$1==f{found=1} END{exit !found}'; then
      out+="${flag}: ${cval} -> (absent); "
    fi
  done < <(pairs "$ctrl")
  printf '%s' "${out:-none}"
}

# ---------------------------------------------------------------- dry run ----
if [ "$DRY" -eq 1 ]; then
  echo "DRY RUN -- nothing is executed."
  echo
  echo "RID          = $RID"
  echo "baseline     = --baseline-run-id $BASE_RID --baseline-phase $BASE_PHASE"
  echo "checkpoint   = $CKPT"
  echo "traces       = $TRACE_NUM"
  pending=$(git -C "$REPO" status --porcelain -- \
      adaptive_bitrate_streaming/plm_special/speculative abr_spec | wc -l)
  echo "frozen at    = $(git -C "$REPO" rev-parse --short HEAD)  (${pending} uncommitted change(s) under the frozen paths -- must be 0)"
  echo "M6 drafter/k = ${BEST_DRAFTER:-<unset>} / ${BEST_K:-<unset>}"
  echo
  if [ -f "$REPO/results/soyun/$BASE_RID/manifest.json" ]; then
    echo "preflight: baseline manifest found (results/soyun/$BASE_RID/manifest.json)"
  else
    echo "preflight: !! results/soyun/$BASE_RID/manifest.json MISSING -- speedup would be null"
  fi
  echo "preflight: python $([ -x "$PY" ] && echo OK || echo '!! MISSING')  $PY"
  echo

  # control row = M1a; every other run is diffed against it to prove one-knob isolation
  ctrl_w=""; ctrl_p=""
  for entry in "${ABLATION[@]}"; do
    if [ "${entry%%|*}" = "m1a_mpc_k3_sample" ]; then
      rest="${entry#*|}"; rest="${rest#*|}"
      ctrl_w="${rest%%|*}"; ctrl_p="${rest#*|}"
    fi
  done

  total=0; n=0
  for entry in "${ABLATION[@]}"; do
    name="${entry%%|*}"; rest="${entry#*|}"
    est="${rest%%|*}"; rest="${rest#*|}"
    wrap="${rest%%|*}"; pass="${rest#*|}"
    state="RUN"
    if ! selected "$name"; then state="SKIP (not in RUNS)"
    elif [ "$name" = "m6_best_plus_selectors" ] && ! m6_ready; then
      state="PENDING (needs BEST_DRAFTER + BEST_K from M2-M5)"
    elif done_already "$name"; then state="SKIP (already ok)"
    fi
    wall=$(awk -v l="$est" 'BEGIN{printf "%.0f", 4.7*l + 3.7}')
    echo "--- $name   [$state]   est ${wall}s (mean latency ~${est} ms x 4700 decisions + 3.7 s load)"
    echo "$PY abr_spec/run_wrapped.py \\"
    echo "  --run-id $RID --phase $name --ckpt-name $CKPT \\"
    echo "  --baseline-run-id $BASE_RID --baseline-phase $BASE_PHASE \\"
    echo "  --decision-trace $wrap \\"
    echo "  -- ${COMMON[*]} \\"
    echo "     $pass"
    # ---- one-knob isolation check against M1a ----
    if [ "$name" != "m1a_mpc_k3_sample" ]; then
      echo "    knob diff vs M1a -- wrapper: $(knob_diff "$ctrl_w" "$wrap")"
      echo "    knob diff vs M1a -- run_plm: $(knob_diff "$ctrl_p" "$pass")"
    else
      echo "    knob diff vs M1a control:  (this IS the control; also re-runs s0 to confirm reproduction)"
    fi
    echo "    common pinned:  seed 1 | fcc-test/$TRACE_NUM | video1 | fixed-order | rank 128 | fp16 | tolerances 1.0/0.25/0.01"
    echo
    if [ "$state" = "RUN" ]; then
      total=$(awk -v t="$total" -v w="$wall" 'BEGIN{print t+w}')
      n=$((n+1))
    fi
  done
  ceil=$(awk -v n="$n" 'BEGIN{printf "%.0f", n*(4.7*54.8+3.7)}')
  awk -v t="$total" -v n="$n" -v c="$ceil" 'BEGIN{
    printf "TOTAL: %d run(s), point estimate %.0f s = %.1f min = %.2f h\n", n, t, t/60, t/3600
    printf "       conservative ceiling (every run as slow as mpc k=3) %.0f s = %.1f min\n", c, c/60
    printf "cost @ $0.228/h  point ~ $%.3f   ceiling ~ $%.3f\n", 0.228*t/3600, 0.228*c/3600
  }'
  echo
  echo "Notes"
  echo " - M1a doubles as a reproduction check of SWEEP_SPEC's s0 (same knobs, drafter"
  echo "   'mpc' installs NO patch in drafter_select), so its metrics should land on"
  echo "   s0's QoE 0.95637 / q 7.36 % / acceptance 7.91 % exactly. Any divergence means"
  echo "   the freeze was broken."
  echo " - M4/M5 push k to 5 because repeat-last costs no search: the 6^k CPU wall that"
  echo "   capped MPC (1.90 % of latency at k=5, 7.2x its k=3 share) does not apply."
  echo "   decisions.jsonl records mpc_rollout_cpu_ms per decision, so M5 also measures"
  echo "   what fraction of hybrid's decisions actually paid for an MPC rollout."
  echo " - M6 stays a placeholder until M2-M5 name a winner; re-run this script with"
  echo "   BEST_DRAFTER=<repeat-last|hybrid> BEST_K=<3|5> to materialise it."
  echo " - ETA for M2-M6 assumes the post-hoc q ~ 35 % estimate holds; treat as +-30 %."
  exit 0
fi

# ------------------------------------------------------------------- run ----
mkdir -p "$LOGDIR"
FAILED=(); RAN=0
echo "RID=$RID  BASELINE=$BASE_RID/$BASE_PHASE  TRACE_NUM=$TRACE_NUM  started $(date -Is)"
echo "frozen at $(git -C "$REPO" rev-parse --short HEAD)"

for entry in "${ABLATION[@]}"; do
  name="${entry%%|*}"; rest="${entry#*|}"; rest="${rest#*|}"
  wrap="${rest%%|*}"; pass="${rest#*|}"

  if ! selected "$name"; then
    echo "=== [$(date -Is)] phase=$name SKIPPED (not in RUNS) ==="; continue
  fi
  if [ "$name" = "m6_best_plus_selectors" ] && ! m6_ready; then
    echo "=== [$(date -Is)] phase=$name SKIPPED (BEST_DRAFTER/BEST_K unset) ==="; continue
  fi
  if done_already "$name"; then
    echo "=== [$(date -Is)] phase=$name SKIPPED (already completed ok) ==="; continue
  fi

  echo "=== [$(date -Is)] phase=$name START ==="
  rc=0
  "$PY" abr_spec/run_wrapped.py \
    --run-id "$RID" --phase "$name" --ckpt-name "$CKPT" \
    --baseline-run-id "$BASE_RID" --baseline-phase "$BASE_PHASE" \
    --decision-trace $wrap \
    -- "${COMMON[@]}" $pass 2>&1 | tee "$LOGDIR/$name.log" || rc=$?
  echo "=== [$(date -Is)] phase=$name rc=$rc ==="
  if [ "$rc" -ne 0 ]; then
    echo "FAILED: phase $name (rc=$rc) -- continuing with the remaining phases"
    FAILED+=("$name")
  fi
  RAN=$((RAN+1))
done

echo
echo "ABLATION DONE $(date -Is): $RAN run(s) executed -> results/soyun/$RID/"
if [ "${#FAILED[@]}" -gt 0 ]; then
  echo "FAILURES: ${FAILED[*]}"; exit 1
fi
echo "no failures"
