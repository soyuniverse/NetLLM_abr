#!/usr/bin/env python3
"""abr_spec/build_baseline6_report.py -- tables for the README 6-condition matrix.

soyun / speculative inference.  Reads results/soyun/<run-id>/manifest.json (which
run_wrapped.py wrote, one entry per phase) and emits:

  <run-dir>/table1_performance.csv   QoE / bitrate / rebuffer / smoothness + delta% vs A1
  <run-dir>/table2_efficiency.csv    latency, speedup, call counts, speculative counters
  <run-dir>/tables.md                both as markdown
  <run-dir>/summary_all.json         the flattened per-phase metric rows

A1 (the first all-off phase) is the reference for every delta and every speedup.
"""
import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

PERF = [
    ("qoe_raw_mean", "QoE (raw mean)", 5),
    ("mean_reward", "mean_reward", 5),
    ("mean_bitrate_mbps", "bitrate (Mbps)", 5),
    ("mean_rebuffer_s_per_chunk", "rebuffer (s/chunk)", 5),
    ("total_rebuffer_s", "rebuffer total (s)", 3),
    ("mean_smoothness_mbps", "smoothness (Mbps)", 5),
]
EFF = [
    ("inference_latency_mean_ms", "latency mean (ms)", 3),
    ("inference_latency_p50_ms", "latency p50 (ms)", 3),
    ("inference_latency_p95_ms", "latency p95 (ms)", 3),
    ("inference_calls", "inference_calls", 0),
    ("target_plm_calls", "target_plm_calls", 0),
    ("llm_call_reduction_ratio", "llm_call_reduction_ratio", 5),
    ("acceptance_rate", "acceptance_rate", 5),
    ("drafted_actions", "drafted", 0),
    ("accepted_actions", "accepted", 0),
    ("corrected_actions", "corrected", 0),
    ("queued_actions_served", "queued_actions_served", 0),
    ("fallback_calls", "fallback total", 0),
    ("buffer_mismatch_fallbacks", "fallback: buffer", 0),
    ("feature_mismatch_fallbacks", "fallback: state", 0),
    ("return_mismatch_fallbacks", "fallback: return", 0),
    ("draft_generation_failures", "draft_generation_failures", 0),
]


def fmt(v, nd):
    if v is None:
        return "n/a"
    if isinstance(v, str):
        return v
    return f"{v:.{nd}f}" if nd else f"{int(v)}"


def delta_pct(cur, base):
    if cur is None or base in (None, 0):
        return None
    return 100.0 * (cur - base) / abs(base)


def md_table(header, rows):
    out = ["| " + " | ".join(header) + " |",
           "|" + "|".join(["---"] * len(header)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--baseline-phase", default="a1_all_off")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    allm = json.loads((run_dir / "manifest.json").read_text())
    phases = []
    for ph in allm["phases"]:
        res = ph.get("result", {}) or {}
        phases.append({
            "phase": ph["phase"],
            "status": res.get("status"),
            "wall_seconds": res.get("wall_seconds"),
            "gpu": ph.get("gpu"),
            "argv": ph.get("parsed", {}),
            "decision_trace": (res.get("decision_trace") or {}).get("path"),
            "metrics": res.get("metrics", {}) or {},
        })
    by_phase = {p["phase"]: p for p in phases}
    base = by_phase[args.baseline_phase]["metrics"]

    # ---- table 1: performance ----
    h1 = ["구성"] + [lbl for _, lbl, _ in PERF] + [
        "ΔQoE %", "Δbitrate %", "Δrebuffer %", "Δsmoothness %"]
    r1 = []
    for p in phases:
        m = p["metrics"]
        row = [p["phase"]] + [fmt(m.get(k), nd) for k, _, nd in PERF]
        for k in ("qoe_raw_mean", "mean_bitrate_mbps",
                  "mean_rebuffer_s_per_chunk", "mean_smoothness_mbps"):
            d = delta_pct(m.get(k), base.get(k))
            row.append("n/a" if d is None else f"{d:+.2f}")
        r1.append(row)

    # ---- table 2: efficiency ----
    h2 = ["구성", "speedup vs A1 (mean)", "speedup p50", "speedup p95"] + \
         [lbl for _, lbl, _ in EFF]
    r2 = []
    for p in phases:
        m = p["metrics"]
        sp = []
        for k in ("inference_latency_mean_ms", "inference_latency_p50_ms",
                  "inference_latency_p95_ms"):
            cur, b = m.get(k), base.get(k)
            sp.append("n/a" if not (cur and b) else f"{b / cur:.3f}x")
        r2.append([p["phase"]] + sp + [fmt(m.get(k), nd) for k, _, nd in EFF])

    (run_dir / "table1_performance.csv").write_text(
        "\n".join([",".join(h1)] + [",".join(r) for r in r1]) + "\n")
    (run_dir / "table2_efficiency.csv").write_text(
        "\n".join([",".join(h2)] + [",".join(r) for r in r2]) + "\n")
    (run_dir / "summary_all.json").write_text(json.dumps(
        {"run_id": allm.get("run_id"), "baseline_phase": args.baseline_phase,
         "instance_changed": allm.get("instance_changed"), "phases": phases},
        indent=2, sort_keys=True))

    md = ["## 표1 — 성능 (QoE 계열, A1 기준 델타)", "", md_table(h1, r1), "",
          "## 표2 — 효율 (latency / call / speculative counters)", "",
          md_table(h2, r2), ""]
    (run_dir / "tables.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
