# AGENTS.md — soyun / Speculative inference

This is a shared research repository. Modules are split across the team.
I am **soyun**, owning **Speculative inference**. This file constrains any
agent working on my behalf on branch `soyun/spec-abr`.

## Write-allowed paths (ONLY these)

| Path | Permission |
|---|---|
| `abr_spec/` | read / write |
| `results/soyun/` | read / write (run outputs only) |
| `docs/soyun/` | read / write |
| `adaptive_bitrate_streaming/plm_special/speculative/` | **read only for now** — modify only when soyun explicitly says so, after the team lead's implementation is understood |
| `AGENTS.md`, `.gitignore` | read / write (safety scaffolding) |

**Everything else in the repo is READ ONLY.** This includes all other
teammates' code, in particular `adaptive_bitrate_streaming/plm_special/models/`
(the `selector` / `event_selection` / `selectors` / `rl_policy` family).

If a change outside the allowed paths looks necessary, **do not make it**.
Record it in [`docs/soyun/NEEDS_UPSTREAM.md`](docs/soyun/NEEDS_UPSTREAM.md)
with the file, the reason, and the proposed change, and stop.

## No experiment code at this stage

Only build safety scaffolding and documentation. Do not add experiment
runners, sweeps, or model-execution scripts unless soyun explicitly asks.

## Experiment run commands are fixed

Evaluation commands follow the README "6 evaluation conditions" table and its
`$COMMON` arguments (README.md, "모듈 설정" section). Run commands from
`adaptive_bitrate_streaming/`.

```bash
COMMON="--fp16 --seed 1 --plm-type llama --plm-size base --rank 128 \
--plm-dir ../downloaded_plms/llama/base \
--model-dir data/ft_plms/try_llama2_7b \
--trace fcc-test --trace-num 100 --video video1 --fixed-order \
--device cuda:0 --device-out cuda:0"
```

| Condition | Extra args |
|---|---|
| Original NetLLM | `--temporal-selector none --token-selector none --speculative-draft-steps 0` |
| Temporal only | `--temporal-selector event-aware --token-selector none --speculative-draft-steps 0` |
| Recent-token only | `--temporal-selector none --token-selector recent-timestep --selector-history-steps 5 --speculative-draft-steps 0` |
| Temporal + Token | `--temporal-selector event-aware --token-selector intra-timestep --speculative-draft-steps 0` |
| Speculative only | `--temporal-selector none --token-selector none --speculative-draft-steps 3` |
| All three | `--temporal-selector event-aware --token-selector intra-timestep --speculative-draft-steps 3` |

**Do not change** `--trace fcc-test --trace-num 100 --video video1 --fixed-order`.
These pin the evaluation set and ordering; altering them invalidates
cross-condition comparison. Speculative parameters that may be swept:
`--speculative-draft-steps`, `--speculative-verification-mode`,
`--speculative-buffer-tolerance`, `--speculative-state-tolerance`,
`--speculative-return-tolerance`.

## Result output layout

All generated output goes to `results/soyun/<run_id>/` and nowhere else.
Large binaries are git-ignored there; `*.json`, `*.csv`, `*.md` are tracked
so a run stays reviewable. Never write results into
`adaptive_bitrate_streaming/artifacts/` or any shared location.

## Enforcement

`.git/hooks/pre-commit` blocks any commit that stages a file outside the
write-allowed paths (plus `AGENTS.md` / `.gitignore`).

`.git/hooks/` is **not** tracked by git, so **immediately after every fresh
clone run:**

```bash
bash abr_spec/hooks/install.sh
```

The tracked source of truth is [`abr_spec/hooks/pre-commit`](abr_spec/hooks/pre-commit);
`install.sh` copies it into `.git/hooks/`, `chmod +x`, and prints a verification.

## Onboarding a new server

New instance / resumed work: see [`docs/soyun/HANDOFF.md`](docs/soyun/HANDOFF.md)
for the resume point and [`docs/soyun/ASSETS.md`](docs/soyun/ASSETS.md) for what
to re-download (base weights, venv) vs. what arrives with the clone (exp_pool,
traces, video1).
