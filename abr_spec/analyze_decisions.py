#!/usr/bin/env python3
"""abr_spec/analyze_decisions.py -- post-hoc analysis of a decisions.jsonl trace.

soyun / speculative inference.  Pure CPU, no model, no re-run: everything here is
derived from the per-decision records written by ``abr_spec/decision_trace.py``.

Answers, per the task:
  1. MPC 1-step hit rate      mpc_draft_actions[0] == llm_target_action
  2. "repeat last action" drafter's hypothetical hit rate
                              last_action        == llm_target_action
  3. LLM action autocorrelation
                              llm_action(t)      == llm_action(t-1)
  4. (1)-(3) split by buffer band and by throughput-stability band.

Also: latency attribution (MPC brute-force CPU vs context growth vs the rest),
per-position draft agreement, and accepted-prefix-length distributions for the
real MPC drafter and for the hypothetical repeat-last drafter.

    python abr_spec/analyze_decisions.py <decisions.jsonl> --out-dir <dir> --label E
"""
import argparse
import json
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

BUFFER_BANDS = (("<5s", None, 5.0), ("5-10s", 5.0, 10.0),
                ("10-20s", 10.0, 20.0), (">=20s", 20.0, None))
CV_BANDS = (("stable cv<0.10", None, 0.10), ("moderate 0.10-0.30", 0.10, 0.30),
            ("volatile cv>=0.30", 0.30, None))


def band(value, bands):
    if value is None:
        return "unknown"
    for name, lo, hi in bands:
        if (lo is None or value >= lo) and (hi is None or value < hi):
            return name
    return "unknown"


def cv(values):
    """Coefficient of variation of the positive throughput observations."""
    vals = [v for v in values if v and v > 0]
    if len(vals) < 2:
        return None
    mean = sum(vals) / len(vals)
    if mean <= 0:
        return None
    return st.pstdev(vals) / mean


def pct(num, den):
    return None if not den else num / den


def load(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def enrich(rows):
    """Attach the LLM's own action, the bands, and the previous LLM action."""
    for r in rows:
        # The LLM decided this step iff the target model actually ran.  On a
        # draft_verify step that is llm_target_actions[0]; on a fallback/plain
        # step the executed action IS the plain-policy LLM action.  On a
        # queue_serve step no LLM call happened at all.
        if r.get("stage") == "draft_verify" and r.get("llm_target_action") is not None:
            r["llm_action"] = int(r["llm_target_action"])
        elif r.get("target_plm_called") and r.get("stage") in ("fallback", "plain"):
            r["llm_action"] = int(r["action"])
        else:
            r["llm_action"] = None
        r["cv"] = cv(r.get("throughput_recent") or [])
        r["buffer_band"] = band(r.get("buffer"), BUFFER_BANDS)
        r["cv_band"] = band(r["cv"], CV_BANDS)

    # previous-step LLM action, strictly adjacent within one trace
    prev_by_trace = {}
    for r in rows:
        key = r.get("trace_idx")
        prev = prev_by_trace.get(key)
        r["prev_llm_action_adjacent"] = (
            prev["llm_action"] if (prev is not None
                                   and prev.get("t") == r.get("t", 0) - 1)
            else None
        )
        prev_by_trace[key] = r
    # previous LLM action in the LLM's own call sequence (gaps allowed)
    last_llm = {}
    for r in rows:
        key = r.get("trace_idx")
        r["prev_llm_action_seq"] = last_llm.get(key)
        if r["llm_action"] is not None:
            last_llm[key] = r["llm_action"]
    return rows


def rates(rows):
    """The three agreement rates over one (sub)set of decisions."""
    verify = [r for r in rows if r.get("stage") == "draft_verify"
              and r.get("mpc_draft_actions") and r.get("llm_target_action") is not None]
    mpc_hit = sum(1 for r in verify if r["mpc_draft_actions"][0] == r["llm_target_action"])

    # hypothetical "repeat the last executed action" drafter, scored on exactly
    # the same decisions where the LLM produced a target action.
    llm_rows = [r for r in rows if r.get("llm_action") is not None]
    repeat_hit = sum(1 for r in llm_rows if r["last_action"] == r["llm_action"])

    adj = [r for r in llm_rows if r.get("prev_llm_action_adjacent") is not None]
    auto_adj = sum(1 for r in adj if r["llm_action"] == r["prev_llm_action_adjacent"])
    seq = [r for r in llm_rows if r.get("prev_llm_action_seq") is not None]
    auto_seq = sum(1 for r in seq if r["llm_action"] == r["prev_llm_action_seq"])

    # same-basis comparison: MPC vs repeat-last restricted to verify steps
    repeat_hit_v = sum(1 for r in verify if r["last_action"] == r["llm_target_action"])
    return {
        "n_decisions": len(rows),
        "n_verify": len(verify),
        "n_llm_actions": len(llm_rows),
        "mpc_step1_hits": mpc_hit,
        "mpc_step1_rate": pct(mpc_hit, len(verify)),
        "repeat_last_hits": repeat_hit,
        "repeat_last_rate": pct(repeat_hit, len(llm_rows)),
        "repeat_last_rate_on_verify": pct(repeat_hit_v, len(verify)),
        "llm_autocorr_adjacent_n": len(adj),
        "llm_autocorr_adjacent_rate": pct(auto_adj, len(adj)),
        "llm_autocorr_seq_n": len(seq),
        "llm_autocorr_seq_rate": pct(auto_seq, len(seq)),
    }


def per_position(rows):
    """Position-wise draft agreement and accepted-prefix distributions."""
    verify = [r for r in rows if r.get("stage") == "draft_verify"
              and r.get("mpc_draft_actions") and r.get("llm_target_actions")]
    k = max((len(r["mpc_draft_actions"]) for r in verify), default=0)
    pos = []
    for i in range(k):
        pairs = [(r["mpc_draft_actions"][i], r["llm_target_actions"][i])
                 for r in verify
                 if len(r["mpc_draft_actions"]) > i and len(r["llm_target_actions"]) > i]
        hits = sum(1 for d, t in pairs if d == t)
        # same position for the hypothetical repeat-last drafter: it proposes the
        # same action for every step of the horizon.
        rep = [(r["last_action"], r["llm_target_actions"][i]) for r in verify
               if len(r["llm_target_actions"]) > i]
        rep_hits = sum(1 for d, t in rep if d == t)
        pos.append({"position": i, "n": len(pairs),
                    "mpc_match_rate": pct(hits, len(pairs)),
                    "repeat_last_match_rate": pct(rep_hits, len(rep))})

    def prefix_len(draft, target):
        n = 0
        for d, t in zip(draft, target):
            if d != t:
                break
            n += 1
        return n

    mpc_prefix = Counter(prefix_len(r["mpc_draft_actions"], r["llm_target_actions"])
                         for r in verify)
    rep_prefix = Counter(prefix_len([r["last_action"]] * len(r["llm_target_actions"]),
                                    r["llm_target_actions"]) for r in verify)
    n = len(verify)
    return {
        "k": k, "n_verify": n,
        "positions": pos,
        "mpc_accepted_prefix_hist": {str(i): mpc_prefix.get(i, 0) for i in range(k + 1)},
        "mpc_accepted_prefix_mean": pct(sum(i * c for i, c in mpc_prefix.items()), n),
        "repeat_last_prefix_hist": {str(i): rep_prefix.get(i, 0) for i in range(k + 1)},
        "repeat_last_prefix_mean": pct(sum(i * c for i, c in rep_prefix.items()), n),
    }


def latency_attribution(rows):
    def agg(vals):
        vals = [v for v in vals if v is not None]
        if not vals:
            return None
        vals_sorted = sorted(vals)
        return {
            "n": len(vals),
            "mean": sum(vals) / len(vals),
            "p50": vals_sorted[len(vals_sorted) // 2],
            "p95": vals_sorted[min(len(vals_sorted) - 1,
                                   int(round(0.95 * (len(vals_sorted) - 1))))],
            "total": sum(vals),
        }

    out = {"by_stage": {}}
    for stage in sorted({r.get("stage") for r in rows}):
        sub = [r for r in rows if r.get("stage") == stage]
        out["by_stage"][stage] = {
            "count": len(sub),
            "share": pct(len(sub), len(rows)),
            "latency_ms": agg(r.get("latency_ms") for r in sub),
            "mpc_rollout_cpu_ms": agg(r.get("mpc_rollout_cpu_ms") for r in sub),
            "throughput_observe_cpu_ms": agg(r.get("throughput_observe_cpu_ms") for r in sub),
            "verify_logits_wall_ms": agg(r.get("verify_logits_wall_ms") for r in sub),
            "context_selected_tokens": agg(r.get("context_selected_tokens") for r in sub),
        }
    mpc = [r.get("mpc_rollout_cpu_ms") or 0.0 for r in rows]
    obs = [r.get("throughput_observe_cpu_ms") or 0.0 for r in rows]
    lat = [r.get("latency_ms") or 0.0 for r in rows]
    out["totals_ms"] = {
        "latency": sum(lat),
        "mpc_rollout_cpu": sum(mpc),
        "throughput_observe_cpu": sum(obs),
        "mpc_share_of_latency": pct(sum(mpc), sum(lat)),
        "mpc_plus_observe_share_of_latency": pct(sum(mpc) + sum(obs), sum(lat)),
    }
    return out


def bucketed(rows, key):
    order = [b[0] for b in (BUFFER_BANDS if key == "buffer_band" else CV_BANDS)] + ["unknown"]
    groups = defaultdict(list)
    for r in rows:
        groups[r[key]].append(r)
    return [{"band": b, **rates(groups[b])} for b in order if groups.get(b)]


def md_table(header, rows):
    out = ["| " + " | ".join(header) + " |",
           "|" + "|".join(["---"] * len(header)) + "|"]
    for r in rows:
        out.append("| " + " | ".join("" if c is None else str(c) for c in r) + " |")
    return "\n".join(out)


def f3(x, scale=1.0, suffix=""):
    return "n/a" if x is None else f"{x * scale:.3f}{suffix}"


def fpct(x):
    return "n/a" if x is None else f"{100 * x:.2f} %"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("jsonl")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--label", default="E")
    args = ap.parse_args()

    rows = enrich(load(args.jsonl))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "label": args.label,
        "source": args.jsonl,
        "overall": rates(rows),
        "per_position": per_position(rows),
        "latency": latency_attribution(rows),
        "by_buffer": bucketed(rows, "buffer_band"),
        "by_throughput_stability": bucketed(rows, "cv_band"),
        "stage_counts": dict(Counter(r.get("stage") for r in rows)),
        "fallback_reasons": dict(Counter(r.get("fallback_reason") for r in rows
                                         if r.get("fallback_reason"))),
        "rebuffer_events": sum(1 for r in rows if r.get("rebuffered")),
        "traces": len({r.get("trace_idx") for r in rows}),
    }
    (out_dir / f"decision_analysis_{args.label}.json").write_text(
        json.dumps(report, indent=2, sort_keys=True))

    # ---- CSV: the bucket table ----
    csv_lines = ["dimension,band,n_decisions,n_verify,n_llm_actions,"
                 "mpc_step1_rate,repeat_last_rate_on_verify,llm_autocorr_adjacent_rate"]
    for dim, key in (("buffer", "by_buffer"), ("throughput_cv", "by_throughput_stability")):
        for b in report[key]:
            csv_lines.append(",".join(str(x) for x in [
                dim, b["band"], b["n_decisions"], b["n_verify"], b["n_llm_actions"],
                "" if b["mpc_step1_rate"] is None else f"{b['mpc_step1_rate']:.6f}",
                "" if b["repeat_last_rate_on_verify"] is None else f"{b['repeat_last_rate_on_verify']:.6f}",
                "" if b["llm_autocorr_adjacent_rate"] is None else f"{b['llm_autocorr_adjacent_rate']:.6f}",
            ]))
    (out_dir / f"decision_buckets_{args.label}.csv").write_text("\n".join(csv_lines) + "\n")

    # ---- Markdown ----
    o = report["overall"]
    md = [f"### {args.label} — per-decision post-hoc analysis",
          "",
          f"`{args.jsonl}` — {o['n_decisions']} decisions over {report['traces']} traces; "
          f"{o['n_verify']} draft+verify steps, {o['n_llm_actions']} steps where the LLM "
          f"actually produced an action.",
          "",
          md_table(["지표", "정의", "값", "분모"], [
              ["1. MPC draft 1-step 일치율", "`mpc_draft_actions[0] == llm_target_action`",
               fpct(o["mpc_step1_rate"]), o["n_verify"]],
              ["2. 직전 행동 반복 drafter (가상)", "`last_action == llm_action`",
               fpct(o["repeat_last_rate"]), o["n_llm_actions"]],
              ["2b. 동일 기준(verify step만)", "`last_action == llm_target_action`",
               fpct(o["repeat_last_rate_on_verify"]), o["n_verify"]],
              ["3. LLM 행동 자기상관 (인접 t)", "`llm_action(t) == llm_action(t-1)`",
               fpct(o["llm_autocorr_adjacent_rate"]), o["llm_autocorr_adjacent_n"]],
              ["3b. LLM 호출 순서 기준", "직전 LLM 호출의 행동과 비교",
               fpct(o["llm_autocorr_seq_rate"]), o["llm_autocorr_seq_n"]],
          ]),
          ""]

    pp = report["per_position"]
    md += [f"**Draft 위치별 일치율 (k={pp['k']})**", "",
           md_table(["draft position", "n", "MPC 일치율", "repeat-last 일치율"],
                    [[p["position"], p["n"], fpct(p["mpc_match_rate"]),
                      fpct(p["repeat_last_match_rate"])] for p in pp["positions"]]),
           "",
           f"accepted-prefix 길이 평균 — MPC **{f3(pp['mpc_accepted_prefix_mean'])}** / "
           f"repeat-last **{f3(pp['repeat_last_prefix_mean'])}** (최대 {pp['k']}). "
           f"MPC prefix 분포 {pp['mpc_accepted_prefix_hist']}, "
           f"repeat-last {pp['repeat_last_prefix_hist']}.", ""]

    for title, key in (("buffer 구간별", "by_buffer"),
                       ("throughput 안정성(최근 6 관측 CV) 구간별", "by_throughput_stability")):
        md += [f"**{title}**", "",
               md_table(["구간", "decisions", "verify", "1. MPC 1-step",
                         "2b. repeat-last", "3. LLM 자기상관"],
                        [[b["band"], b["n_decisions"], b["n_verify"],
                          fpct(b["mpc_step1_rate"]),
                          fpct(b["repeat_last_rate_on_verify"]),
                          fpct(b["llm_autocorr_adjacent_rate"])]
                         for b in report[key]]),
               ""]

    lat = report["latency"]
    md += ["**Latency 귀속 (per-decision)**", "",
           md_table(["stage", "n", "비중", "latency mean ms", "MPC rollout CPU ms",
                     "verify logits ms", "selected tokens mean"],
                    [[s, v["count"], fpct(v["share"]),
                      f3((v["latency_ms"] or {}).get("mean")),
                      f3((v["mpc_rollout_cpu_ms"] or {}).get("mean")),
                      f3((v["verify_logits_wall_ms"] or {}).get("mean")),
                      f3((v["context_selected_tokens"] or {}).get("mean"))]
                     for s, v in sorted(lat["by_stage"].items())]),
           "",
           f"전체 decision latency 합 {lat['totals_ms']['latency']:.0f} ms 중 "
           f"MPC brute-force rollout CPU 시간은 {lat['totals_ms']['mpc_rollout_cpu']:.0f} ms "
           f"(**{fpct(lat['totals_ms']['mpc_share_of_latency'])}**), "
           f"throughput predictor까지 포함해도 "
           f"{fpct(lat['totals_ms']['mpc_plus_observe_share_of_latency'])}.", ""]

    (out_dir / f"decision_analysis_{args.label}.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
