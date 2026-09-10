#!/usr/bin/env python3
"""abr_spec/build_seed_sweep_report.py -- G1 drafter seed sweep summary.

soyun / speculative inference.  Reads the seed-1 phases from
drafter_ab_20260908 + serve_gate_20260909/m5_ctrl (hybrid k5) and the seed-2/3/4
phases from drafter_seed_sweep_20260910, and prints, per (condition):

  * QoE / total-rebuffering / speedup / q / 1-step, per seed and mean +- std (n=4)
  * per-trace rebuffer concentration (top-1 trace share of the total) -- the
    "outlier domination" check
  * ratio vs the same-seed A1

No new runs.  Pure aggregation.
"""
import json, math, sys, collections
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SW = REPO / "results/soyun/drafter_seed_sweep_20260910"
AB = REPO / "results/soyun/drafter_ab_20260908"
SG = REPO / "results/soyun/serve_gate_20260909"

# condition -> {seed -> phase dir}
COND = {
    "A1 (no spec)":       {1: AB/"a1_all_off",        2: SW/"a1_s2", 3: SW/"a1_s3", 4: SW/"a1_s4"},
    "m2 repeat-last k3":  {1: AB/"m2_repeat_k3",      2: SW/"m2_s2", 3: SW/"m2_s3", 4: SW/"m2_s4"},
    "m3 hybrid k3":       {1: AB/"m3_hybrid_k3",      2: SW/"m3_s2", 3: SW/"m3_s3", 4: SW/"m3_s4"},
    "m4 repeat-last k5":  {1: AB/"m4_repeat_k5",      2: SW/"m4_s2", 3: SW/"m4_s3", 4: SW/"m4_s4"},
    "m5 hybrid k5":       {1: AB/"m5_hybrid_k5",      2: SG/"m5_ctrl_s2", 3: SG/"m5_ctrl_s3", 4: SG/"m5_ctrl_s4"},
    "m6 repeat-last k3+sel": {1: AB/"m6_best_plus_selectors", 2: SW/"m6_s2", 3: SW/"m6_s3", 4: SW/"m6_s4"},
}

A1_LAT_SEED1 = 80.62689349575444  # drafter_ab_20260908/a1_all_off, same driver 570


def load(p):
    m = json.load(open(p/"selector_metrics.json"))
    return m


def trace_conc_raw(p):
    """A1 (non-spec) has no decisions.jsonl -- read per-trace result_sim files.
    col 3 (0-indexed) is per-chunk rebuffer seconds."""
    files = sorted(p.glob("raw/**/result_sim_abr_*"))
    if not files:
        return None
    per = []
    for f in files:
        tot = 0.0
        # skip first chunk/trace: startup rebuffer, excluded from total_rebuffer_s
        for line in open(f).read().splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 4:
                try:
                    tot += float(parts[3])
                except ValueError:
                    pass
        per.append(tot)
    total = sum(per)
    if total <= 0.01:
        return (0.0, 0, total, None)
    return (max(per)/total, sum(1 for v in per if v > 0.5), total, None)


def trace_conc(p):
    """top-1 trace share of total rebuffering, count of traces > 0.5 s, and
    1-step draft/LLM agreement over draft_verify rows."""
    f = p/"decisions.jsonl"
    if not f.exists() or f.stat().st_size == 0:
        return trace_conc_raw(p)
    reb = collections.defaultdict(float)
    m1 = t1 = 0
    for line in open(f):
        d = json.loads(line)
        ti = d.get("trace_idx")
        reb[ti] += d.get("rebuffer_after_s", 0) or 0
        da = d.get("mpc_draft_actions"); la = d.get("llm_target_actions")
        if d.get("stage") == "draft_verify" and da and la:
            t1 += 1
            if da[0] == la[0]:
                m1 += 1
    tot = sum(reb.values())
    s1 = (m1/t1) if t1 else None
    if tot <= 0.01:
        return (0.0, 0, tot, s1)
    top = max(reb.values())
    nz = sum(1 for v in reb.values() if v > 0.5)
    return (top/tot, nz, tot, s1)


def stats(xs):
    n = len(xs); mu = sum(xs)/n
    sd = math.sqrt(sum((x-mu)**2 for x in xs)/(n-1)) if n > 1 else 0.0
    return mu, sd


def main():
    a1 = {s: load(COND["A1 (no spec)"][s]) for s in (1,2,3,4)}
    print(f"{'condition':22} {'seed':>4} {'QoE':>8} {'dQoE%':>7} {'rebuf':>7} {'drebuf':>7} "
          f"{'lat_ms':>7} {'speedup':>8} {'q%':>6} {'1step%':>7} {'top1%':>6} {'nz':>3}")
    rows = {}
    for cond, seeds in COND.items():
        rows[cond] = collections.defaultdict(list)
        for s in (1,2,3,4):
            p = seeds[s]
            if not (p/"selector_metrics.json").exists():
                print(f"{cond:22} {s:>4}  MISSING {p}")
                continue
            m = load(p)
            qoe = m["qoe_raw_mean"]; reb = m["total_rebuffer_s"]
            lat = m["inference_latency_mean_ms"]
            q = m.get("llm_call_reduction_ratio", 0)*100
            base_qoe = a1[s]["qoe_raw_mean"]; base_reb = a1[s]["total_rebuffer_s"]
            dqoe = (qoe-base_qoe)/base_qoe*100
            dreb = reb-base_reb
            a1lat = a1[s]["inference_latency_mean_ms"]
            spd = a1lat/lat
            tc = trace_conc(p)
            top1 = tc[0]*100 if tc else float('nan')
            nz = tc[1] if tc else -1
            s1 = tc[3] if tc else None
            s1s = f"{s1*100:6.1f}" if isinstance(s1,(int,float)) else "   -  "
            print(f"{cond:22} {s:>4} {qoe:8.4f} {dqoe:7.2f} {reb:7.2f} {dreb:7.2f} "
                  f"{lat:7.2f} {spd:8.3f} {q:6.1f} {s1s} {top1:6.1f} {nz:>3}")
            rows[cond]["qoe"].append(qoe); rows[cond]["dqoe"].append(dqoe)
            rows[cond]["reb"].append(reb); rows[cond]["dreb"].append(dreb)
            rows[cond]["spd"].append(spd); rows[cond]["q"].append(q)
            if isinstance(s1,(int,float)): rows[cond]["s1"].append(s1*100)
        print()

    print("\n=== mean +- std (n=4) ===")
    print(f"{'condition':22} {'QoE':>16} {'dQoE%':>15} {'rebuf s':>16} {'drebuf s':>16} {'speedup':>15} {'q%':>13}")
    for cond in COND:
        r = rows[cond]
        if not r["qoe"]:
            continue
        def f(k, p=2):
            mu, sd = stats(r[k]); return f"{mu:.{p}f}+-{sd:.{p}f}"
        print(f"{cond:22} {f('qoe',4):>16} {f('dqoe'):>15} {f('reb'):>16} {f('dreb'):>16} {f('spd',3):>15} {f('q',1):>13}")


if __name__ == "__main__":
    main()
