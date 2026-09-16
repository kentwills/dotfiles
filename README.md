# Kent's Dotfiles

Bash/Zsh, Git, SSH, Vim/Neovim, and tmux configuration for macOS and Linux,
with optional Claude Code, Codex, and Firstmate setup. Based on
[bukzor/dotfiles](https://github.com/bukzor/dotfiles).

## Install the dotfiles

Start with Git and Python 3. Keep the checkout at a stable path because installed
files link back to it.

```sh
git clone git@github.com:kentwills/dotfiles.git ~/Documents/dotfiles
cd ~/Documents/dotfiles
python3 setup/install.py --dry-run
```

On macOS, install [Homebrew](https://brew.sh/) if needed, then the shared tools:

```sh
brew bundle --file=Brewfile
```

On Linux, install the corresponding tools with your package manager, or use
Homebrew. The shell also works without Homebrew. Additional applications and
language toolchains from the old configuration are optional:
`brew bundle --file=Brewfile.extras`.

Apply the reviewed plan:

```sh
python3 setup/install.py
```

The installer links only the paths in [setup/files.txt](setup/files.txt). It backs
up conflicting files or directories under
`~/.local/state/dotfiles/backups/<timestamp>/`, preserving their relative paths.
Running it again leaves correct links alone. It does not turn your home directory
into a Git checkout or replace your entire `.ssh` or `.claude` directory. A linked
parent directory is reported rather than followed for writes.

Use `--target /path/to/test-home` to preview or install somewhere else.
`--dry-run` does not clone repositories, download tools, or change install targets.

### Personal and work overrides

Keep machine-specific settings and credentials outside this public repository:

- `~/.ssh/config.local`: host-specific SSH settings, loaded before shared defaults.
- `~/private-dotfiles/.gitconfig`: Git identities and work-only aliases.
- `~/private-dotfiles/.sh_env`: environment overrides after shared defaults.
- `~/private-dotfiles/.sh_rc` and `.zshrc`: shell customizations.

Existing `TMPDIR`, `TERM`, and SSH-agent settings are preserved. The 1Password
agent is selected on macOS only when no agent is already configured and its socket
exists. Set `DOTFILES_SHOW_TODO=1` if you want `~/TODO.md` displayed at shell startup.

The retired upload, IRC, and old deployment helpers have been removed. Removing
them does not revoke credentials that appeared in earlier commits; revoke any
that are still valid through their owning service.

### Editor plugins

Vim and Neovim share the base configuration through `~/.config/vim/init.vim`.
Neovim's Lazy plugins live under `~/.local/share/nvim/lazy`, outside Vim's
automatically loaded packages. Use `:Lazy restore` to restore the checked-in
plugin versions.

Language tools are optional: select servers and formatters with `:Mason`, and
syntax parsers with `:TSInstall <language>`. Opening a file does not install
additional toolchains. To request the full configured Mason tool list, launch
Neovim with `DOTFILES_INSTALL_LANGUAGE_TOOLS=1 nvim`.

## Manager skills for Claude Code and Codex

The source is the private
[claude_manager_plugins](https://github.yelpcorp.com/rkwills/claude_manager_plugins)
repository. It is pinned as a Git submodule at
`.claude/skill-sources/manager-plugins`. This public repository stores its commit
pointer and skill links, not the internal skill text or rubrics. Yelp GitHub access
is needed only when installing or updating these skills.

| Skill | Purpose |
| --- | --- |
| `review-packet` | Route a packet or proposal to its specialist reviewer |
| `em-promotion-reviewer` | Review management-track promotion evidence |
| `ic-promotion-reviewer` | Review IC promotion evidence |
| `pep-reviewer` | Review Product Engineering Proposals |
| `promo-eval` | Evaluate review quality against a supplied scoring rubric |
| `writing-style` | Revise professional prose |

Install either set, or both, without changing your shell configuration:

```sh
python3 setup/install.py --skills-only --claude-skills --codex-skills --dry-run
python3 setup/install.py --skills-only --claude-skills --codex-skills
```

Claude receives links under `~/.claude/skills`. Codex receives native adapters
with focused instructions and locally generated domain references under
`~/.local/share/dotfiles/codex-manager-skills`. The installer links them into
`~/.agents/skills` and backs up same-named legacy `~/.codex/skills` installations
to avoid duplicate registrations and keep sibling-skill references together. Other skills and
global configuration are left alone. Open a new session to refresh discovery.

The adapters use Codex's available document/code connectors instead of hard-coded
Claude MCP tool names, proceed when the requested scope is clear, and produce local
review output unless an external write is explicitly requested. Supplied document
text works without connectors. The current source omits `evals/rubric.md`, so
`promo-eval` requests an authoritative scoring rubric before assigning numeric
scores; it does not manufacture one.

Examples: `/review-packet` in Claude Code, `$review-packet` in Codex. See the
[Codex skill documentation](https://developers.openai.com/codex/skills/) for discovery.

## Firstmate and companion repositories

[Firstmate](https://github.com/kunchenguid/firstmate) runs in its own home with its
own instructions and state. The default here is **Codex with tmux**; Claude Code
is also supported. This setup does not start agents or enable global hooks.

The optional `tools/` submodules pin Firstmate and the companions required by its
documented tmux toolchain:

| Repository | Role |
| --- | --- |
| [treehouse](https://github.com/kunchenguid/treehouse) | Isolated worktree management |
| [no-mistakes](https://github.com/kunchenguid/no-mistakes) | Validation pipeline |
| [gh-axi](https://github.com/kunchenguid/gh-axi) | GitHub operations |
| [chrome-devtools-axi](https://github.com/kunchenguid/chrome-devtools-axi) | Browser operations |
| [tasks-axi](https://github.com/kunchenguid/tasks-axi) | Backlog management |
| [quota-axi](https://github.com/kunchenguid/quota-axi) | Quota-aware dispatch |

Alternative backends such as Herdr, Orca, cmux, and Zellij, optional Lavish
presentation, and public Relay integrations are not enabled. Firstmate's own
[configuration guide](https://github.com/kunchenguid/firstmate/blob/main/docs/configuration.md)
documents those choices.

```sh
brew bundle --file=Brewfile.firstmate  # macOS platform prerequisites
python3 setup/firstmate.py --tools --dry-run
python3 setup/firstmate.py --tools
gh auth login                        # if not already authenticated
firstmate codex
# or: firstmate claude
```

Use the equivalent package-manager tools on Linux. Node must satisfy the pinned
npm tools' engine requirements (currently Node 22.19 or newer). The selected agent
harness must already be installed and authenticated.

The setup creates an independent checkout at `~/.local/share/firstmate`, links
companion sources under `~/.local/share/firstmate-companions`, and installs pinned
CLI releases into `~/.local/bin`. Binary archives are checked against recorded
SHA-256 hashes. The named public npm tools use `registry.npmjs.org` for this
installation only; your saved npm registry configuration is unchanged. Versions are recorded in
[setup/firstmate-tools.json](setup/firstmate-tools.json). Omit `--tools` to install
only the sources, launcher, and standalone skill. Existing Firstmate homes are
not reset or updated by reinstallation.

Ensure `~/bin` and `~/.local/bin` are on `PATH`. `firstmate codex` launches from the
Firstmate home without choosing a model or bypassing harness permissions. You can
override `FM_HOME` or `FM_BACKEND`, and pass additional harness arguments. For a
visible crew, run it inside tmux.

Only Firstmate's public standalone `stow` skill is linked globally for Claude and
Codex. Its `.agents/skills` are internal to a Firstmate home and are not exported
into ordinary projects. Firstmate runtime updates and dotfiles submodule updates
are separate; review source-pin changes explicitly when updating this repository.

## Checks

```sh
sh setup/check.sh
```

Checks cover shell syntax and fresh startup, SSH defaults, tmux selection,
portable difftool arguments, preservation of unpushed Git history, installer
backups, skill generation, and Firstmate launcher isolation. GitHub Actions runs
on macOS and Linux without fetching any private submodules.
