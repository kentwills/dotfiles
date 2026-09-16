#!/usr/bin/env python3
"""Install selected dotfiles with backups, without making HOME a Git checkout."""

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
MANAGER = ROOT / '.claude/skill-sources/manager-plugins'


class Installer:
    def __init__(self, target, dry_run=False):
        self.target = Path(target).expanduser().absolute()
        self.dry_run = dry_run
        self.backup = None

    def check_destination(self, destination):
        destination = Path(destination)
        if destination == self.target or self.target not in destination.parents:
            raise RuntimeError(f'Install destination is outside the target home: {destination}')
        for parent in destination.parents:
            if parent == self.target:
                break
            if parent.is_symlink():
                raise RuntimeError(f'Refusing to write through directory symlink: {parent}')

    def save_existing(self, destination):
        self.check_destination(destination)
        if not os.path.lexists(destination):
            return
        if self.dry_run:
            print(f'BACKUP {destination}')
            return
        if self.backup is None:
            parent = self.target / '.local/state/dotfiles/backups'
            self.check_destination(parent / 'backup')
            parent.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-')
            self.backup = Path(tempfile.mkdtemp(prefix=stamp, dir=parent))
        saved = self.backup / destination.relative_to(self.target)
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(destination), str(saved))
        print(f'BACKUP {destination} -> {saved}')

    def link(self, source, relative):
        source = Path(source).absolute()
        destination = self.target / relative
        if not source.exists():
            raise RuntimeError(f'Missing install source: {source}')
        if destination.is_symlink() and destination.resolve() == source.resolve():
            print(f'UNCHANGED {destination}')
            return
        self.check_destination(destination)
        if destination == source or destination in source.parents:
            raise RuntimeError(f'Install target would replace its source checkout: {destination}')
        self.save_existing(destination)
        print(f'LINK {destination} -> {source}')
        if not self.dry_run:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.symlink_to(source, target_is_directory=source.is_dir())

    def codex_skill(self, source, name):
        # Keep sibling references resolvable and avoid duplicate discovery.
        legacy = self.target / '.codex/skills' / name
        self.check_destination(legacy)
        self.link(source, Path('.agents/skills') / name)
        self.save_existing(legacy)


def initialize_submodule(path, dry_run):
    if (ROOT / path / '.git').exists():
        return
    command = ['git', '-C', str(ROOT), 'submodule', 'update', '--init', '--', path]
    print('RUN ' + ' '.join(command))
    if not dry_run:
        subprocess.run(command, check=True)


def install_skills(installer, claude, codex):
    initialize_submodule('.claude/skill-sources/manager-plugins', installer.dry_run)
    if not MANAGER.exists() or not (MANAGER / 'skills').exists():
        if installer.dry_run:
            print('PLAN install manager skills after initializing the private submodule')
            return
        raise RuntimeError('The private manager skill submodule is not available.')
    skills = sorted((MANAGER / 'skills').glob('*/SKILL.md'))
    if claude:
        for skill in skills:
            installer.link(skill.parent, Path('.claude/skills') / skill.parent.name)
    if codex:
        from adapt_skills import generate

        generated = installer.target / '.local/share/dotfiles/codex-manager-skills'
        installer.check_destination(generated)
        if installer.dry_run:
            print(f'GENERATE Codex adapters -> {generated}')
            for skill in skills:
                name = skill.parent.name
                legacy = installer.target / '.codex/skills' / name
                destination = installer.target / '.agents/skills' / name
                installer.check_destination(destination)
                installer.check_destination(legacy)
                if os.path.lexists(destination):
                    print(f'BACKUP IF CHANGED {destination}')
                print(f'LINK {destination} -> {generated / name}')
                installer.save_existing(legacy)
            return
        # Generate a complete new version before replacing any installed skill.
        generated.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='codex-skills-', dir=generated.parent) as temporary:
            generate(MANAGER, Path(temporary))
            expected = {p.relative_to(temporary): p.read_bytes()
                        for p in Path(temporary).rglob('*') if p.is_file()}
            existing = {p.relative_to(generated): p.read_bytes()
                        for p in generated.rglob('*') if p.is_file()} if generated.is_dir() else None
            if expected != existing:
                installer.save_existing(generated)
                shutil.copytree(temporary, generated)
        for skill in sorted(generated.iterdir()):
            if (skill / 'SKILL.md').is_file():
                installer.codex_skill(skill, skill.name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=Path, default=Path.home(), help='Home directory to install into')
    parser.add_argument('--dry-run', action='store_true', help='Print the plan; do not write or access the network')
    parser.add_argument('--claude-skills', action='store_true', help='Include the private manager skills for Claude')
    parser.add_argument('--codex-skills', action='store_true', help='Include locally generated Codex manager skills')
    parser.add_argument('--skills-only', action='store_true', help='Leave shell/editor configuration alone')
    parser.add_argument('--firstmate', action='store_true', help='Initialize Firstmate and its companion sources')
    args = parser.parse_args()
    if args.skills_only and not (args.claude_skills or args.codex_skills):
        parser.error('--skills-only requires --claude-skills or --codex-skills')
    installer = Installer(args.target, args.dry_run)
    if not args.skills_only:
        targets = (ROOT / 'setup/files.txt').read_text().splitlines()
        for relative in targets:
            if relative and not relative.startswith('#'):
                installer.link(ROOT / relative, Path(relative))
    if args.claude_skills or args.codex_skills:
        install_skills(installer, args.claude_skills, args.codex_skills)
    if args.firstmate:
        from firstmate import install_sources

        install_sources(installer)


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
