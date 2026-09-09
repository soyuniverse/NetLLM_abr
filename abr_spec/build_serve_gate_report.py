#!/usr/bin/env python3
"""abr_spec/build_serve_gate_report.py -- the serve-time-gate campaign table.

soyun / speculative inference.  Pure CPU.  Joins per phase in
results/soyun/serve_gate_20260909/ (+ the drafter_ab_20260908 controls):
selector_metrics.json, analysis/decision_analysis_*, analysis/queue_safety.json,
result.json (serve_gate provenance) into serve_gate_20260909/analysis/
serve_gate_table.{csv,md}, with the four pre-fixed judgement criteria per row.

    python abr_spec/build_serve_gate_report.py
"""
import argparse
import csv
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SG = REPO / "results" / "soyun" / "serve_gate_20260909"
DA = REPO / "results" / "soyun" / "drafter_ab_20260908"

A1_LAT = 80.6269
A1_QOE = 0.94872
A1_REB = 6.39172

DREB_MAX = 0.64
QOE_MIN = -1.5
SPEEDUP_MIN = 1.24
MPC_C = 0.005780346820809248

CONTROLS = {
    "m2_repeat_k3": ("repeat-last", 3), "m3_hybrid_k3": ("hybrid", 3),
    "m4_repeat_k5": ("repeat-last", 5), "m5_hybrid_k5": ("hybrid", 5),
    "m2_ctrl": ("repeat-last", 3), "m3_ctrl": ("hybrid", 3), "m5_ctrl": ("hybrid", 5),
}


def jload(p):
    p = Path(p)
    return json.loads(p.read_text()) if p.is_file() else {}


def g(d, *ks, default=None):
    for k in ks:
        if not isinstance(d, dict):
            return default
        d = d.get(k)
    return default if d is None else d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phases", nargs="*", default=None)
    args = ap.parse_args()

    qs = {**jload(DA / "analysis" / "queue_safety.json"),
          **jload(SG / "analysis" / "queue_safety.json")}

    phases = args.phases
    if not phases:
        gate_ph = sorted(p.name for p in SG.iterdir()
                         if p.is_dir() and (p / "selector_metrics.json").is_file())
        phases = ["m2_repeat_k3", "m3_hybrid_k3", "m4_repeat_k5", "m5_hybrid_k5"] + gate_ph

    rows = []
    for ph in phases:
        root = DA if (ph in CONTROLS and (DA / ph).is_dir()) else SG
        m = jload(root / ph / "selector_metrics.json")
        if not m:
            continue
        res = jload(root / ph / "result.json")
        da = jload((DA if root is DA else SG) / "analysis" / f"decision_analysis_{ph}.json")
        sg = g(res, "serve_gate", default={})
        ic = m["inference_calls"]
        lat = m["inference_latency_mean_ms"]
        reb = m["total_rebuffer_s"]
        dq = 100 * (m["qoe_raw_mean"] - A1_QOE) / A1_QOE
        spd = A1_LAT / lat
        dreb = reb - A1_REB
        C = g(qs.get(ph, {}), "C_incidence", "rate")
        drafter, k = CONTROLS.get(ph, (None, None))
        if drafter is None:
            drafter = "hybrid" if "hybrid" in ph else ("repeat-last" if "repeat" in ph else "?")
            k = 5 if "k5" in ph else 3
        floor = sg.get("floor_seconds", 0.0)
        mode = "none" if not floor else (sg.get("mode") or "fallback")

        c_total = "PASS" if dreb <= DREB_MAX else "FAIL"
        c_incid = "PASS" if (C is not None and C <= MPC_C) else ("FAIL" if C is not None else "?")
        c_spd = "PASS" if spd >= SPEEDUP_MIN else "FAIL"
        c_qoe = "PASS" if dq >= QOE_MIN else "FAIL"
        npass = sum(x == "PASS" for x in (c_total, c_incid, c_spd, c_qoe))

        rows.append({
            "phase": ph, "drafter": drafter, "k": k, "gate": mode, "floor_s": floor,
            "gate_trips": sg.get("gate_trips", ""), "safe_serves": sg.get("safe_serves", ""),
            "qoe": round(m["qoe_raw_mean"], 5), "d_qoe_pct": round(dq, 2),
            "speedup_vs_a1": round(spd, 3), "latency_ms": round(lat, 2),
            "q": round(m["queued_actions_served"] / ic, 4),
            "acceptance": round(m["acceptance_rate"], 4),
            "draft_1step": round(g(da, "overall", "mpc_step1_rate") or 0, 4),
            "rebuffer_s": round(reb, 3), "d_rebuffer_s": round(dreb, 3),
            "fb_total": m["fallback_calls"], "fb_buffer": m["buffer_mismatch_fallbacks"],
            "incidence_C": None if C is None else round(C, 5),
            "crit_total": c_total, "crit_incidence": c_incid,
            "crit_speedup": c_spd, "crit_qoe": c_qoe, "n_pass": npass,
        })

    cols = list(rows[0].keys())
    out = SG / "analysis"
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "serve_gate_table.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    md = ["# Serve-time buffer gate -- serve_gate_20260909", "",
          f"A1: QoE {A1_QOE:.5f} / latency {A1_LAT:.2f} ms / rebuffer {A1_REB:.3f} s. "
          f"Criteria T/I/S/Q: dRebuffer <= {DREB_MAX}s / incidence C <= {MPC_C*100:.3f}% / "
          f"speedup >= {SPEEDUP_MIN}x / dQoE >= {QOE_MIN}%.", "",
          "| phase | drafter | k | gate | floor | trips | QoE | dQoE% | speedup | q | "
          "draft 1-step | rebuf (s) | dRebuf | C% | T/I/S/Q | n |",
          "|" + "---|" * 16]
    for r in rows:
        md.append("| " + " | ".join(str(x) for x in [
            r["phase"], r["drafter"], r["k"], r["gate"],
            r["floor_s"] or "", r["gate_trips"],
            f'{r["qoe"]:.5f}', f'{r["d_qoe_pct"]:+.2f}', f'{r["speedup_vs_a1"]:.3f}x',
            f'{r["q"]*100:.1f}%', f'{r["draft_1step"]*100:.1f}%',
            f'{r["rebuffer_s"]:.2f}', f'{r["d_rebuffer_s"]:+.2f}',
            "" if r["incidence_C"] is None else f'{r["incidence_C"]*100:.3f}',
            f'{r["crit_total"][0]}/{r["crit_incidence"][0]}/{r["crit_speedup"][0]}/{r["crit_qoe"][0]}',
            r["n_pass"],
        ]) + " |")
    (out / "serve_gate_table.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
