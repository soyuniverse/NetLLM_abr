#!/usr/bin/env python3
"""abr_spec/trajectory_divergence.py -- how far a serve-time gate trip perturbs the run.

soyun / speculative inference.  Pure CPU.  Compares each gated run's per-decision
action sequence against the un-gated control and writes, to
<gate-rid>/analysis/divergence_<label>.csv:
  - post-first-trip action-mismatch rate vs the control, in 100-decision buckets
  - per-trace rebuffering (control vs gated) for traces that rebuffer in either
so fig6 (and TRAJECTORY_DIVERGENCE.md) are reproducible from a tracked file.

    python abr_spec/trajectory_divergence.py \
      --control results/soyun/drafter_ab_20260908/m5_hybrid_k5/decisions.jsonl \
      --gated  v1=results/soyun/serve_gate_20260909/g_hybrid_k5_f5/decisions.jsonl \
               v2=results/soyun/serve_gate_20260909/v_hybrid_k5_f5_cons/decisions.jsonl \
      --out-dir results/soyun/serve_gate_20260909/analysis
"""
import argparse
import collections
import csv
import json
from pathlib import Path

LOW = 5.0  # buffer floor used by the gate runs


def load(p):
    with open(p) as f:
        return [json.loads(l) for l in f if l.strip()]


def trips(rows):
    return [(r["trace_idx"], r["t"]) for r in rows
            if r.get("stage") == "fallback" and r.get("fallback_reason") == "buffer"
            and (r.get("buffer") if r.get("buffer") is not None else 99) < LOW]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--control", required=True)
    ap.add_argument("--gated", nargs="+", required=True, help="label=path ...")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--bucket", type=int, default=100)
    args = ap.parse_args()

    base = load(args.control)
    bidx = {(r["trace_idx"], r["t"]): r for r in base}
    order = sorted(bidx)
    gpos = {k: i for i, k in enumerate(order)}
    base_reb = collections.defaultdict(float)
    for r in base:
        base_reb[r["trace_idx"]] += r.get("rebuffer_after_s") or 0.0

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary = []

    for item in args.gated:
        label, _, path = item.partition("=")
        rows = load(path)
        ridx = {(r["trace_idx"], r["t"]): r for r in rows}
        tr = trips(rows)
        first = min((gpos[k] for k in tr if k in gpos), default=0)

        buckets = collections.defaultdict(lambda: [0, 0])
        total_m = total_t = 0
        for k in order:
            if k not in ridx:
                continue
            off = gpos[k] - first
            if off < 0:
                continue
            b = off // args.bucket
            buckets[b][1] += 1
            total_t += 1
            if ridx[k].get("action") != bidx[k].get("action"):
                buckets[b][0] += 1
                total_m += 1

        gate_reb = collections.defaultdict(float)
        for r in rows:
            gate_reb[r["trace_idx"]] += r.get("rebuffer_after_s") or 0.0
        div_traces = sorted({k[0] for k in order
                             if k in ridx and k in bidx
                             and ridx[k].get("action") != bidx[k].get("action")})

        with open(out / f"divergence_{label}.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["kind", "x", "mismatch", "total", "rate"])
            for b in sorted(buckets):
                m, t = buckets[b]
                w.writerow(["bucket", b * args.bucket, m, t, round(m / t, 4) if t else ""])
            for tidx in sorted(set(list(base_reb) + list(gate_reb))):
                cb, cg = base_reb.get(tidx, 0.0), gate_reb.get(tidx, 0.0)
                if max(cb, cg) > 0.05:
                    w.writerow(["trace_rebuffer", tidx, round(cb, 3), round(cg, 3), ""])

        summary.append({
            "label": label, "n_rows": len(rows), "n_trips": len(tr),
            "first_trip_global_pos": first, "n_control_decisions": len(order),
            "post_trip_mismatch": total_m, "post_trip_total": total_t,
            "post_trip_mismatch_rate": round(total_m / total_t, 4) if total_t else None,
            "per_intervention_decisions": round(total_m / len(tr), 1) if tr else None,
            "diverged_traces": len(div_traces),
            "control_rebuffer_s": round(sum(base_reb.values()), 3),
            "gated_rebuffer_s": round(sum(gate_reb.values()), 3),
        })

    (out / "divergence_summary.json").write_text(json.dumps(summary, indent=2))
    for s in summary:
        print(f"{s['label']:12s} trips={s['n_trips']}  mismatch={s['post_trip_mismatch_rate']*100:.1f}%"
              f"  per-intervention={s['per_intervention_decisions']}  diverged_traces={s['diverged_traces']}"
              f"  rebuf {s['control_rebuffer_s']}->{s['gated_rebuffer_s']}"
              + ("  (jsonl incomplete)" if s["n_rows"] < s["n_control_decisions"] else ""))


if __name__ == "__main__":
    main()
