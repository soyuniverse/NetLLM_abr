#!/usr/bin/env python3
"""abr_spec/derive_decision_summary.py -- compress decisions.jsonl into a tracked summary.

soyun / speculative inference.  CPU only.

``decisions.jsonl`` (one JSON line per ABR decision, ~5.5 MB per 4,700-decision
run) is gitignored under ``results/soyun/``, so it dies with the instance.  This
script distils every statistic the analysis so far has needed -- and the two the
next analysis will need -- into ``results/soyun/derived/<run_id>_summary.json``,
which IS tracked.  After that the raw file can be lost without forcing a re-run.

Definitions are imported from ``abr_spec/analyze_decisions.py`` (``cv``, the
buffer/CV band edges, ``enrich``) so the derived numbers are the same statistics
BASELINE6 and SWEEP_SPEC were written against, not a re-derivation.

What is preserved per phase
  - counts: decisions, traces, per-stage split, q, acceptance, target PLM calls
  - accepted-prefix histogram + mean, for the real MPC draft and for the
    hypothetical "repeat the last action" drafter
  - fallback counts by reason
  - buffer-band x CV-band cross tables: MPC 1-step match, repeat-last match,
    LLM autocorrelation, q, rebuffer rate
  - latency mean/p50/p90/p95/p99/max overall and per stage
  - MPC rollout CPU time, isolated, and its share of latency
  - rebuffer rate after a queue-served decision vs after an LLM-call decision
  - the source file's line count, byte size and sha256, so a later reader can
    tell exactly what was discarded

What is NOT preserved (accept this before deleting the raw file)
  - per-decision sequences: you cannot re-bucket by a *new* dimension, re-time
    anything, or replay a trajectory. Only the axes below survive.

    python abr_spec/derive_decision_summary.py --out-dir results/soyun/derived
"""
import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "abr_spec"))

# Imported, not re-derived: these are the exact definitions BASELINE6 and
# SWEEP_SPEC were written against (band edges, the CV statistic, and the
# llm_action / prev_llm_action derivation).
from analyze_decisions import (  # noqa: E402
    BUFFER_BANDS,
    CV_BANDS,
    enrich,
    load,
    pct,
)

SCHEMA_VERSION = 2


def prefix_len(draft, target):
    n = 0
    for d, t in zip(draft, target):
        if d != t:
            break
        n += 1
    return n


def quantiles(values):
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None

    def q(p):
        return vals[min(len(vals) - 1, int(round(p * (len(vals) - 1))))]

    return {"n": len(vals), "mean": sum(vals) / len(vals), "p50": q(0.50),
            "p90": q(0.90), "p95": q(0.95), "p99": q(0.99), "max": vals[-1],
            "total": sum(vals)}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rate_block(rows):
    """MPC / repeat-last / autocorrelation / q / rebuffer over one subset."""
    verify = [r for r in rows if r.get("stage") == "draft_verify"
              and r.get("mpc_draft_actions") and r.get("llm_target_action") is not None]
    llm = [r for r in rows if r.get("llm_action") is not None]
    adj = [r for r in llm if r.get("prev_llm_action_adjacent") is not None]
    serves = [r for r in rows if r.get("stage") == "queue_serve"]
    reb = [r for r in rows if r.get("rebuffer_after_s") is not None]
    return {
        "n_decisions": len(rows),
        "n_verify": len(verify),
        "n_llm_actions": len(llm),
        "mpc_step1_rate": pct(sum(1 for r in verify
                                  if r["mpc_draft_actions"][0] == r["llm_target_action"]),
                              len(verify)),
        "repeat_last_rate_on_verify": pct(
            sum(1 for r in verify if r["last_action"] == r["llm_target_action"]),
            len(verify)),
        "repeat_last_rate_all_llm": pct(
            sum(1 for r in llm if r["last_action"] == r["llm_action"]), len(llm)),
        "llm_autocorr_adjacent_rate": pct(
            sum(1 for r in adj if r["llm_action"] == r["prev_llm_action_adjacent"]),
            len(adj)),
        "llm_autocorr_adjacent_n": len(adj),
        "q_queue_serve_share": pct(len(serves), len(rows)),
        "rebuffer_rate": pct(sum(1 for r in reb if r["rebuffer_after_s"] > 0), len(reb)),
        "rebuffer_n": len(reb),
    }


def phase_summary(phase_dir, run_id):
    jsonl = phase_dir / "decisions.jsonl"
    if not jsonl.is_file():
        return None
    rows = enrich(load(str(jsonl)))
    if not rows:
        return None
    st = os.stat(jsonl)
    with open(jsonl) as f:
        lines = sum(1 for _ in f)

    cfg = {}
    sm = phase_dir / "selector_metrics.json"
    if sm.is_file():
        m = json.loads(sm.read_text())
        cfg = {k: m.get(k) for k in (
            "speculative_draft_steps", "speculative_verification_mode",
            "speculative_buffer_tolerance", "speculative_state_tolerance",
            "speculative_return_tolerance", "temporal_selector", "selector",
            "selector_history_steps", "inference_calls", "target_plm_calls",
            "llm_call_reduction_ratio", "acceptance_rate", "qoe_raw_mean",
            "mean_bitrate_mbps", "total_rebuffer_s", "mean_smoothness_mbps",
            "inference_latency_mean_ms", "original_tokens_mean",
            "selected_tokens_mean")}
    mp = phase_dir / "manifest_phase.json"
    if mp.is_file():
        man = json.loads(mp.read_text())
        cfg["drafter"] = man.get("drafter")
        cfg["git_commit"] = man.get("git_commit")
        cfg["utc"] = man.get("utc")
        cfg["gpu"] = man.get("gpu")

    verify = [r for r in rows if r.get("stage") == "draft_verify"
              and r.get("mpc_draft_actions") and r.get("llm_target_actions")]
    k = max((len(r["mpc_draft_actions"]) for r in verify), default=0)
    mpc_pref = Counter(prefix_len(r["mpc_draft_actions"], r["llm_target_actions"])
                       for r in verify)
    rep_pref = Counter(prefix_len([r["last_action"]] * len(r["llm_target_actions"]),
                                  r["llm_target_actions"]) for r in verify)

    serves = [r for r in rows if r.get("stage") == "queue_serve"]
    llm_calls = [r for r in rows if r.get("stage") in ("draft_verify", "fallback", "plain")]

    def reb_stats(sub):
        vals = [r["rebuffer_after_s"] for r in sub if r.get("rebuffer_after_s") is not None]
        if not vals:
            return {"n": 0}
        hits = sum(1 for v in vals if v > 0)
        return {"n": len(vals), "rebuffer_events": hits,
                "rebuffer_rate": hits / len(vals),
                "mean_rebuffer_s": sum(vals) / len(vals),
                "total_rebuffer_s": sum(vals)}

    per_stage = {}
    for stage in sorted({r.get("stage") for r in rows}):
        sub = [r for r in rows if r.get("stage") == stage]
        per_stage[stage] = {
            "count": len(sub), "share": pct(len(sub), len(rows)),
            "latency_ms": quantiles(r.get("latency_ms") for r in sub),
            "context_selected_tokens_mean": (
                pct(sum(r.get("context_selected_tokens") or 0 for r in sub), len(sub))),
        }

    mpc_cpu = [r.get("mpc_rollout_cpu_ms") for r in rows]
    lat_all = [r.get("latency_ms") or 0.0 for r in rows]
    obs_cpu = [r.get("throughput_observe_cpu_ms") for r in rows]

    def by(key, bands):
        order = [b[0] for b in bands] + ["unknown"]
        groups = {}
        for r in rows:
            groups.setdefault(r[key], []).append(r)
        return [{"band": b, **rate_block(groups[b])} for b in order if groups.get(b)]

    return {
        "phase": phase_dir.name,
        "run_id": run_id,
        "source": {
            "path": str(jsonl.relative_to(REPO)),
            "lines": lines,
            "bytes": st.st_size,
            "sha256": sha256(jsonl),
            "status": "NOT tracked by git -- lost when the instance is released",
        },
        "config": cfg,
        "totals": {
            "decisions": len(rows),
            "traces": len({r.get("trace_idx") for r in rows}),
            "k": k,
            "stage_counts": dict(Counter(r.get("stage") for r in rows)),
            "q_queue_serve_share": pct(len(serves), len(rows)),
            # accepted_actions / drafted_actions, matching upstream's counter.
            # The denominator is the *actual* rollout length per verify, not
            # k * n_verify: near the end of a video the horizon is clipped.
            "acceptance_rate": pct(
                sum(i * c for i, c in mpc_pref.items()),
                sum(len(r["mpc_draft_actions"]) for r in verify)),
            "drafted_actions": sum(len(r["mpc_draft_actions"]) for r in verify),
            "target_plm_called": sum(1 for r in rows if r.get("target_plm_called")),
        },
        "accepted_prefix": {
            "k": k,
            "mpc_hist": {str(i): mpc_pref.get(i, 0) for i in range(k + 1)},
            "mpc_mean": pct(sum(i * c for i, c in mpc_pref.items()), len(verify)),
            "repeat_last_hist": {str(i): rep_pref.get(i, 0) for i in range(k + 1)},
            "repeat_last_mean": pct(sum(i * c for i, c in rep_pref.items()), len(verify)),
        },
        "fallback_reasons": dict(Counter(r.get("fallback_reason") for r in rows
                                         if r.get("fallback_reason"))),
        "latency_ms": {
            "overall": quantiles(r.get("latency_ms") for r in rows),
            "by_stage": per_stage,
        },
        "mpc_rollout_cpu_ms": {
            **(quantiles(mpc_cpu) or {}),
            "share_of_total_latency": pct(sum(v or 0 for v in mpc_cpu), sum(lat_all)),
            "per_decision_mean_over_all": pct(sum(v or 0 for v in mpc_cpu), len(rows)),
        },
        "throughput_observe_cpu_ms": {
            **(quantiles(obs_cpu) or {}),
            "share_of_total_latency": pct(sum(v or 0 for v in obs_cpu), sum(lat_all)),
        },
        "rebuffer_after_decision": {
            "queue_serve": reb_stats(serves),
            "llm_call": reb_stats(llm_calls),
            "all": reb_stats(rows),
        },
        "crosstab_buffer_band": by("buffer_band", BUFFER_BANDS),
        "crosstab_cv_band": by("cv_band", CV_BANDS),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results-dir", default=str(REPO / "results" / "soyun"))
    ap.add_argument("--out-dir", default=str(REPO / "results" / "soyun" / "derived"))
    args = ap.parse_args()

    root, out = Path(args.results_dir), Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    index = {"schema_version": SCHEMA_VERSION, "runs": {}}

    for run_dir in sorted(root.iterdir()):
        if not run_dir.is_dir() or run_dir.name == "derived":
            continue
        phases = []
        for phase_dir in sorted(run_dir.iterdir()):
            if not phase_dir.is_dir():
                continue
            s = phase_summary(phase_dir, run_dir.name)
            if s:
                phases.append(s)
        if not phases:
            continue
        doc = {"schema_version": SCHEMA_VERSION, "run_id": run_dir.name,
               "generated_from": "decisions.jsonl (gitignored)",
               "phases": phases}
        path = out / f"{run_dir.name}_summary.json"
        path.write_text(json.dumps(doc, indent=1, sort_keys=True))
        index["runs"][run_dir.name] = {
            "file": path.name,
            "phases": [p["phase"] for p in phases],
            "source_lines": sum(p["source"]["lines"] for p in phases),
            "source_bytes": sum(p["source"]["bytes"] for p in phases),
            "summary_bytes": path.stat().st_size,
        }
        print(f"{run_dir.name:24s} {len(phases):2d} phase(s)  "
              f"{sum(p['source']['bytes'] for p in phases)/1e6:6.1f} MB raw -> "
              f"{path.stat().st_size/1024:6.1f} KB  {path.name}")

    (out / "index.json").write_text(json.dumps(index, indent=1, sort_keys=True))
    tot_raw = sum(v["source_bytes"] for v in index["runs"].values())
    tot_sum = sum(v["summary_bytes"] for v in index["runs"].values())
    print(f"\ntotal {tot_raw/1e6:.1f} MB raw -> {tot_sum/1024:.1f} KB tracked "
          f"({tot_raw/max(tot_sum,1):.0f}x compression)")


if __name__ == "__main__":
    main()
