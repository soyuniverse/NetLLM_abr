#!/usr/bin/env python3
"""abr_spec/queue_safety.py -- rebuffering in the window right after a queue-served decision.

soyun / speculative inference.  Pure post-hoc arithmetic on one or more
``decisions.jsonl`` traces (no GPU, no re-run).  This is DRAFTER_ABLATION's
core safety gate: a ``queue_serve`` decision executes a previously drafted
action with no LLM call, and a wrong draft can spill rebuffering into the next
few chunks, not just its own.

Design (DRAFTER_ABLATION.md section S):

  window   For each queue_serve decision D, the window is D itself (offset 0)
           through the next W = k decisions in the same trace (k = the run's
           draft length), never crossing an end-of-video boundary.
  A direct     mean rebuffer_after_s on queue_serve decisions vs LLM-served ones
  B lagged     mean rebuffer_after_s on offsets 1..W after a queue_serve vs all
  C incidence  share of queue_serve decisions whose [0..W] window has a rebuffer
  control  every figure is also split by buffer band (<5 / 5-10 / 10-20 / >=20 s)
           so queue-vs-LLM is compared within a band, and the mpc run is the
           reference drafter.

    python abr_spec/queue_safety.py LABEL=path/to/decisions.jsonl [LABEL2=...] \
        --out-dir <dir> [--window k]      # --window auto-detects k per file if omitted
"""
import argparse
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

BUFFER_BANDS = (("<5s", None, 5.0), ("5-10s", 5.0, 10.0),
                ("10-20s", 10.0, 20.0), (">=20s", 20.0, None))
LLM_STAGES = ("draft_verify", "fallback", "plain")


def band(value, bands):
    if value is None:
        return "unknown"
    for name, lo, hi in bands:
        if (lo is None or value >= lo) and (hi is None or value < hi):
            return name
    return "unknown"


def load(path):
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def mean(xs):
    xs = [x for x in xs if x is not None]
    return None if not xs else sum(xs) / len(xs)


def pct(n, d):
    return None if not d else n / d


def order_traces(rows):
    """Group by trace_idx, sort each by t; return list of per-trace lists."""
    by_trace = defaultdict(list)
    for r in rows:
        by_trace[r.get("trace_idx")].append(r)
    out = []
    for _, rs in sorted(by_trace.items(), key=lambda kv: (kv[0] is None, kv[0])):
        out.append(sorted(rs, key=lambda r: r.get("t", 0)))
    return out


def detect_k(rows):
    ks = [len(r["mpc_draft_actions"]) for r in rows
          if r.get("stage") == "draft_verify" and r.get("mpc_draft_actions")]
    if ks:
        return max(ks)
    ks = [len(r["llm_target_actions"]) for r in rows if r.get("llm_target_actions")]
    return max(ks) if ks else 3


def analyse(rows, window):
    traces = order_traces(rows)
    n = len(rows)

    # ---- A: direct, queue_serve chunk vs LLM-served chunk -------------------
    q_direct = [r.get("rebuffer_after_s") for r in rows if r.get("stage") == "queue_serve"]
    llm_direct = [r.get("rebuffer_after_s") for r in rows if r.get("stage") in LLM_STAGES]

    # ---- B: lagged, offsets 1..W after any queue_serve ---------------------
    lagged, lagged_seen = [], set()
    # ---- C: window incidence + total rebuffering in windows ---------------
    win_has_event = 0
    win_total_s = 0.0
    n_qserve = 0
    per_band = defaultdict(lambda: {"q_direct": [], "llm_direct": [],
                                    "win_events": 0, "win_n": 0, "win_total_s": 0.0})

    for tr in traces:
        for i, r in enumerate(tr):
            if r.get("stage") != "queue_serve":
                continue
            n_qserve += 1
            b = band(r.get("buffer"), BUFFER_BANDS)
            per_band[b]["q_direct"].append(r.get("rebuffer_after_s"))
            per_band[b]["win_n"] += 1

            # window = offsets 0..W within this trace
            w_rows = tr[i:i + window + 1]
            reb = [x.get("rebuffer_after_s") or 0.0 for x in w_rows]
            has_ev = any((x.get("rebuffered") or (x.get("rebuffer_after_s") or 0) > 0)
                         for x in w_rows)
            win_has_event += int(has_ev)
            win_total_s += sum(reb)
            per_band[b]["win_events"] += int(has_ev)
            per_band[b]["win_total_s"] += sum(reb)

            for x in w_rows[1:]:
                key = (x.get("trace_idx"), x.get("t"))
                if key not in lagged_seen:
                    lagged_seen.add(key)
                    lagged.append(x.get("rebuffer_after_s"))

    for r in rows:
        if r.get("stage") in LLM_STAGES:
            b = band(r.get("buffer"), BUFFER_BANDS)
            per_band[b]["llm_direct"].append(r.get("rebuffer_after_s"))

    total_reb_all = sum((r.get("rebuffer_after_s") or 0.0) for r in rows)

    bands_out = []
    for name, _, _ in list(BUFFER_BANDS) + [("unknown", None, None)]:
        d = per_band.get(name)
        if not d or (d["win_n"] == 0 and not d["llm_direct"]):
            continue
        bands_out.append({
            "band": name,
            "queue_serve_n": d["win_n"],
            "A_queue_direct_mean_s": mean(d["q_direct"]),
            "A_llm_direct_mean_s": mean(d["llm_direct"]),
            "C_window_incidence": pct(d["win_events"], d["win_n"]),
            "window_total_rebuffer_s": d["win_total_s"],
        })

    return {
        "decisions": n,
        "queue_serve_n": n_qserve,
        "queue_serve_share": pct(n_qserve, n),
        "window_W": window,
        "total_rebuffer_s_run": total_reb_all,
        "A_direct": {
            "queue_serve_mean_s": mean(q_direct),
            "llm_served_mean_s": mean(llm_direct),
            "queue_serve_n": len(q_direct),
            "llm_served_n": len(llm_direct),
        },
        "B_lagged": {
            "post_queue_offsets_1..W_mean_s": mean(lagged),
            "run_mean_s": mean([r.get("rebuffer_after_s") for r in rows]),
            "n": len([x for x in lagged if x is not None]),
        },
        "C_incidence": {
            "windows_with_rebuffer_event": win_has_event,
            "queue_serve_windows": n_qserve,
            "rate": pct(win_has_event, n_qserve),
            "window_total_rebuffer_s": win_total_s,
        },
        "by_buffer_band": bands_out,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", help="LABEL=path/to/decisions.jsonl")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--window", type=int, default=None,
                    help="window W (default: auto-detect k per file)")
    args = ap.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    report = {}
    for item in args.inputs:
        label, _, path = item.partition("=")
        rows = load(path)
        w = args.window or detect_k(rows)
        report[label] = {"source": path, **analyse(rows, w)}

    # cross-drafter reference: mpc-labelled run, if present
    ref = next((k for k in report if k.lower().startswith(("m1a", "mpc"))), None)
    if ref:
        rc = report[ref]["C_incidence"]["rate"]
        for k, v in report.items():
            if k == ref or rc in (None, 0):
                continue
            v["C_incidence"]["vs_mpc_ref_ratio"] = (
                None if v["C_incidence"]["rate"] is None else v["C_incidence"]["rate"] / rc)

    (out / "queue_safety.json").write_text(json.dumps(report, indent=2, sort_keys=True))

    lines = ["label,decisions,q_share,W,A_queue_mean_s,A_llm_mean_s,"
             "B_lagged_mean_s,B_run_mean_s,C_incidence,C_vs_mpc_ratio,"
             "window_total_rebuffer_s,run_total_rebuffer_s"]
    for k, v in report.items():
        lines.append(",".join(str(x) for x in [
            k, v["decisions"], f"{v['queue_serve_share']:.6f}" if v['queue_serve_share'] else 0,
            v["window_W"],
            v["A_direct"]["queue_serve_mean_s"], v["A_direct"]["llm_served_mean_s"],
            v["B_lagged"]["post_queue_offsets_1..W_mean_s"], v["B_lagged"]["run_mean_s"],
            v["C_incidence"]["rate"], v["C_incidence"].get("vs_mpc_ref_ratio"),
            v["C_incidence"]["window_total_rebuffer_s"], v["total_rebuffer_s_run"],
        ]))
    (out / "queue_safety.csv").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
