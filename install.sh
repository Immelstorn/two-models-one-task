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

archive=${DUO_ARCHIVE:-https://github.com/Immelstorn/two-models-one-task/archive/refs/heads/main.tar.gz}
install_line="curl -fsSL https://raw.githubusercontent.com/Immelstorn/two-models-one-task/main/install.sh | bash"
home_dir=${DUO_HOME:-$HOME/.local/share/duo}
bin_dir=${DUO_BIN:-$HOME/.local/bin}
files="duo.py START_PROMPT.md skill bin install.sh LICENSE"
skill_links="$HOME/.claude/skills/duo $HOME/.agents/skills/duo"

# Colours only in a real terminal, and never when NO_COLOR is set.
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  bold=$'\033[1m' green=$'\033[32m' yellow=$'\033[33m' red=$'\033[31m' dim=$'\033[2m' reset=$'\033[0m'
else
  bold='' green='' yellow='' red='' dim='' reset=''
fi
title() { printf '%s%s%s\n' "$bold" "$*" "$reset"; }
done_step() { printf '  %s✓%s %s\n' "$green" "$reset" "$*"; }
warn() { printf '  %s!%s %s\n' "$yellow" "$reset" "$*" >&2; }
fail() { printf '%s✗ %s%s\n' "$red" "$*" "$reset" >&2; exit 1; }
short() { case $1 in "$HOME"/*) printf '~%s' "${1#"$HOME"}" ;; *) printf '%s' "$1" ;; esac; }
fingerprint() { if [ -d "$1" ]; then (cd "$1" && find . -type f | LC_ALL=C sort | xargs cksum | cksum); fi; }

if [ "${1:-}" = --uninstall ]; then
  title "🧹 Removing duo..."
  for link in $skill_links "$bin_dir/duo"; do
    if [ -L "$link" ]; then rm "$link"; fi
  done
  done_step "Skill removed from Claude Code and Codex"
  if [ -f "$home_dir/duo.py" ]; then rm -rf "$home_dir"; fi
  done_step "Removed $(short "$home_dir") and the duo command"
  echo
  title "👋 duo is gone. Come back any time:"
  printf '   %s%s%s\n' "$dim" "$install_line" "$reset"
  exit 0
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# Without --from: download the latest version, then let its own installer do the rest. That way the
# newest installer always runs, even when this copy came from a cache that is a few minutes old.
if [ "${1:-}" != --from ]; then
  mkdir "$work/source"
  curl -fsSL "$archive" | tar -xz --strip-components=1 -C "$work/source" \
    || fail "Download failed; check your connection. Nothing changed."
  [ -f "$work/source/install.sh" ] || fail "The download has no installer; nothing changed."
  bash "$work/source/install.sh" --from "$work/source" --downloaded
  exit
fi

before=$(fingerprint "$home_dir")
if [ -n "$before" ]; then title "🔄 Updating duo..."; else title "🤝 Installing duo..."; fi

source_dir=$(cd "${2:?--from needs a folder}" && pwd)
if [ "${3:-}" = --downloaded ]; then
  done_step "Downloaded the latest version"
else
  done_step "Using the copy in $(short "$source_dir")"
fi
for file in $files; do
  [ -e "$source_dir/$file" ] || fail "$(short "$source_dir") has no $file; nothing changed."
done

# Build the new copy beside the old one, then swap, so a failed run never leaves half an install.
mkdir -p "$(dirname "$home_dir")"
fresh=$(mktemp -d "$home_dir.new.XXXXXX")
(cd "$source_dir" && tar -cf - $files) | (cd "$fresh" && tar -xf -)
if [ -e "$home_dir" ]; then mv "$home_dir" "$work/previous"; fi
mv "$fresh" "$home_dir"
done_step "Installed in $(short "$home_dir")"

for link in $skill_links; do
  mkdir -p "$(dirname "$link")"
  if [ -e "$link" ] && [ ! -L "$link" ]; then
    warn "$(short "$link") is a real folder, not a link, so it was left alone"
    continue
  fi
  ln -sfn "$home_dir/skill" "$link"
done
done_step "Skill ready: /duo in Claude Code, \$duo in Codex"

mkdir -p "$bin_dir"
ln -sfn "$home_dir/bin/duo" "$bin_dir/duo"
case ":$PATH:" in
  *":$bin_dir:"*) done_step "duo command ready" ;;
  *) case $bin_dir in "$HOME"/*) shown='$HOME'${bin_dir#"$HOME"} ;; *) shown=$bin_dir ;; esac
     case ${SHELL:-} in */bash) profile='~/.bashrc' ;; *) profile='~/.zshrc' ;; esac
     warn "To use the duo command in a terminal, add $(short "$bin_dir") to your PATH:"
     printf '      %secho %s >> %s%s\n' "$dim" "'export PATH=\"$shown:\$PATH\"'" "$profile" "$reset" >&2 ;;
esac

echo
after=$(fingerprint "$home_dir")
if [ -z "$before" ]; then
  title "🎉 All set! Try /duo in Claude Code or \$duo in Codex."
elif [ "$before" = "$after" ]; then
  title "✨ Already up to date."
else
  title "✨ duo is updated. New sessions use the new version."
fi
