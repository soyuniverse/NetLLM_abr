#!/usr/bin/env bash
#
# Install soyun's pre-commit guardrail into .git/hooks/ (which git does not track).
# Run once after a fresh clone:  bash abr_spec/hooks/install.sh
#
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(git -C "$here" rev-parse --show-toplevel)"
src="$here/pre-commit"
dst="$repo_root/.git/hooks/pre-commit"

[ -f "$src" ] || { echo "missing source hook: $src" >&2; exit 1; }

mkdir -p "$repo_root/.git/hooks"
cp "$src" "$dst"
chmod +x "$dst"

if [ -x "$dst" ] && cmp -s "$src" "$dst"; then
	echo "installed : $dst"
	echo "verify    : OK (executable, byte-identical to abr_spec/hooks/pre-commit)"
else
	echo "verify    : FAILED" >&2
	exit 1
fi

echo "guards    : abr_spec/  results/soyun/  docs/soyun/"
echo "            adaptive_bitrate_streaming/plm_special/speculative/  (read-only for now)"
echo "            AGENTS.md  .gitignore"

# dry self-test: an upstream path must NOT match the allow-regex
regex='^(abr_spec/|results/soyun/|docs/soyun/|adaptive_bitrate_streaming/plm_special/speculative/|AGENTS\.md$|\.gitignore$)'
if printf 'adaptive_bitrate_streaming/run_plm.py\n' | grep -Eq "$regex"; then
	echo "self-test : FAILED (regex would allow run_plm.py)" >&2; exit 1
fi
echo "self-test : OK (run_plm.py would be rejected; abr_spec/ allowed)"
