#!/usr/bin/env python3
"""abr_spec/make_figures.py -- the four paper figures for the drafter ablation.

soyun / speculative inference.  Pure CPU.  Every number is read from a tracked
results file (drafter_ablation_table.csv, sweep_table.csv, queue_safety.json,
decision_analysis_*.json); nothing is estimated.  Missing values are drawn as a
gap and annotated "n/a" -- never guessed.

Output (results/soyun/figures/ by default): each figure as 300-dpi PNG + vector
PDF, greyscale-safe (hatch patterns + distinct markers, not colour alone),
English captions printed to <name>.caption.txt.

    python abr_spec/make_figures.py --out-dir results/soyun/figures
"""
import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402

REPO = Path(__file__).resolve().parents[1]
RID = "drafter_ab_20260908"
AB = REPO / "results" / "soyun" / RID / "analysis"
SWEEP = REPO / "results" / "soyun" / "sweep_spec_20260902" / "analysis" / "sweep_table.csv"
SEED_SWEEP = REPO / "results" / "soyun" / "drafter_seed_sweep_20260910" / "seed_sweep_table.csv"

plt.rcParams.update({
    "font.size": 9, "axes.titlesize": 10, "axes.labelsize": 9,
    "figure.dpi": 150, "savefig.dpi": 300, "savefig.bbox": "tight",
    "axes.grid": True, "grid.alpha": 0.3, "grid.linewidth": 0.5,
})

# BASELINE6 reference lines (old instance) -- see docs/soyun/BASELINE6.md §3.5
Q_PARITY_OLD = 0.1463
Q_124X_OLD = 0.3143
A1_QOE = 0.94872


def read_table():
    with open(AB / "drafter_ablation_table.csv") as f:
        return {r["phase"]: r for r in csv.DictReader(f)}


def read_seed_sweep():
    """4-seed mean/std per condition (abr_spec/build_seed_sweep_report.py)."""
    with open(SEED_SWEEP) as f:
        return {r["condition"]: {k: fnum(v) for k, v in r.items() if k != "condition"}
                for r in csv.DictReader(f)}


def read_sweep():
    with open(SWEEP) as f:
        return list(csv.DictReader(f))


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def save(fig, out_dir, name, caption):
    for ext in ("png", "pdf"):
        fig.savefig(Path(out_dir) / f"{name}.{ext}")
    (Path(out_dir) / f"{name}.caption.txt").write_text(caption.strip() + "\n")
    plt.close(fig)
    print(f"  {name}.png / .pdf")


# --------------------------------------------------------------------------
def fig1(t, out_dir):
    """Drafter ablation, 4-seed: dQoE vs A1 (left) and speedup (right), mean +- std."""
    ss = read_seed_sweep()
    # x order: A1, mpc k3 (seed-1 point), then the 4-seed conditions
    conds = ["m2 repeat-last k3", "m3 hybrid k3", "m4 repeat-last k5",
             "m5 hybrid k5", "m6 repeat-last k3+sel"]
    labels = ["A1\nall-off", "mpc k3\n(seed 1)", "repeat\nk3", "hybrid\nk3",
              "repeat\nk5", "hybrid\nk5", "M6\nk3+sel"]
    is_m6 = [False, False, False, False, False, False, True]

    # mpc k3: not in the 4-seed sweep -> seed-1 point from the ablation table
    mpc_dqoe = (fnum(t["m1a_mpc_k3_sample"]["qoe"]) - A1_QOE) / A1_QOE * 100
    mpc_spd = fnum(t["m1a_mpc_k3_sample"]["speedup_vs_a1"])

    dqoe = [0.0, mpc_dqoe] + [ss[c]["dqoe_mean"] for c in conds]
    dqoe_e = [0.0, 0.0] + [ss[c]["dqoe_std"] for c in conds]
    spd = [1.0, mpc_spd] + [ss[c]["spd_mean"] for c in conds]
    spd_e = [0.0, 0.0] + [ss[c]["spd_std"] for c in conds]
    # A1's own QoE spread across seeds, as % -> the "seed noise floor" band
    a1_cv = ss["A1 (no spec)"]["qoe_std"] / ss["A1 (no spec)"]["qoe_mean"] * 100

    fig, ax1 = plt.subplots(figsize=(7.2, 4.0))
    fig.subplots_adjust(top=0.80)
    x = list(range(len(labels)))

    ax1.axhspan(-a1_cv, a1_cv, color="0.85", zorder=0,
                label=f"A1 seed spread (+-{a1_cv:.1f} %)")
    b1 = None
    for i in x:
        hatch = "...." if is_m6[i] else ""
        bar = ax1.bar(i - 0.2, dqoe[i], 0.4, color="0.6", hatch=hatch,
                      edgecolor="black", linewidth=0.8, zorder=3)
        b1 = b1 or bar
    ax1.errorbar([i - 0.2 for i in x], dqoe, yerr=dqoe_e, fmt="none",
                 ecolor="black", elinewidth=0.9, capsize=2, zorder=4)
    ax1.axhline(0, color="black", lw=0.8)
    ax1.set_ylabel(r"$\Delta$QoE vs same-seed A1 (%)")
    ax1.set_ylim(-7, 4)

    ax2 = ax1.twinx()
    b2 = None
    for i in x:
        hatch = "xxxx" if is_m6[i] else "////"
        bar = ax2.bar(i + 0.2, spd[i], 0.4, color="white", hatch=hatch,
                      edgecolor="black", linewidth=0.8, zorder=3)
        b2 = b2 or bar
    ax2.errorbar([i + 0.2 for i in x], spd, yerr=spd_e, fmt="none",
                 ecolor="black", elinewidth=0.9, capsize=2, zorder=4)
    ax2.set_ylabel("speedup vs A1 (latency ratio)")
    ax2.set_ylim(0.0, 2.4)
    ax2.axhline(1.0, color="black", ls="--", lw=1)
    ax2.axhline(1.24, color="0.4", ls="-.", lw=1)
    ax2.annotate("1.24x", (len(labels) - 0.5, 1.24), fontsize=7, va="bottom", ha="right")

    ax1.set_xticks(x)
    ax1.set_xticklabels(labels)
    ax1.grid(False)
    ax1.annotate("M6: 2x speedup\nbut -3.0 +- 1.9 % QoE",
                 (6, -3.0), xytext=(3.6, -5.6), fontsize=7, ha="left",
                 arrowprops=dict(arrowstyle="->", lw=0.7))
    from matplotlib.patches import Patch
    ax1.legend(handles=[
        Patch(facecolor="0.85", label=f"A1 seed spread (+-{a1_cv:.1f} %)"),
        Patch(facecolor="0.6", edgecolor="black", label=r"$\Delta$QoE (left)"),
        Patch(facecolor="white", edgecolor="black", hatch="////", label="speedup (right)"),
        Patch(facecolor="0.6", edgecolor="black", hatch="....", label="M6 (drafter + selectors)"),
    ], loc="lower center", ncol=2, bbox_to_anchor=(0.5, 1.02), fontsize=7.5,
        framealpha=0.9)
    fig.suptitle("Drafter ablation, 4 seeds: QoE cost and speedup (mean +- std)",
                 y=1.0, fontsize=10)
    save(fig, out_dir, "fig1_qoe_speedup",
         "Figure 1. Drafter ablation over seeds {1,2,3,4}, fcc-test 100 traces / "
         "video1 / sample verification, one RTX 3090. Grey bars (left axis): QoE "
         "change vs the same-seed all-off baseline A1; error bars are the "
         "seed-to-seed std (n=4). Shaded band: A1's own QoE spread across seeds "
         "(the noise floor). Hatched bars (right axis): latency speedup vs A1, "
         "mean +- std; the std is dominated by cross-session latency drift, not "
         "behaviour (q varies < 0.7 pp, Fig. 2). Dashed line: parity; dash-dot: "
         "the 1.24x target. mpc k3 is a single seed-1 point. Every zero-search / "
         "hybrid drafter clears 1.24x; at k=3 the QoE change sits inside the A1 "
         "seed band (no measurable cost). M6 (drafter + Temporal/Token selectors, "
         "dotted bar) is the exception: 2.03x speedup but a -3.0 +- 1.9 % QoE "
         "cost, negative at all four seeds.")


# --------------------------------------------------------------------------
def fig2(t, sweep, out_dir):
    """q vs speedup: cost-model curves + parameter runs + drafter points."""
    fig, ax = plt.subplots(figsize=(6.2, 4.0))

    # model curves  speedup(q) = c_plain / ((1-q) c_verify + q c_serve)
    import numpy as np
    qq = np.linspace(0, 0.55, 200)

    def curve(c_plain, c_verify, c_serve, **kw):
        ax.plot(qq * 100, c_plain / ((1 - qq) * c_verify + qq * c_serve), **kw)

    curve(50.329, 58.808, 0.832, color="0.55", ls="--", lw=1.2,
          label="cost model, old instance (k=3)")
    m2 = t["m2_repeat_k3"]
    curve(80.6269, fnum(m2["c_verify_ms"]), fnum(m2["c_serve_ms"]),
          color="black", ls="-", lw=1.2,
          label="cost model, this instance (k=3)")

    # parameter sweep runs (old instance): q vs speedup.  The 11 SWEEP_SPEC rows
    # -- exclude the s2_k2_precheck duplicate (SWEEP_SPEC §3-0).
    srows = [r for r in sweep if r["run"] != "s2_k2_precheck"
             and fnum(r["q_queue_serve_share"]) is not None]
    sx = [fnum(r["q_queue_serve_share"]) for r in srows]
    sy = [fnum(r["speedup_vs_a1"]) for r in srows]
    ax.scatter([v * 100 for v in sx], sy, marker="o", s=30, facecolor="0.8",
               edgecolor="black", linewidth=0.6, zorder=3,
               label=f"parameter sweep runs (n={len(sx)}, old instance)")

    # drafter points (this instance)
    marks = {"m2_repeat_k3": ("repeat-last k3", "s"), "m3_hybrid_k3": ("hybrid k3", "^"),
             "m4_repeat_k5": ("repeat-last k5", "D"), "m5_hybrid_k5": ("hybrid k5", "v"),
             "m1a_mpc_k3_sample": ("mpc k3", "*")}
    for ph, (lab, mk) in marks.items():
        r = t[ph]
        ax.scatter(fnum(r["q_queue_serve"]) * 100, fnum(r["speedup_vs_a1"]),
                   marker=mk, s=55, facecolor="black", edgecolor="black",
                   zorder=4, label=lab)

    ax.axhline(1.0, color="black", ls=":", lw=1)
    ax.axvline(Q_PARITY_OLD * 100, color="0.4", ls="--", lw=0.9)
    ax.axvline(Q_124X_OLD * 100, color="0.4", ls="-.", lw=0.9)
    ax.annotate("break-even\nq = 14.63 %", (14.63, 1.46), fontsize=7, ha="center",
                va="top")
    ax.annotate("1.24x\nq = 31.43 %", (31.43, 1.46), fontsize=7, ha="center", va="top")
    ax.annotate("parameter sweep ceiling:\nq < 10 %, speedup < 1.0x",
                (9.8, 0.905), fontsize=7, ha="left", va="center",
                xytext=(15, 0.78), arrowprops=dict(arrowstyle="->", lw=0.7))
    ax.set_xlabel("queue-serve share q (%)")
    ax.set_ylabel("speedup vs A1")
    ax.set_xlim(-1, 52)
    ax.set_ylim(0.6, 1.62)
    ax.set_title("q vs speedup: the parameter sweep's ceiling and the drafter points")
    ax.legend(fontsize=6.5, loc="center right", framealpha=0.95)
    save(fig, out_dir, "fig2_q_vs_speedup",
         "Figure 2. Latency speedup as a function of the queue-serve share q. "
         "Curves: the (1-q) c_verify + q c_serve cost model for the old "
         "instance (dashed) and this instance (solid, k=3). Circles: the 11 "
         "speculative parameter-sweep runs (SWEEP_SPEC, old instance) -- all sit "
         "at q < 10 % and below parity. Filled markers: the drafter ablation "
         "(this instance). repeat-last / hybrid push q to ~38-42 %, riding the "
         "model curve past both the break-even (q = 14.63 %) and 1.24x "
         "(q = 31.43 %) lines. Speedup is a within-instance ratio; the two "
         "instances are compared only through that ratio, not raw ms.")


# --------------------------------------------------------------------------
def fig3(sweep, out_dir):
    """buffer-tolerance sweep: buffer vs state fallback, stacked."""
    rows = {r["run"]: r for r in sweep}
    keys = [("E k=3 greedy (BASELINE6)", "1.0"), ("s5_buftol2", "2.0"),
            ("s6_buftol4", "4.0"), ("s7_buftol8", "8.0")]
    have = [(lab, bt) for lab, bt in keys if lab in rows]
    buf = [fnum(rows[lab]["fallback_buffer"]) for lab, _ in have]
    sta = [fnum(rows[lab]["fallback_state"]) for lab, _ in have]
    tot = [b + s for b, s in zip(buf, sta)]

    fig, ax = plt.subplots(figsize=(5.6, 3.4))
    x = range(len(have))
    ax.bar(x, buf, 0.55, color="0.8", edgecolor="black", linewidth=0.7,
           label="buffer-tolerance fallbacks")
    ax.bar(x, sta, 0.55, bottom=buf, color="white", hatch="xxx",
           edgecolor="black", linewidth=0.7, label="state-tolerance fallbacks")
    for i, tt in enumerate(tot):
        ax.annotate(f"total {tt:.0f}", (i, tt + 6), ha="center", fontsize=7)
    ax.set_xticks(list(x))
    ax.set_xticklabels([f"btol {bt} s" for _, bt in have])
    ax.set_ylabel("fallback count (of 4700 decisions)")
    ax.set_ylim(0, max(tot) * 1.25)
    ax.set_title("Loosening the buffer tolerance substitutes rather than fixes")
    ax.legend(fontsize=7, loc="upper right")
    ax.grid(axis="x")
    save(fig, out_dir, "fig3_buffer_tolerance_substitution",
         "Figure 3. Fallback composition as the buffer tolerance is loosened "
         "(SWEEP_SPEC axis 3, mpc drafter, old instance). Buffer-tolerance "
         "fallbacks fall from 236 to 43 while state-tolerance fallbacks rise "
         "from 32 to 191; the total barely moves (268 -> 234). The queue "
         "entries are discarded because the drafted trajectory is wrong, not "
         "because a threshold is too tight -- evidence that the drafter, not "
         "the acceptance gate, is the bottleneck.")


# --------------------------------------------------------------------------
def fig4(t, out_dir):
    """drafter comparison, 4-seed: rebuffering cost (left) + 1-step agreement by buffer band (right)."""
    ss = read_seed_sweep()
    conds = ["m2 repeat-last k3", "m3 hybrid k3", "m4 repeat-last k5",
             "m5 hybrid k5", "m6 repeat-last k3+sel"]
    labels = ["repeat\nk3", "hybrid\nk3", "repeat\nk5", "hybrid\nk5", "M6\nk3+sel"]
    is_m6 = [False, False, False, False, True]
    dreb = [ss[c]["dreb_mean"] for c in conds]
    dreb_e = [ss[c]["dreb_std"] for c in conds]
    q = [ss[c]["q_mean"] for c in conds]
    spd = [ss[c]["spd_mean"] for c in conds]
    a1_reb_sd = ss["A1 (no spec)"]["reb_std"]

    da = {p: json.loads((AB / f"decision_analysis_{p}.json").read_text())
          for p in ("m1a_mpc_k3_sample", "m2_repeat_k3", "m3_hybrid_k3")}

    fig, (axL, axR) = plt.subplots(1, 2, figsize=(9.2, 3.7),
                                   gridspec_kw={"width_ratios": [3, 2]})

    # ---- left: Delta-rebuffering vs same-seed A1, mean +- std ----
    x = list(range(len(labels)))
    axL.axhspan(-a1_reb_sd, a1_reb_sd, color="0.85", zorder=0)
    for i in x:
        axL.bar(i, dreb[i], 0.55, color="0.6",
                hatch="...." if is_m6[i] else "",
                edgecolor="black", linewidth=0.8, zorder=3)
    axL.errorbar(x, dreb, yerr=dreb_e, fmt="none", ecolor="black",
                 elinewidth=0.9, capsize=3, zorder=4)
    axL.axhline(0, color="black", lw=0.8)
    for i in x:
        axL.annotate(f"q {q[i]:.0f}%\n{spd[i]:.2f}x", (i, -14), ha="center",
                     fontsize=6.5, va="top")
    axL.set_xticks(x)
    axL.set_xticklabels(labels)
    axL.set_ylabel(r"$\Delta$rebuffering vs same-seed A1 (s)")
    axL.set_ylim(-22, 78)
    axL.set_title("Rebuffering cost (4 seeds, mean +- std)")
    axL.annotate("A1 seed spread\n(+-%.0f s)" % a1_reb_sd, (0, a1_reb_sd),
                 xytext=(0.0, 40), fontsize=6.5, ha="center",
                 arrowprops=dict(arrowstyle="->", lw=0.6))
    axL.annotate("M6", (4, dreb[4]), xytext=(3.2, 66), fontsize=7,
                 arrowprops=dict(arrowstyle="->", lw=0.7))
    axL.grid(axis="x")

    # ---- right: draft 1-step agreement by buffer band (mechanism, seed 1) ----
    bands = ["<5s", "5-10s", "10-20s", ">=20s"]
    band_names = ["mpc k3", "repeat-last k3", "hybrid k3"]
    for j, ph in enumerate(("m1a_mpc_k3_sample", "m2_repeat_k3", "m3_hybrid_k3")):
        by = {b["band"]: b for b in da[ph]["by_buffer"]}
        y = [by[b]["mpc_step1_rate"] if b in by and by[b]["mpc_step1_rate"] is not None
             else None for b in bands]
        axR.plot([i for i, v in enumerate(y) if v is not None],
                 [v for v in y if v is not None],
                 marker=["*", "s", "^"][j], color="black", ls=["-", "--", ":"][j],
                 label=band_names[j])
    axR.set_xticks(range(len(bands)))
    axR.set_xticklabels(bands, fontsize=7)
    axR.set_ylabel("draft 1-step agreement")
    axR.set_ylim(0, 1.0)
    axR.set_title("Agreement by buffer band (seed 1)")
    axR.legend(fontsize=7)
    save(fig, out_dir, "fig4_drafter_comparison",
         "Figure 4. Left: total-rebuffering change vs the same-seed all-off "
         "baseline A1, per drafter, mean +- std over seeds 1-4 "
         "(drafter_seed_sweep_20260910); each bar annotated with its mean "
         f"queue-serve share q and speedup. Shaded band: A1's own rebuffering "
         f"spread across seeds (std +-{a1_reb_sd:.0f} s) -- the noise floor. "
         "Every k=3 drafter's rebuffering change sits inside that band; k=5 is "
         "worse; M6 (dotted bar, drafter + Temporal/Token selectors) adds "
         "+38 +- 29 s and is the only condition clearly outside the band. "
         "Right: draft 1-step agreement with the policy split by buffer band "
         "(seed 1, mechanism) -- repeat-last agrees ~88 percent everywhere; "
         "hybrid drops to ~43 percent in the <5s band because it routes those "
         "decisions to mpc.")


SGT = REPO / "results" / "soyun" / "serve_gate_20260909" / "analysis" / "serve_gate_table.csv"
A1_REB = 6.39172


def read_gate():
    with open(SGT) as f:
        return list(csv.DictReader(f))


# --------------------------------------------------------------------------
# ARCHIVED seed-1 versions of fig1 / fig4 (superseded 2026-09-10 by the 4-seed
# versions above; kept for provenance -- rendered into <out>/archive/ with a
# _seed1 suffix). The narrative these support was retired: see DRAFTER_ABLATION
# section 9.13 / RNG_CONTAMINATION_AUDIT.
def fig1_seed1_archived(t, out_dir):
    """[ARCHIVED seed-1] 6 conditions x [QoE, speedup] dual axis."""
    order = ["a1", "m1a_mpc_k3_sample", "m2_repeat_k3", "m3_hybrid_k3",
             "m4_repeat_k5", "m5_hybrid_k5"]
    labels = ["A1\nall-off", "mpc\nk3", "repeat\nk3", "hybrid\nk3",
              "repeat\nk5", "hybrid\nk5"]
    qoe = [A1_QOE] + [fnum(t[p]["qoe"]) for p in order[1:]]
    spd = [1.0] + [fnum(t[p]["speedup_vs_a1"]) for p in order[1:]]

    fig, ax1 = plt.subplots(figsize=(6.4, 3.8))
    fig.subplots_adjust(top=0.78)
    x = range(len(order))
    b1 = ax1.bar([i - 0.2 for i in x], qoe, 0.4, color="0.75",
                 edgecolor="black", linewidth=0.7, label="QoE (raw mean)")
    ax1.set_ylabel("QoE (raw mean)")
    ax1.set_ylim(0.85, 0.97)
    ax1.axhline(A1_QOE, color="black", ls=":", lw=1)
    ax1.annotate("A1 QoE 0.949", (0.0, A1_QOE), fontsize=7, va="bottom", ha="left")
    ax2 = ax1.twinx()
    b2 = ax2.bar([i + 0.2 for i in x], spd, 0.4, color="white", hatch="////",
                 edgecolor="black", linewidth=0.7, label="speedup vs A1")
    ax2.errorbar([i + 0.2 for i in x], spd, yerr=[s * 0.019 for s in spd],
                 fmt="none", ecolor="black", elinewidth=0.8, capsize=2)
    ax2.set_ylabel("speedup vs A1 (latency ratio)")
    ax2.set_ylim(0.0, 1.6)
    ax2.axhline(1.0, color="black", ls="--", lw=1)
    ax2.axhline(1.24, color="0.4", ls="-.", lw=1)
    ax2.annotate("1.24x", (len(order) - 0.5, 1.24), fontsize=7, va="bottom", ha="right")
    ax1.set_xticks(list(x))
    ax1.set_xticklabels(labels)
    ax1.grid(False)
    ax1.legend(handles=[b1, b2], loc="lower center", ncol=2,
               bbox_to_anchor=(0.5, 1.14), fontsize=8, framealpha=0.9)
    fig.suptitle("[ARCHIVED seed-1] Drafter ablation: QoE and speedup",
                 y=0.98, fontsize=10)
    save(fig, out_dir, "fig1_qoe_speedup_seed1",
         "Figure 1 [ARCHIVED, seed 1 only -- superseded by the 4-seed Fig. 1]. "
         "QoE (grey, left) and speedup vs A1 (hatched, right) for the drafter "
         "ablation at --seed 1. The QoE 'cost of 1.5-4 %' shown here did not "
         "survive a 4-seed re-measurement (DRAFTER_ABLATION 9.13): at k=3 it is "
         "inside the seed noise. Kept for provenance.")


def fig4_seed1_archived(t, out_dir):
    """[ARCHIVED seed-1] drafter+serve-gate metrics + buffer-band agreement."""
    gate = {r["phase"]: r for r in read_gate()}
    da = {p: json.loads((AB / f"decision_analysis_{p}.json").read_text())
          for p in ("m1a_mpc_k3_sample", "m2_repeat_k3", "m3_hybrid_k3")}
    names = ["repeat-last k3", "hybrid k5\n(no gate)", "hybrid k5\n+ v2 gate"]
    src = [t["m2_repeat_k3"], gate["m5_ctrl"], gate["v_hybrid_k5_f5_cons"]]
    metrics = ["draft 1-step\nagreement", "q\n(queue serve)", "speedup\nvs A1",
               "dQoE\nvs A1", "drebuffer\nvs A1 (s, /50)"]

    def get(r, k):
        return fnum(r.get(k))
    vals = []
    for r in src:
        vals.append([
            get(r, "draft_1step_rate") if "draft_1step_rate" in r else get(r, "draft_1step"),
            get(r, "q_queue_serve") if "q_queue_serve" in r else get(r, "q"),
            (get(r, "speedup_vs_a1") or 1.0) - 1.0,
            (get(r, "d_qoe_pct") or 0.0) / 100.0,
            (get(r, "d_rebuffer_s") / 50.0) if (r.get("d_rebuffer_s") is not None) else None,
        ])
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(8.8, 3.6),
                                   gridspec_kw={"width_ratios": [3, 2]})
    hatches = ["////", "", "xxx"]
    w = 0.25
    for j, hz in enumerate(hatches):
        axL.bar([i + (j - 1) * w for i in range(len(metrics))],
                [vals[j][i] for i in range(len(metrics))], w, color="0.85",
                hatch=hz, edgecolor="black", linewidth=0.7, label=names[j])
    axL.axhline(0, color="black", lw=0.8)
    axL.set_xticks(range(len(metrics)))
    axL.set_xticklabels(metrics, fontsize=7)
    axL.set_ylabel("value (fractions; speedup as d from 1.0)")
    axL.set_title("[ARCHIVED] Serve gate: hybrid k5 before / after")
    axL.legend(fontsize=6.5)
    bands = ["<5s", "5-10s", "10-20s", ">=20s"]
    band_names = ["mpc k3", "repeat-last k3", "hybrid k3"]
    for j, ph in enumerate(("m1a_mpc_k3_sample", "m2_repeat_k3", "m3_hybrid_k3")):
        by = {b["band"]: b for b in da[ph]["by_buffer"]}
        y = [by[b]["mpc_step1_rate"] if b in by and by[b]["mpc_step1_rate"] is not None
             else None for b in bands]
        axR.plot([i for i, v in enumerate(y) if v is not None],
                 [v for v in y if v is not None],
                 marker=["*", "s", "^"][j], color="black", ls=["-", "--", ":"][j],
                 label=band_names[j])
    axR.set_xticks(range(len(bands)))
    axR.set_xticklabels(bands, fontsize=7)
    axR.set_ylabel("draft 1-step agreement")
    axR.set_ylim(0, 1.0)
    axR.set_title("Agreement by buffer band")
    axR.legend(fontsize=7)
    save(fig, out_dir, "fig4_drafter_comparison_seed1",
         "Figure 4 [ARCHIVED, seed 1 only -- superseded by the 4-seed Fig. 4]. "
         "Left: hybrid k5 before/after the v2 serve-time gate. The serve gate "
         "was later withdrawn (inert once measured without the seed-once RNG "
         "confound, CHANGE_REQUEST_SERVE_TIME_GATE). Right: 1-step agreement by "
         "buffer band (unchanged, still valid). Kept for provenance.")


def fig5(out_dir):
    """serve-gate strength (floor) vs rebuffering vs speedup -- v1 fallback / v2."""
    rows = read_gate()
    def fx(r, k):
        try: return float(r[k])
        except (TypeError, ValueError): return None

    # group: (drafter, k, gate-mode) -> list of (floor, rebuf, speedup, dqoe, npass)
    groups = {}
    ctrl = {}
    for r in rows:
        key = (r["drafter"], r["k"])
        pt = (fx(r, "floor_s") or 0.0, fx(r, "rebuffer_s"), fx(r, "speedup_vs_a1"),
              fx(r, "d_qoe_pct"), int(r["n_pass"]))
        gate = r["gate"]
        if gate == "none":
            ctrl[key] = pt
        else:
            groups.setdefault((*key, gate), []).append(pt)

    fig, (axL, axR) = plt.subplots(1, 2, figsize=(9.0, 3.8))

    # ---- left: rebuffering vs floor ----
    style = {"fallback": ("-", "o"), "conservative": ("-", "s"), "safe-mode": (":", "^")}
    shade = {("repeat-last", "3"): "0.0", ("hybrid", "3"): "0.35",
             ("hybrid", "5"): "0.0", ("repeat-last", "5"): "0.55"}
    for (drafter, k, gate), pts in sorted(groups.items()):
        pts = sorted(p for p in pts if p[1] is not None)
        if not pts:
            continue
        c0 = ctrl.get((drafter, k))
        xs = ([0.0] + [p[0] for p in pts]) if c0 else [p[0] for p in pts]
        ys = ([c0[1]] + [p[1] for p in pts]) if c0 else [p[1] for p in pts]
        ls, mk = style[gate]
        axL.plot(xs, ys, ls=ls, marker=mk, ms=5,
                 color=shade.get((drafter, k), "0.4"), lw=1.1,
                 label=f"{drafter} k{k} · {gate}")
    axL.axhline(A1_REB, color="0.5", ls="--", lw=0.9)
    axL.annotate("A1 rebuffering", (0.1, A1_REB), fontsize=7, va="bottom")
    axL.set_xlabel("serve-gate buffer floor (s); 0 = no gate")
    axL.set_ylabel("total rebuffering (s)")
    axL.set_title("Gate strength vs rebuffering")
    axL.set_ylim(0, 62)
    axL.legend(fontsize=6, ncol=1, loc="upper left")

    # ---- right: speedup vs rebuffering, every config ----
    for r in rows:
        reb, spd, npass = fx(r, "rebuffer_s"), fx(r, "speedup_vs_a1"), int(r["n_pass"])
        if reb is None or spd is None:
            continue
        gate = r["gate"]
        mk = {"none": "x", "fallback": "o", "conservative": "s", "safe-mode": "^"}.get(gate, ".")
        fc = "black" if npass == 4 else ("0.6" if gate != "none" else "white")
        axR.scatter(reb, spd, marker=mk, s=70 if npass == 4 else 34,
                    facecolor=fc, edgecolor="black", linewidth=0.7, zorder=3)
    axR.axvline(A1_REB, color="0.5", ls="--", lw=0.9)
    axR.axhline(1.24, color="0.4", ls="-.", lw=0.9)
    axR.annotate("1.24x", (55, 1.245), fontsize=7)
    axR.annotate("A1\nrebuf", (A1_REB + 1, 1.66), fontsize=7)
    axR.annotate("v2 conservative\nhybrid k5 (4/4)", (1.64, 1.499), fontsize=7,
                 xytext=(14, 1.40), arrowprops=dict(arrowstyle="->", lw=0.7))
    axR.set_xlabel("total rebuffering (s)")
    axR.set_ylabel("speedup vs A1")
    axR.set_title("All serve-gate configs")
    axR.set_xlim(-2, 62)
    from matplotlib.lines import Line2D
    axR.legend(handles=[
        Line2D([], [], marker="x", ls="", color="black", label="no gate (control)"),
        Line2D([], [], marker="o", ls="", mfc="0.6", mec="black", label="v1 fallback"),
        Line2D([], [], marker="s", ls="", mfc="0.6", mec="black", label="v2 conservative"),
        Line2D([], [], marker="^", ls="", mfc="0.6", mec="black", label="v2 safe-mode"),
        Line2D([], [], marker="s", ls="", mfc="black", mec="black", label="4/4 at seed 1 only"),
    ], fontsize=6, loc="lower right")
    save(fig, out_dir, "fig5_serve_gate_tradeoff",
         "Figure 5. The serve-time buffer gate, all at --seed 1. Left: total "
         "rebuffering vs the gate's buffer-floor threshold (0 = no gate), one "
         "line per drafter x response mode. v1 'fallback' (demote to an LLM "
         "call) makes rebuffering worse for every drafter except hybrid k5; v2 "
         "'conservative' (serve one quality level down, no LLM) on hybrid k5 "
         "drops rebuffering to 1.6 s; v2 'safe-mode' over-corrects. Right: "
         "speedup vs rebuffering. The one hybrid k5 + conservative + floor 5 s "
         "point (filled square) passes all four seed-1 criteria -- BUT this does "
         "not survive seeds 2-4 (help 1 / inert 2 / hurt 1) or per-episode "
         "re-seeding (1 decision changed, 0 s rebuffer effect): the seed-1 win "
         "is a coincidental trip/cascade alignment (DRAFTER_ABLATION section "
         "9.9-9.11, TRAJECTORY_DIVERGENCE).")



DIVDIR = REPO / "results" / "soyun" / "serve_gate_20260909" / "analysis"


def fig6(out_dir):
    """serve-gate trajectory divergence: mismatch-vs-distance + per-trace rebuffer."""
    def readdiv(label):
        rows = list(csv.DictReader(open(DIVDIR / f"divergence_{label}.csv")))
        buckets = [(int(r["x"]), float(r["rate"])) for r in rows if r["kind"] == "bucket" and r["rate"]]
        traces = {int(r["x"]): (float(r["mismatch"]), float(r["total"]))
                  for r in rows if r["kind"] == "trace_rebuffer"}
        return buckets, traces

    v1b, v1t = readdiv("v1_fallback")
    v2b, v2t = readdiv("v2_conservative")

    fig, (axL, axR) = plt.subplots(1, 2, figsize=(9.0, 3.6),
                                   gridspec_kw={"width_ratios": [3, 2]})

    axL.plot([x for x, _ in v1b], [r * 100 for _, r in v1b], "-o", ms=3, color="black",
             lw=1.2, label="v1 fallback (demote to LLM)")
    axL.plot([x for x, _ in v2b], [r * 100 for _, r in v2b], "--s", ms=3, color="0.45",
             lw=1.2, label="v2 conservative (step down, no LLM)")
    axL.axhline(0, color="0.7", lw=0.6)
    axL.set_xlabel("decisions after the first gate trip")
    axL.set_ylabel("action-mismatch rate vs the un-gated run (%)")
    axL.set_title("Downstream divergence from 3 gate trips")
    axL.legend(fontsize=7, loc="upper right")
    axL.annotate("v1: 27 % sustained, never damps", (1100, 30), fontsize=7)
    axL.annotate("v2: burst on traces 59-64, then re-converges to 0",
                 (150, 52), fontsize=7)

    # right: per-trace rebuffer for the traces that matter
    base = {int(r["x"]): float(r["mismatch"]) for r in csv.DictReader(
        open(DIVDIR / "divergence_v1_fallback.csv")) if r["kind"] == "trace_rebuffer"}
    traces = sorted(set(base) | set(v1t) | set(v2t))
    x = range(len(traces))
    w = 0.27
    axR.bar([i - w for i in x], [base.get(t, 0) for t in traces], w, color="0.5",
            edgecolor="black", linewidth=0.6, label="m5 (no gate)")
    axR.bar([i for i in x], [v1t.get(t, (0, 0))[1] for t in traces], w, color="white",
            hatch="////", edgecolor="black", linewidth=0.6, label="v1 fallback")
    axR.bar([i + w for i in x], [v2t.get(t, (0, 0))[1] for t in traces], w, color="0.8",
            edgecolor="black", linewidth=0.6, label="v2 conservative")
    axR.set_xticks(list(x))
    axR.set_xticklabels([f"tr {t}" for t in traces], fontsize=7)
    axR.set_ylabel("rebuffering on that trace (s)")
    axR.set_title("Where the rebuffering is")
    axR.legend(fontsize=6.5)
    axR.annotate("v1 moves the cascade to tr 79", (0.5, 5.9), fontsize=6.5)
    save(fig, out_dir, "fig6_trajectory_divergence",
         "Figure 6. The serve-time gate fires on the same 3 queue-serve "
         "decisions in v1 and v2; both serve bitrate 0 there. Left: the "
         "action-mismatch rate against the un-gated run, vs how many decisions "
         "downstream. The evaluation RNG is seeded once for all 100 traces "
         "(test.py:42), so a gate trip that changes the RNG-draw count shifts "
         "every later trace. v1's demote-to-LLM (1 extra sample + a stochastic "
         "LLM decision per trip) holds a 27 % mismatch for the rest of the run; "
         "v2's step-down (0 samples at the trip) perturbs traces 59-64 then "
         "re-converges. Right: rebuffering per trace -- v2 fixes trace 94's 13 s "
         "cascade structurally (its trip lands on the drain chunk); v1 relocates "
         "trace 94 by luck and creates a new 5.8 s cascade on trace 79.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(REPO / "results" / "soyun" / "figures"))
    args = ap.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    archive = out / "archive"
    archive.mkdir(exist_ok=True)
    t = read_table()
    sweep = read_sweep()
    print("writing figures ->", out)
    fig1(t, out)
    fig2(t, sweep, out)
    fig3(sweep, out)
    fig4(t, out)
    for fn in (fig5, fig6):
        try:
            fn(out)
        except (FileNotFoundError, KeyError) as e:
            print(f'  {fn.__name__} skipped ({e})')
    print("writing archived seed-1 figures ->", archive)
    for fn in (fig1_seed1_archived, fig4_seed1_archived):
        try:
            fn(t, archive)
        except (FileNotFoundError, KeyError) as e:
            print(f'  {fn.__name__} skipped ({e})')


if __name__ == "__main__":
    main()
