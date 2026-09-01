#!/usr/bin/env python3
"""abr_spec/validate_ckpt.py — CPU-only structural check of a NetLLM ABR checkpoint.

Compares a checkpoint dir (adapter_config.json + adapter_model.{bin,safetensors} +
modules_except_plm.bin) against what THIS fork's `OfflineRLPolicy` expects
(rl_policy.py:168 ModuleList; spec transcribed in docs/soyun/CHECKPOINT_RECOVERY.md §3b).

No GPU, no model construction — just torch.load(map_location="cpu") + shape maths.

Usage:
    python abr_spec/validate_ckpt.py <ckpt_dir> [<ckpt_dir> ...]
Exit code 0 iff every dir is ABR-compatible.
"""
import json
import sys
from pathlib import Path

import torch

E = 4096          # llama-2-7b hidden / plm_embed_size
SFD = 256         # --state-feature-dim
CONV = 4          # EncoderNetwork conv_size (default)
ES3_IN = SFD * (6 - CONV + 1)   # 768
MAX_EP_LEN_PLUS_1 = 48          # Embedding(max_ep_len+1) ; max_timestep 46 -> 47 -> +1
BITRATE_LEVELS = 6

# --- reference: exact state_dict of this fork's modules_except_plm (12 modules) ---
MODULE_NAMES = [
    "state_encoder", "embed_timestep", "embed_return", "embed_action", "embed_ln",
    "embed_state1", "embed_state2", "embed_state3", "embed_state4", "embed_state5",
    "embed_state6", "action_head",
]
REF = {
    "0.fc1.0.weight": (SFD, 1), "0.fc1.0.bias": (SFD,),
    "0.fc2.0.weight": (SFD, 1), "0.fc2.0.bias": (SFD,),
    "0.conv3.0.weight": (SFD, 1, CONV), "0.conv3.0.bias": (SFD,),
    "0.conv4.0.weight": (SFD, 1, CONV), "0.conv4.0.bias": (SFD,),
    "0.conv5.0.weight": (SFD, 1, BITRATE_LEVELS), "0.conv5.0.bias": (SFD,),
    "0.fc6.0.weight": (SFD, 1), "0.fc6.0.bias": (SFD,),
    "1.weight": (MAX_EP_LEN_PLUS_1, E),
    "2.weight": (E, 1), "2.bias": (E,),
    "3.weight": (E, 1), "3.bias": (E,),
    "4.weight": (E,), "4.bias": (E,),
    "5.weight": (E, SFD), "5.bias": (E,),
    "6.weight": (E, SFD), "6.bias": (E,),
    "7.weight": (E, ES3_IN), "7.bias": (E,),
    "8.weight": (E, ES3_IN), "8.bias": (E,),
    "9.weight": (E, SFD), "9.bias": (E,),
    "10.weight": (E, SFD), "10.bias": (E,),
    "11.weight": (BITRATE_LEVELS, E), "11.bias": (BITRATE_LEVELS,),
}
REF_RANK = 128


def _load_state_dict(path):
    if path.suffix == ".safetensors":
        from safetensors.torch import load_file
        return load_file(str(path))
    return torch.load(str(path), map_location="cpu")


def _finite_scan(sd):
    bad = {}
    total = 0
    for k, v in sd.items():
        if not torch.is_tensor(v) or not v.is_floating_point():
            continue
        total += v.numel()
        nnan = int(torch.isnan(v).sum())
        ninf = int(torch.isinf(v).sum())
        if nnan or ninf:
            bad[k] = (nnan, ninf)
    return total, bad


def inspect(ckpt_dir):
    d = Path(ckpt_dir)
    out = {"dir": str(d), "problems": []}

    # ---- adapter_config.json ----
    cfg_p = d / "adapter_config.json"
    cfg = json.loads(cfg_p.read_text()) if cfg_p.is_file() else {}
    out["adapter"] = {
        "peft_type": cfg.get("peft_type"),
        "r": cfg.get("r"),
        "lora_alpha": cfg.get("lora_alpha"),
        "target_modules": cfg.get("target_modules"),
        "task_type": cfg.get("task_type"),
    }

    # ---- adapter_model weights ----
    adp = None
    for name in ("adapter_model.safetensors", "adapter_model.bin"):
        if (d / name).is_file():
            adp = d / name
            break
    out["adapter_file"] = adp.name if adp else None
    if adp:
        asd = _load_state_dict(adp)
        out["adapter_keys"] = len(asd)
        a_shape = next((tuple(v.shape) for k, v in asd.items() if "lora_A" in k), None)
        out["adapter_lora_A_shape"] = a_shape
        out["adapter_rank_from_weights"] = a_shape[0] if a_shape else None
        tot, bad = _finite_scan(asd)
        out["adapter_nonfinite"] = bad
        del asd

    # ---- modules_except_plm.bin ----
    mp = d / "modules_except_plm.bin"
    if not mp.is_file():
        out["problems"].append("modules_except_plm.bin missing")
        return out
    msd = _load_state_dict(mp)
    got = {k: tuple(v.shape) for k, v in msd.items()}
    top = sorted({k.split(".")[0] for k in got},
                 key=lambda x: (int(x) if x.isdigit() else 1e9, x))
    out["modules_top_level"] = [
        f"{i}={MODULE_NAMES[int(i)]}" if i.isdigit() and int(i) < len(MODULE_NAMES) else i
        for i in top
    ]
    out["modules_top_count"] = len(top)
    out["modules_tensor_count"] = len(got)
    out["modules_all"] = got

    # output head (index 11 .weight  -> [out_features, E])
    head_w = got.get("11.weight") or got.get("action_head.0.weight") \
        or got.get("4.task_head.0.weight")
    out["head_key"] = ("11.weight" if "11.weight" in got
                       else next((k for k in got if "task_head" in k or "action_head" in k), None))
    out["head_out_features"] = head_w[0] if head_w else None

    # ---- diff vs REF ----
    rows = []
    missing = [k for k in REF if k not in got]
    unexpected = [k for k in got if k not in REF]
    for k, want in REF.items():
        have = got.get(k)
        rows.append((k, want, have, "PASS" if have == want else ("MISSING" if have is None else "FAIL")))
    out["diff_rows"] = rows
    out["missing"] = missing
    out["unexpected"] = unexpected
    # run_plm.load_model does model.modules_except_plm.load_state_dict(msd) with
    # strict=True (default): every key AND shape must match exactly.
    out["strict_load_state_dict"] = (
        "PASS" if (not missing and not unexpected
                   and all(r[3] == "PASS" for r in rows)) else "FAIL")
    # adapter: run_plm builds LoraConfig(r=--rank, target q/v); load_adapter loads
    # these 128 keys via set_peft_model_state_dict. Keys are the fork's bare
    # LlamaModel path (base_model.model.layers.N... , single 'model').
    ak = out.get("adapter_keys")
    out["adapter_load_expectation"] = (
        "PASS (128 keys, r matches --rank 128)"
        if ak == 128 and out["adapter"].get("r") == REF_RANK
        else f"CHECK (keys={ak}, r={out['adapter'].get('r')})")

    tot, bad = _finite_scan(msd)
    out["modules_total_floats"] = tot
    out["modules_nonfinite"] = bad
    del msd

    # ---- verdict ----
    struct_ok = (not missing and not unexpected
                 and all(r[3] == "PASS" for r in rows))
    rank_ok = (out["adapter"].get("r") == REF_RANK
               and out.get("adapter_rank_from_weights") in (REF_RANK, None))
    finite_ok = not out.get("adapter_nonfinite") and not out["modules_nonfinite"]
    head = out["head_out_features"]

    if struct_ok and rank_ok and finite_ok:
        out["verdict"] = "ABR 호환 확인 (ABR-COMPATIBLE)"
    elif head == 3:
        out["verdict"] = "VP 재확인 (VIEWPORT checkpoint — output head = 3)"
    elif head == BITRATE_LEVELS and struct_ok and not rank_ok:
        out["verdict"] = "ABR 구조지만 rank 불일치 (ABR shape, rank mismatch)"
    else:
        out["verdict"] = "제3의 구조 (UNKNOWN structure — see diff)"
    out["_ok"] = struct_ok and rank_ok and finite_ok
    return out


def _print(o):
    print("=" * 78)
    print("dir:", o["dir"])
    a = o.get("adapter", {})
    print(f"  adapter_config : peft_type={a.get('peft_type')} r={a.get('r')} "
          f"alpha={a.get('lora_alpha')} targets={a.get('target_modules')} "
          f"task_type={a.get('task_type')}")
    print(f"  adapter_file   : {o.get('adapter_file')}  keys={o.get('adapter_keys')} "
          f"lora_A={o.get('adapter_lora_A_shape')} rank_from_weights={o.get('adapter_rank_from_weights')}")
    if o.get("adapter_nonfinite"):
        print(f"  adapter NONFINITE: {o['adapter_nonfinite']}")
    print(f"  modules_except_plm : top-level modules = {o.get('modules_top_count')} "
          f"({','.join(o.get('modules_top_level', []))})  tensors = {o.get('modules_tensor_count')}")
    print(f"  output head    : key={o.get('head_key')}  out_features={o.get('head_out_features')} "
          f"(ABR expects {BITRATE_LEVELS})")
    if o.get("missing"):
        print(f"  MISSING keys   : {o['missing']}")
    if o.get("unexpected"):
        print(f"  UNEXPECTED keys: {o['unexpected']}")
    fails = [r for r in o.get("diff_rows", []) if r[3] != "PASS"]
    if fails:
        print("  shape diffs (key | expected | got | result):")
        for k, want, have, res in fails:
            print(f"    {k:24} {str(want):14} {str(have):14} {res}")
    else:
        print(f"  shape diffs    : none — all {len(o.get('diff_rows', []))} tensors match the spec card")
    nf = o.get("modules_nonfinite")
    print(f"  finite check   : {'OK (all tensors finite)' if not nf else 'NONFINITE ' + str(nf)}")
    print(f"  load_model sim  : modules_except_plm.load_state_dict(strict) -> {o.get('strict_load_state_dict')}"
          f"   |   plm.load_adapter -> {o.get('adapter_load_expectation')}")
    print(f"  VERDICT        : {o['verdict']}")


if __name__ == "__main__":
    dirs = sys.argv[1:]
    if not dirs:
        print(__doc__)
        sys.exit(2)
    results = [inspect(x) for x in dirs]
    for r in results:
        _print(r)
    if len(results) > 1:
        print("=" * 78)
        print("COMPARISON")
        print(f"  {'dir':<48} {'r':>5} {'top':>4} {'tensors':>8} {'head':>5}  verdict")
        for r in results:
            print(f"  {Path(r['dir']).name:<48} {str(r['adapter'].get('r')):>5} "
                  f"{str(r.get('modules_top_count')):>4} {str(r.get('modules_tensor_count')):>8} "
                  f"{str(r.get('head_out_features')):>5}  {r['verdict']}")
    sys.exit(0 if all(r["_ok"] for r in results) else 1)
