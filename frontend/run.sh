#!/usr/bin/env bash
# Local dev runner. Node comes from a project-local conda env (.conda-node)
# since Node isn't installed globally on this host.
set -euo pipefail
cd "$(dirname "$0")"

export PATH="$(pwd)/.conda-node/bin:$PATH"

if [ ! -d node_modules ]; then
  npm install
fi

exec npm run dev -- --host 0.0.0.0 --port 5173
