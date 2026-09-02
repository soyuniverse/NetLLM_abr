#!/usr/bin/env python3
"""abr_spec/nan_probe.py -- locate the decision where a PLM forward goes non-finite.

soyun / speculative inference.  Monkeypatch only; no upstream file is edited.

Condition C of the README matrix (``--token-selector recent-timestep
--selector-history-steps 5``) aborts mid-run with
``NonFiniteInferenceError`` at stage ``plm_hidden`` -- i.e. the FP16 inputs were
still finite and Llama itself produced an all-NaN hidden state.  This probe
wraps ``OfflineRLPolicy._run_plm`` and ``Environment.get_video_chunk`` to record,
for every decision, the trace index / timestep / context length / FP16 input
absmax, and dumps the tail of that ring buffer when the forward blows up.

    python abr_spec/run_wrapped.py ... --probe nan_probe -- <run_plm args>
"""
import atexit
import json
from collections import deque

_STATE = {"path": None, "ring": deque(maxlen=40), "calls": 0,
          "trace_idx": None, "chunk": 0, "absmax_max": 0.0, "failure": None}


def install(path):
    import torch
    import baseline_special.env as env_mod
    import plm_special.models.rl_policy as rlp

    _STATE["path"] = path
    Policy = rlp.OfflineRLPolicy
    orig_run_plm = Policy._run_plm
    orig_chunk = env_mod.Environment.get_video_chunk

    def _dump():
        try:
            with open(path, "w") as f:
                json.dump({"calls": _STATE["calls"],
                           "input_absmax_running_max": _STATE["absmax_max"],
                           "failure": _STATE["failure"],
                           "tail": list(_STATE["ring"])}, f, indent=2)
        except Exception:
            pass

    atexit.register(_dump)

    def _run_plm(self, inputs_embeds, attention_mask):
        _STATE["calls"] += 1
        fp16 = inputs_embeds.to(self._plm_compute_dtype())
        finite = torch.isfinite(fp16)
        absmax = float(fp16[finite].abs().max().item()) if bool(finite.any()) else None
        rec = {
            "call": _STATE["calls"],
            "trace_idx": _STATE["trace_idx"],
            "chunk": _STATE["chunk"],
            "context_tokens": int(inputs_embeds.shape[1]),
            "attn_mask_sum": (None if attention_mask is None
                              else int(attention_mask.sum().item())),
            "attn_mask_min_row": (None if attention_mask is None
                                  else int(attention_mask.sum(-1).min().item())),
            "fp32_absmax": float(inputs_embeds.detach().abs().max().item()),
            "fp16_input_absmax": absmax,
            "fp16_input_all_finite": bool(finite.all().item()),
        }
        if absmax is not None:
            _STATE["absmax_max"] = max(_STATE["absmax_max"], absmax)
        _STATE["ring"].append(rec)
        try:
            out = orig_run_plm(self, inputs_embeds, attention_mask)
        except rlp.NonFiniteInferenceError as exc:
            rec["FAILED_HERE"] = True
            _STATE["failure"] = {"details": exc.details, "record": rec}
            _dump()
            raise
        rec["hidden_absmax"] = float(out.detach().abs().max().item())
        return out

    def get_video_chunk(self, quality):
        _STATE["trace_idx"] = int(getattr(self, "trace_idx", -1))
        out = orig_chunk(self, quality)
        _STATE["chunk"] = 0 if out[6] else _STATE["chunk"] + 1
        return out

    Policy._run_plm = _run_plm
    env_mod.Environment.get_video_chunk = get_video_chunk
    print(f"[nan_probe] installed -> {path}")
