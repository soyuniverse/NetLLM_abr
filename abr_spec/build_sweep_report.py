#!/usr/bin/env python3
"""abr_spec/build_sweep_report.py -- one table for the speculative sweep.

soyun / speculative inference.  Pure post-hoc: reads each run's
``selector_metrics.json`` (written by upstream ``test_on_env``) and its
``decisions.jsonl`` (written by ``abr_spec/decision_trace.py``).  No GPU, no
model, no re-run.

Rows: the A1 all-off reference and E from the BASELINE6 run, then every sweep
phase.  Columns are the ones the sweep has to answer:

  QoE / bitrate / rebuffer / smoothness      -- what the setting costs
  latency mean,p50,p95 / speedup vs A1       -- what it buys
  acceptance / q / queued_actions_served     -- why
  accepted-prefix mean                       -- what the drafter actually produced
  fallback total,buffer,state,return         -- where the queue leaked
  mpc_rollout_cpu_ms mean                    -- the 6^k brute force, isolated
  context tokens mean                        -- the verification-context cost

Plus, per run, the distance to the two thresholds fixed in BASELINE6:
break-even q = 14.63 % and 1.24x q = 31.43 %, under the measured cost model
mean_latency(q) = (1-q)*58.808 + q*0.832.

    python abr_spec/build_sweep_report.py \
      --sweep-dir results/soyun/sweep_spec_20260902 \
      --baseline-dir results/soyun/baseline6_20260902 \
      --out-dir results/soyun/sweep_spec_20260902/analysis
"""
import argparse
import csv
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# BASELINE6 cost model (results/soyun/baseline6_20260902/analysis/breakeven_E.json)
C_VERIFY = 58.808
C_SERVE = 0.832
Q_PARITY = 0.14625215284630777
Q_124 = 0.31427269599298496


def prefix_len(draft, target):
    n = 0
    for d, t in zip(draft, target):
        if d != t:
            break
        n += 1
    return n


def read_jsonl_stats(path):
    """accepted-prefix mean, MPC rollout CPU mean, and the stage split."""
    if not path.is_file():
        return {}
    verify_prefix, mpc_cpu, stages = [], [], {}
    n = 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            n += 1
            stages[r.get("stage")] = stages.get(r.get("stage"), 0) + 1
            if r.get("mpc_rollout_cpu_ms") is not None:
                mpc_cpu.append(r["mpc_rollout_cpu_ms"])
            if (r.get("stage") == "draft_verify" and r.get("mpc_draft_actions")
                    and r.get("llm_target_actions")):
                verify_prefix.append(
                    prefix_len(r["mpc_draft_actions"], r["llm_target_actions"]))
    if not n:
        return {}
    return {
        "trace_decisions": n,
        "accepted_prefix_mean": (sum(verify_prefix) / len(verify_prefix)
                                 if verify_prefix else None),
        "mpc_rollout_cpu_ms_mean": (sum(mpc_cpu) / len(mpc_cpu)) if mpc_cpu else None,
        "mpc_rollout_cpu_ms_total": sum(mpc_cpu) if mpc_cpu else None,
        "stage_counts": stages,
    }


def phase_row(run_dir, phase, label=None):
    d = run_dir / phase
    sm = d / "selector_metrics.json"
    if not sm.is_file():
        return {"run": label or phase, "status": "incomplete (no selector_metrics.json)"}
    m = json.loads(sm.read_text())
    res_path = d / "result.json"
    status = "ok"
    if res_path.is_file():
        status = json.loads(res_path.read_text()).get("status", "?")
    row = {
        "run": label or phase,
        "status": status,
        "k": m.get("speculative_draft_steps"),
        "mode": m.get("speculative_verification_mode"),
        "buffer_tol": m.get("speculative_buffer_tolerance"),
        "state_tol": m.get("speculative_state_tolerance"),
        "return_tol": m.get("speculative_return_tolerance"),
        "qoe": m.get("qoe_raw_mean"),
        "bitrate_mbps": m.get("mean_bitrate_mbps"),
        "rebuffer_s_per_chunk": m.get("mean_rebuffer_s_per_chunk"),
        "rebuffer_total_s": m.get("total_rebuffer_s"),
        "smoothness_mbps": m.get("mean_smoothness_mbps"),
        "latency_mean_ms": m.get("inference_latency_mean_ms"),
        "latency_p50_ms": m.get("inference_latency_p50_ms"),
        "latency_p95_ms": m.get("inference_latency_p95_ms"),
        "inference_calls": m.get("inference_calls"),
        "target_plm_calls": m.get("target_plm_calls"),
        "llm_call_reduction_ratio": m.get("llm_call_reduction_ratio"),
        "acceptance_rate": m.get("acceptance_rate"),
        "queued_actions_served": m.get("queued_actions_served"),
        "drafted_actions": m.get("drafted_actions"),
        "accepted_actions": m.get("accepted_actions"),
        "corrected_actions": m.get("corrected_actions"),
        "fallback_total": m.get("fallback_calls"),
        "fallback_buffer": m.get("buffer_mismatch_fallbacks"),
        "fallback_state": m.get("feature_mismatch_fallbacks"),
        "fallback_return": m.get("return_mismatch_fallbacks"),
        "draft_generation_failures": m.get("draft_generation_failures"),
        "context_tokens_mean": m.get("original_tokens_mean"),
        "selected_tokens_mean": m.get("selected_tokens_mean"),
    }
    calls = row["inference_calls"] or 0
    row["q_queue_serve_share"] = (row["queued_actions_served"] / calls) if calls else None
    row.update(read_jsonl_stats(d / "decisions.jsonl"))
    return row


def enrich(rows, base_latency):
    for r in rows:
        lat = r.get("latency_mean_ms")
        r["speedup_vs_a1"] = (base_latency / lat) if lat else None
        for k, tag in ((Q_PARITY, "parity"), (Q_124, "1.24x")):
            q = r.get("q_queue_serve_share")
            r[f"q_gap_to_{tag}"] = (k - q) if q is not None else None
            r[f"q_multiple_to_{tag}"] = (k / q) if q else None
        q = r.get("q_queue_serve_share")
        r["model_latency_ms"] = ((1 - q) * C_VERIFY + q * C_SERVE) if q is not None else None
        r["model_speedup"] = (base_latency / r["model_latency_ms"]
                              if r.get("model_latency_ms") else None)
    return rows


def f(v, nd=3, pct=False):
    if v is None:
        return "n/a"
    if isinstance(v, str):
        return v
    if pct:
        return f"{100 * v:.2f} %"
    return f"{v:.{nd}f}" if nd else f"{int(v)}"


def md_table(header, rows):
    out = ["| " + " | ".join(header) + " |",
           "|" + "|".join(["---"] * len(header)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sweep-dir", required=True)
    ap.add_argument("--baseline-dir", required=True)
    ap.add_argument("--baseline-phase", default="a1_all_off")
    ap.add_argument("--e-phase", default="e_speculative")
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    sweep_dir, base_dir = Path(args.sweep_dir), Path(args.baseline_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = [phase_row(base_dir, args.baseline_phase, "A1 all-off (ref)"),
            phase_row(base_dir, args.e_phase, "E k=3 greedy (BASELINE6)")]
    base_latency = rows[0].get("latency_mean_ms")
    if not base_latency:
        raise SystemExit(f"baseline phase {args.baseline_phase} has no latency metric")

    # sweep phases in the order the driver defines them
    order = ["s0_mode_sample", "s1_k1", "s2_k2", "s3_k4", "s4_k5",
             "s5_buftol2", "s6_buftol4", "s7_buftol8", "s8_statetol05"]
    present = [p.name for p in sorted(sweep_dir.iterdir()) if p.is_dir()] \
        if sweep_dir.is_dir() else []
    NON_PHASE = {"logs", "analysis"}
    for p in order + [x for x in present if x not in order and x not in NON_PHASE]:
        if (sweep_dir / p).is_dir():
            rows.append(phase_row(sweep_dir, p))
        else:
            rows.append({"run": p, "status": "NOT RUN"})
    enrich(rows, base_latency)

    keys = ["run", "status", "k", "mode", "buffer_tol", "state_tol", "return_tol",
            "qoe", "bitrate_mbps", "rebuffer_s_per_chunk", "rebuffer_total_s",
            "smoothness_mbps", "latency_mean_ms", "latency_p50_ms", "latency_p95_ms",
            "speedup_vs_a1", "acceptance_rate", "q_queue_serve_share",
            "queued_actions_served", "accepted_prefix_mean",
            "fallback_total", "fallback_buffer", "fallback_state", "fallback_return",
            "mpc_rollout_cpu_ms_mean", "context_tokens_mean", "selected_tokens_mean",
            "inference_calls", "target_plm_calls", "llm_call_reduction_ratio",
            "drafted_actions", "accepted_actions", "corrected_actions",
            "draft_generation_failures", "q_gap_to_parity", "q_multiple_to_parity",
            "q_gap_to_1.24x", "q_multiple_to_1.24x", "model_latency_ms",
            "model_speedup", "trace_decisions", "mpc_rollout_cpu_ms_total"]
    with open(out_dir / "sweep_table.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    (out_dir / "sweep_rows.json").write_text(json.dumps(rows, indent=2, sort_keys=True))

    hdr = ["run", "k", "mode", "btol", "stol", "QoE", "bitrate", "rebuf/chunk",
           "smooth", "lat mean", "p50", "p95", "speedup", "acceptance", "q",
           "queued", "prefix", "fb tot", "fb buf", "fb st", "fb ret",
           "mpc cpu ms", "ctx tok"]
    body = [[r.get("run"), f(r.get("k"), 0), r.get("mode") or "n/a",
             f(r.get("buffer_tol"), 1), f(r.get("state_tol"), 2),
             f(r.get("qoe"), 5), f(r.get("bitrate_mbps"), 5),
             f(r.get("rebuffer_s_per_chunk"), 5), f(r.get("smoothness_mbps"), 5),
             f(r.get("latency_mean_ms")), f(r.get("latency_p50_ms")),
             f(r.get("latency_p95_ms")),
             "n/a" if r.get("speedup_vs_a1") is None else f"{r['speedup_vs_a1']:.3f}x",
             f(r.get("acceptance_rate"), pct=True),
             f(r.get("q_queue_serve_share"), pct=True),
             f(r.get("queued_actions_served"), 0),
             f(r.get("accepted_prefix_mean")),
             f(r.get("fallback_total"), 0), f(r.get("fallback_buffer"), 0),
             f(r.get("fallback_state"), 0), f(r.get("fallback_return"), 0),
             f(r.get("mpc_rollout_cpu_ms_mean")), f(r.get("context_tokens_mean"), 1)]
            for r in rows]

    md = [f"## Sweep table (A1 = {base_latency:.3f} ms = 1.000x; "
          f"break-even q = {100*Q_PARITY:.2f} %, 1.24x q = {100*Q_124:.2f} %)", "",
          md_table(hdr, body), ""]

    # ---- axis views -------------------------------------------------------
    by_run = {r["run"]: r for r in rows}
    kmap = [("s1_k1", 1), ("s2_k2", 2), ("E k=3 greedy (BASELINE6)", 3),
            ("s3_k4", 4), ("s4_k5", 5)]
    kh = ["k", "ctx tokens", "mpc cpu ms/dec", "acceptance", "q", "speedup",
          "prefix mean", "status"]
    kb = []
    for name, k in kmap:
        r = by_run.get(name, {})
        kb.append([k, f(r.get("context_tokens_mean"), 1),
                   f(r.get("mpc_rollout_cpu_ms_mean")),
                   f(r.get("acceptance_rate"), pct=True),
                   f(r.get("q_queue_serve_share"), pct=True),
                   "n/a" if r.get("speedup_vs_a1") is None else f"{r['speedup_vs_a1']:.3f}x",
                   f(r.get("accepted_prefix_mean")), r.get("status", "NOT RUN")])
    md += ["### Axis 2 - draft horizon k", "", md_table(kh, kb), ""]

    tmap = [("E k=3 greedy (BASELINE6)", 1.0), ("s5_buftol2", 2.0),
            ("s6_buftol4", 4.0), ("s7_buftol8", 8.0)]
    th = ["buffer tol (s)", "q", "speedup", "QoE", "rebuf total (s)",
          "fb total", "fb buffer", "fb state", "status"]
    tb = []
    for name, tol in tmap:
        r = by_run.get(name, {})
        tb.append([tol, f(r.get("q_queue_serve_share"), pct=True),
                   "n/a" if r.get("speedup_vs_a1") is None else f"{r['speedup_vs_a1']:.3f}x",
                   f(r.get("qoe"), 5), f(r.get("rebuffer_total_s")),
                   f(r.get("fallback_total"), 0), f(r.get("fallback_buffer"), 0),
                   f(r.get("fallback_state"), 0), r.get("status", "NOT RUN")])
    md += ["### Axis 3 - buffer tolerance", "", md_table(th, tb), ""]

    done = [r for r in rows if r.get("status") == "ok"]
    pend = [r for r in rows if r.get("status") not in ("ok",)]
    md += [f"_{len(done)} run(s) with metrics, {len(pend)} pending/incomplete: "
           + ", ".join(f"{r['run']} ({r.get('status')})" for r in pend) + "_", ""]
    (out_dir / "sweep_tables.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
