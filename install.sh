#!/bin/sh
# Install Dendro and connect it to Claude Code and Codex. Run it again to update.
set -eu

repo=https://github.com/aircoding-inp/dendro
app=${DENDRO_HOME:-$HOME/.dendro}/app

python=
for name in python3 python; do
    if command -v "$name" >/dev/null 2>&1 && "$name" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
        python=$name
        break
    fi
done
[ -n "$python" ] || { echo "Dendro needs Python 3.10 or newer." >&2; exit 1; }
command -v git >/dev/null 2>&1 || { echo "Dendro needs git." >&2; exit 1; }

if [ -d "$app/.git" ]; then
    git -C "$app" pull -q --ff-only
else
    git clone -q --depth 1 "$repo" "$app"
fi

"$python" "$app" connect
echo "Dendro is ready. Restart your agent. To read your projects: $python \"$app\" serve"
