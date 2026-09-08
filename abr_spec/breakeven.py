#!/usr/bin/env python3
"""abr_spec/breakeven.py -- what the drafter would have to deliver, from E's trace.

soyun / speculative inference.  Pure post-hoc arithmetic on
``decisions.jsonl`` + the all-off baseline latency.  No GPU, no re-run.

Latency model, fitted on the measured per-stage costs of the traced run:

    mean_latency(q) = (1 - q) * c_verify + q * c_serve

``q`` = share of decisions served straight out of the verified queue.  Solving
for the all-off baseline gives the *true* break-even queue-serve rate, and for
baseline/1.24 the rate needed to hit a 24 % speedup.

``q`` is then mapped back to the drafter: each verify call leaves ``E`` entries
in the queue, of which a fraction ``r`` survive the tolerance check and are
actually served, so a verify call covers ``1 + E*r`` decisions and
``q = E*r / (1 + E*r)``.  ``E`` is exactly what the drafter controls.
"""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def load(path):
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def prefix_len(draft, target):
    n = 0
    for d, t in zip(draft, target):
        if d != t:
            break
        n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("jsonl")
    ap.add_argument("--baseline-latency-ms", type=float, required=True,
                    help="all-off (A1) inference_latency_mean_ms")
    ap.add_argument("--speedup-target", type=float, default=1.24)
    ap.add_argument("--acceptance-target", type=float, default=0.05,
                    help="the acceptance rate quoted as break-even, for comparison")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--label", default="E")
    args = ap.parse_args()

    rows = load(args.jsonl)
    n = len(rows)
    verify = [r for r in rows if r["stage"] == "draft_verify"
              and r.get("mpc_draft_actions") and r.get("llm_target_actions")]
    serves = [r for r in rows if r["stage"] == "queue_serve"]
    falls = [r for r in rows if r["stage"] == "fallback"]

    def mean(vals):
        vals = [v for v in vals if v is not None]
        return None if not vals else sum(vals) / len(vals)

    c_verify = mean(r["latency_ms"] for r in verify)
    c_serve = mean(r["latency_ms"] for r in serves)
    c_fall = mean(r["latency_ms"] for r in falls)
    c_plain = args.baseline_latency_ms
    q_now = len(serves) / n

    # ---- queue supply actually produced, and how much of it survived --------
    if not verify or c_verify is None or c_serve is None:
        # No draft+verify step carried a draft action array, or no queue was
        # ever served (e.g. a trace that predates the BaseDraftGenerator patch).
        # Emit what stage labels alone support and skip the supply/scenario model.
        report = {
            "label": args.label, "source": args.jsonl,
            "decisions": n, "verify": len(verify), "queue_serves": len(serves),
            "fallbacks": len(falls),
            "cost_ms": {"verify_call": c_verify, "queue_serve": c_serve,
                        "fallback_call": c_fall, "baseline_plain_call": c_plain},
            "queue_serve_share": {"observed": q_now},
            "note": ("draft-action arrays and/or queue serves absent -- "
                     "queue-supply / scenario model skipped; the observed q and "
                     "the per-stage costs above are still valid."),
        }
        out = Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / f"breakeven_{args.label}.json").write_text(
            json.dumps(report, indent=2, sort_keys=True))
        print(json.dumps(report, indent=2, sort_keys=True))
        return

    def q_for(target_ms):
        return (c_verify - target_ms) / (c_verify - c_serve)

    q_parity = q_for(c_plain)
    q_target = q_for(c_plain / args.speedup_target)

    k = max(len(r["mpc_draft_actions"]) for r in verify)
    entries_avail = []           # entries left in the queue after the pop
    for r in verify:
        p = prefix_len(r["mpc_draft_actions"], r["llm_target_actions"])
        full = p == len(r["mpc_draft_actions"])
        entries_avail.append((len(r["mpc_draft_actions"]) - 1) if full else p)

    # depth-conditional realization: after a verify, how many consecutive
    # queue_serve decisions actually followed inside the same trace?
    idx = {id(r): i for i, r in enumerate(rows)}
    run_after = []
    for r in verify:
        i = idx[id(r)]
        c = 0
        j = i + 1
        while (j < n and rows[j]["stage"] == "queue_serve"
               and rows[j]["trace_idx"] == r["trace_idx"]):
            c += 1
            j += 1
        run_after.append(c)
    depth_avail, depth_used = Counter(), Counter()
    for avail, used in zip(entries_avail, run_after):
        for d in range(1, avail + 1):
            depth_avail[d] += 1
            if used >= d:
                depth_used[d] += 1
    r_by_depth = {str(d): (depth_used[d] / depth_avail[d]) if depth_avail[d] else None
                  for d in sorted(depth_avail)}

    E_mpc = sum(entries_avail) / len(verify)
    served = sum(run_after)
    r_real = served / sum(entries_avail) if sum(entries_avail) else 0.0

    def q_from(E, r):
        return (E * r) / (1.0 + E * r) if E and r else 0.0

    def latency_for(q):
        return (1 - q) * c_verify + q * c_serve

    # ---- hypothetical "repeat the last executed action" drafter ------------
    rep_entries = []
    for r in verify:
        kk = len(r["llm_target_actions"])
        p = prefix_len([r["last_action"]] * kk, r["llm_target_actions"])
        rep_entries.append((kk - 1) if p == kk else p)
    E_rep = sum(rep_entries) / len(verify)
    # optimistic: the same flat realization rate; conservative: the measured
    # depth-conditional curve, extrapolated with its deepest measured value.
    deepest = max((v for v in r_by_depth.values() if v is not None), default=r_real)
    r_deep = min([v for v in r_by_depth.values() if v is not None] or [r_real])
    rep_served_depthwise = 0.0
    for avail in rep_entries:
        for d in range(1, avail + 1):
            rep_served_depthwise += (r_by_depth.get(str(d)) if r_by_depth.get(str(d))
                                     is not None else r_deep)
    r_rep_depthwise = (rep_served_depthwise / sum(rep_entries)) if sum(rep_entries) else 0.0

    scenarios = {}
    for name, E, r in (("mpc_measured", E_mpc, r_real),
                       ("repeat_last_flat_r", E_rep, r_real),
                       ("repeat_last_depthwise_r", E_rep, r_rep_depthwise)):
        q = q_from(E, r)
        lat = latency_for(q)
        scenarios[name] = {
            "entries_per_verify": E, "realization_rate": r,
            "queue_serve_share": q, "predicted_latency_ms": lat,
            "predicted_speedup_vs_baseline": c_plain / lat if lat else None,
        }

    report = {
        "label": args.label,
        "source": args.jsonl,
        "decisions": n, "verify": len(verify), "queue_serves": len(serves),
        "fallbacks": len(falls),
        "cost_ms": {"verify_call": c_verify, "queue_serve": c_serve,
                    "fallback_call": c_fall, "baseline_plain_call": c_plain,
                    "draft_context_surcharge_ms": c_verify - c_plain,
                    "draft_context_surcharge_pct": 100.0 * (c_verify - c_plain) / c_plain},
        "queue_serve_share": {
            "observed": q_now,
            "needed_for_parity": q_parity,
            f"needed_for_{args.speedup_target:g}x": q_target,
            "multiple_needed_for_parity": q_parity / q_now if q_now else None,
            f"multiple_needed_for_{args.speedup_target:g}x": q_target / q_now if q_now else None,
        },
        "queue_supply": {
            "k": k,
            "entries_per_verify_mpc": E_mpc,
            "entries_per_verify_repeat_last": E_rep,
            "entries_ratio_repeat_over_mpc": E_rep / E_mpc if E_mpc else None,
            "realization_rate_flat": r_real,
            "realization_rate_by_queue_depth": r_by_depth,
            "deepest_measured_realization": deepest,
        },
        "scenarios": scenarios,
        "acceptance_rate_reference": {
            "quoted_breakeven": args.acceptance_target,
            "observed_acceptance_rate": (
                sum(prefix_len(r["mpc_draft_actions"], r["llm_target_actions"])
                    for r in verify)
                / sum(len(r["mpc_draft_actions"]) for r in verify)),
            "note": ("acceptance_rate alone does not set the break-even: what buys "
                     "latency is the queue-serve share q, which is acceptance x "
                     "horizon x tolerance-survival."),
        },
    }
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"breakeven_{args.label}.json").write_text(
        json.dumps(report, indent=2, sort_keys=True))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
