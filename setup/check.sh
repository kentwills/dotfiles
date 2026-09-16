#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
git diff --check
for file in .bashrc .profile .sh_env .sh_rc .sh_advanced_rc .sh_plugins.d/*.sh bin/git-main; do
  bash -n "$file"
done
sh -n bin/brew bin/firstmate
if command -v zsh >/dev/null 2>&1; then
  zsh -n .zshrc
  for file in .sh_env .sh_rc .sh_advanced_rc; do zsh -n "$file"; done
fi
git config --file .gitconfig --list >/dev/null
python3 -m unittest discover -s tests -v
