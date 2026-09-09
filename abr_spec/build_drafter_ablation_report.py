#!/usr/bin/env python3
"""abr_spec/build_drafter_ablation_report.py -- assemble the DRAFTER_ABLATION table.

soyun / speculative inference.  Pure CPU.  Joins, per ablation phase:
  results/soyun/<rid>/<phase>/selector_metrics.json   (QoE, counters, latency)
  results/soyun/<rid>/analysis/decision_analysis_<phase>.json  (agreement, prefix)
  results/soyun/<rid>/analysis/breakeven_<phase>.json          (q model)
  results/soyun/<rid>/analysis/queue_safety.json               (safety gate)
into one CSV + markdown, speedup taken against <rid>/a1_all_off measured on the
same instance.

    python abr_spec/build_drafter_ablation_report.py --rid drafter_ab_20260908
"""
import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PHASES = ["m1a_mpc_k3_sample", "m1b_mpc_k3_greedy", "m2_repeat_k3",
          "m3_hybrid_k3", "m4_repeat_k5", "m5_hybrid_k5"]


def jload(p):
    return json.loads(Path(p).read_text()) if Path(p).is_file() else {}


def g(d, *ks, default=None):
    for k in ks:
        if not isinstance(d, dict):
            return default
        d = d.get(k)
    return default if d is None else d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rid", default="drafter_ab_20260908")
    ap.add_argument("--phases", nargs="*", default=PHASES)
    ap.add_argument("--a1-rid", default=None,
                    help="run-id holding a1_all_off for the speedup/QoE reference "
                         "(default: --rid). Use when a gate run reuses an earlier "
                         "instance's A1.")
    args = ap.parse_args()
    root = REPO / "results" / "soyun" / args.rid
    A = root / "analysis"
    a1_root = REPO / "results" / "soyun" / (args.a1_rid or args.rid)

    a1 = jload(a1_root / "a1_all_off" / "selector_metrics.json")
    a1_lat = a1.get("inference_latency_mean_ms")
    a1_qoe = a1.get("qoe_raw_mean")
    a1_reb = a1.get("total_rebuffer_s")
    qsafe = jload(A / "queue_safety.json")

    rows = []
    for ph in args.phases:
        m = jload(root / ph / "selector_metrics.json")
        da = jload(A / f"decision_analysis_{ph}.json")
        be = jload(A / f"breakeven_{ph}.json")
        res = jload(root / ph / "result.json")
        qs = qsafe.get(ph, {})
        if not m:
            rows.append({"phase": ph, "status": "MISSING"})
            continue
        ic = m["inference_calls"]
        lat = m["inference_latency_mean_ms"]
        q = m["queued_actions_served"] / ic
        drafter = g(res, "drafter", "drafter") or (
            "mpc" if "mpc" in ph else ("repeat-last" if "repeat" in ph else "hybrid"))
        rows.append({
            "phase": ph,
            "drafter": drafter,
            "k": int(m.get("speculative_draft_steps") or (5 if "k5" in ph else 3)),
            "mode": m.get("speculative_verification_mode", "sample"),
            "selectors": f"{m.get('temporal_selector','none')}/{m.get('token_selector','none')}",
            "qoe": m["qoe_raw_mean"],
            "d_qoe_pct": 100 * (m["qoe_raw_mean"] - a1_qoe) / a1_qoe if a1_qoe else None,
            "bitrate_mbps": m["mean_bitrate_mbps"],
            "rebuffer_total_s": m["total_rebuffer_s"],
            "d_rebuffer_s": m["total_rebuffer_s"] - a1_reb if a1_reb is not None else None,
            "smoothness_mbps": m["mean_smoothness_mbps"],
            "latency_mean_ms": lat,
            "speedup_vs_a1": a1_lat / lat if a1_lat else None,
            "acceptance_rate": m["acceptance_rate"],
            "q_queue_serve": q,
            "queued_actions_served": m["queued_actions_served"],
            "target_plm_calls": m["target_plm_calls"],
            "fallback_total": m["fallback_calls"],
            "fallback_buffer": m["buffer_mismatch_fallbacks"],
            "fallback_state": m["feature_mismatch_fallbacks"],
            "fallback_return": m["return_mismatch_fallbacks"],
            "draft_1step_rate": g(da, "overall", "mpc_step1_rate"),
            "repeat_on_verify_rate": g(da, "overall", "repeat_last_rate_on_verify"),
            "llm_autocorr_rate": g(da, "overall", "llm_autocorr_adjacent_rate"),
            "accepted_prefix_mean": g(da, "per_position", "mpc_accepted_prefix_mean"),
            "ctx_tokens_mean": g(da, "latency", "by_stage", "draft_verify",
                                 "context_selected_tokens", "mean"),
            "q_parity_model": g(be, "queue_serve_share", "needed_for_parity"),
            "q_1p24x_model": g(be, "queue_serve_share", "needed_for_1.24x"),
            "c_verify_ms": g(be, "cost_ms", "verify_call"),
            "c_serve_ms": g(be, "cost_ms", "queue_serve"),
            "safety_C_incidence": g(qs, "C_incidence", "rate"),
            "safety_C_vs_mpc": g(qs, "C_incidence", "vs_mpc_ref_ratio"),
            "safety_window_union_rebuffer_s": g(qs, "C_incidence", "window_union_rebuffer_s"),
            "safety_A_queue_mean_s": g(qs, "A_direct", "queue_serve_mean_s"),
            "safety_A_llm_mean_s": g(qs, "A_direct", "llm_served_mean_s"),
        })

    cols = list(rows[0].keys())
    csv = [",".join(cols)]
    for r in rows:
        csv.append(",".join("" if r.get(c) is None else str(r.get(c)) for c in cols))
    (A / "drafter_ablation_table.csv").write_text("\n".join(csv) + "\n")

    def f(x, s=1.0, d=3):
        return "" if x is None else f"{x*s:.{d}f}"

    md = [f"# Drafter ablation — {args.rid}", "",
          f"A1 (this instance): QoE {a1_qoe:.5f} · latency {a1_lat:.2f} ms · "
          f"rebuffer_total {a1_reb:.3f} s", "",
          "| phase | drafter | k | mode | QoE | ΔQoE % | speedup | q | accept | "
          "draft 1-step | prefix mean | rebuf tot (s) | Δrebuf (s) | fb tot/buf/st | "
          "safety C | C vs mpc |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if r.get("status") == "MISSING":
            md.append(f"| {r['phase']} | — MISSING — |")
            continue
        md.append("| " + " | ".join([
            r["phase"], r["drafter"], str(r["k"]), r["mode"],
            f(r["qoe"], d=5), f(r["d_qoe_pct"], d=2),
            f(r["speedup_vs_a1"]) + "×", f(r["q_queue_serve"], 100, 2) + "%",
            f(r["acceptance_rate"], 100, 1) + "%",
            f(r["draft_1step_rate"], 100, 1) + "%", f(r["accepted_prefix_mean"]),
            f(r["rebuffer_total_s"]), f(r["d_rebuffer_s"]),
            f"{r['fallback_total']}/{r['fallback_buffer']}/{r['fallback_state']}",
            f(r["safety_C_incidence"], 100, 3) + "%",
            f(r["safety_C_vs_mpc"]) if r["safety_C_vs_mpc"] else "ref",
        ]) + " |")
    (A / "drafter_ablation_table.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
