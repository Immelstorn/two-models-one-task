#!/usr/bin/env bash
# Copyright (c) 2026 Denys Volovenko. MIT License.
# https://github.com/Immelstorn/two-models-one-task
#
# Install or update duo straight from GitHub:
#   curl -fsSL https://raw.githubusercontent.com/Immelstorn/two-models-one-task/main/install.sh | bash
# It downloads the latest version into ~/.local/share/duo, links the duo skill for Claude Code and
# Codex, and puts the duo launcher in ~/.local/bin. Run it again to update.
#   install.sh --from DIR    install from a local copy instead of downloading
#   install.sh --uninstall   remove what this script installed
set -euo pipefail

archive=https://github.com/Immelstorn/two-models-one-task/archive/refs/heads/main.tar.gz
home_dir=${DUO_HOME:-$HOME/.local/share/duo}
bin_dir=${DUO_BIN:-$HOME/.local/bin}
files="duo.py START_PROMPT.md skill bin install.sh LICENSE"
skill_links="$HOME/.claude/skills/duo $HOME/.agents/skills/duo"

if [ "${1:-}" = --uninstall ]; then
  for link in $skill_links "$bin_dir/duo"; do
    if [ -L "$link" ]; then rm "$link"; fi
  done
  if [ -f "$home_dir/duo.py" ]; then rm -rf "$home_dir"; fi
  echo "duo: removed"
  exit 0
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

if [ "${1:-}" = --from ]; then
  source_dir=$(cd "${2:?duo: --from needs a folder}" && pwd)
else
  echo "duo: downloading the latest version"
  source_dir=$work/source
  mkdir "$source_dir"
  curl -fsSL "$archive" | tar -xz --strip-components=1 -C "$source_dir"
fi
for file in $files; do
  if [ ! -e "$source_dir/$file" ]; then
    echo "duo: $source_dir has no $file; nothing changed" >&2
    exit 1
  fi
done

# Build the new copy beside the old one, then swap, so a failed run never leaves half an install.
mkdir -p "$(dirname "$home_dir")"
fresh=$(mktemp -d "$home_dir.new.XXXXXX")
(cd "$source_dir" && tar -cf - $files) | (cd "$fresh" && tar -xf -)
if [ -e "$home_dir" ]; then mv "$home_dir" "$work/previous"; fi
mv "$fresh" "$home_dir"
echo "duo: installed in $home_dir"

for link in $skill_links; do
  mkdir -p "$(dirname "$link")"
  if [ -e "$link" ] && [ ! -L "$link" ]; then
    echo "duo: $link exists and is not a link; left alone" >&2
    continue
  fi
  ln -sfn "$home_dir/skill" "$link"
  echo "duo: skill linked at $link"
done

mkdir -p "$bin_dir"
ln -sfn "$home_dir/bin/duo" "$bin_dir/duo"
case ":$PATH:" in
  *":$bin_dir:"*) echo "duo: done; try duo -h" ;;
  *) echo "duo: done. For the terminal launcher, add this line to ~/.zshrc or ~/.bashrc:"
     echo "  export PATH=\"$bin_dir:\$PATH\"" ;;
esac
