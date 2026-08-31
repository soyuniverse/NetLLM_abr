"""GPU fp16 sanity probe — run in .venv. Records why the plumbing smoke is blocked.

Result on this instance (RTX 3090, driver 535.154.05, torch 2.2.0+cu12.1, 2026-08-31):
  fp32 cpu->cuda roundtrip : OK
  fp16 cpu->cuda (large 2D): NaN   <-- corrupts
  bf16 cpu->cuda (large 2D): NaN
  fp16 matmul on cuda      : NaN
  fp32->fp16 cast ON cuda  : NaN   (reproducible)
  fp16 cpu->cuda (small 1D): OK    (size/shape dependent -> intermittent HW-style corruption)
  Llama-2-7b .to('cuda') in fp16 -> input embedding weights become all-NaN (reproduced x2)

fp32 works; Llama-2-7b fp32 weights (~26 GB) do not fit in 24 GB VRAM.
=> not fixable in wrapper/app code. Infra blocker (bad fp16 datapath / GPU or CUDA runtime).
"""
import torch

def finite(t):
    return bool(torch.isfinite(t.float()).all())

print("torch", torch.__version__, "cuda", torch.version.cuda,
      "gpu", torch.cuda.get_device_name(0), "cap", torch.cuda.get_device_capability(0))

for dt in (torch.float32, torch.float16, torch.bfloat16):
    x = torch.randn(4096, 4096, dtype=dt)
    g = x.cuda()
    print(f"{str(dt):18} cpu->cuda finite={finite(g)} "
          f"roundtrip_match={torch.allclose(x.float(), g.cpu().float(), atol=1e-2)}")

a = torch.randn(2048, 2048, dtype=torch.float16, device="cuda")
print("fp16 matmul on cuda finite:", finite(a @ a))
print("fp32->fp16 cast on cuda finite:", finite(torch.randn(2048, 2048, device="cuda").half()))

from transformers import LlamaConfig
import sys
sys.path.insert(0, "adaptive_bitrate_streaming")
from plm_special.models.llama import LlamaModel
P = "downloaded_plms/llama/base"
m = LlamaModel.from_pretrained(P, config=LlamaConfig.from_pretrained(P), torch_dtype=torch.float16)
print("Llama embed on CPU  finite:", finite(m.get_input_embeddings().weight))
m = m.to("cuda:0")
print("Llama embed on CUDA finite:", finite(m.get_input_embeddings().weight))
