#!/usr/bin/env bash
set -euo pipefail

DIFF_BASE="${1:-}"
if [ -n "${DIFF_BASE}" ]; then
  git diff --check "${DIFF_BASE}...HEAD"
else
  git diff --check
fi

if command -v ruby >/dev/null 2>&1; then
  ruby -e 'require "yaml"; ARGV.each { |f| YAML.load_file(f); puts "OK #{f}" }' .github/workflows/*.yml
else
  echo "ruby non disponibile: salto parse YAML workflow." >&2
fi

bash -n scripts/*.sh

python3 - <<'PY'
import ast
from pathlib import Path

for path in sorted(Path("scripts").glob("*.py")):
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    print(f"OK {path}")
PY
