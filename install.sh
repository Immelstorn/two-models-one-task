#!/usr/bin/env bash
# Copyright (c) 2026 Denys Volovenko. MIT License.
# https://github.com/Immelstorn/two-models-one-task
#
# Install or update duo: get the latest version and link the skill for Claude Code and Codex.
# Safe to run again at any time.
set -euo pipefail

repo=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

if [ -d "$repo/.git" ]; then
  git -C "$repo" pull --ff-only --quiet
  echo "duo: up to date at $(git -C "$repo" log -1 --format='%h %s')"
fi

# Running older install steps twice could leave a link to the skill inside the skill folder.
if [ -L "$repo/skill/skill" ]; then rm "$repo/skill/skill"; fi

for dir in "$HOME/.claude/skills" "$HOME/.agents/skills"; do
  mkdir -p "$dir"
  if [ -e "$dir/duo" ] && [ ! -L "$dir/duo" ]; then
    echo "duo: $dir/duo exists and is not a link; left alone" >&2
    continue
  fi
  ln -sfn "$repo/skill" "$dir/duo"
  echo "duo: skill linked at $dir/duo"
done

case ":$PATH:" in
  *":$repo/bin:"*) ;;
  *) echo "duo: for the terminal launcher, add this line to ~/.zshrc or ~/.bashrc:"
     echo "  export PATH=\"$repo/bin:\$PATH\"" ;;
esac
