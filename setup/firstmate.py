#!/usr/bin/env python3
"""Optional Firstmate sources and pinned companion tools for the tmux backend."""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tarfile
from urllib.request import urlopen

from install import Installer, ROOT, initialize_submodule

REPOSITORIES = (
    'firstmate', 'treehouse', 'no-mistakes', 'gh-axi',
    'chrome-devtools-axi', 'tasks-axi', 'quota-axi',
)


def install_sources(installer):
    installer.link(ROOT / 'bin/firstmate', Path('bin/firstmate'))
    for name in REPOSITORIES:
        initialize_submodule('tools/' + name, installer.dry_run)
    runtime = installer.target / '.local/share/firstmate'
    source = ROOT / 'tools/firstmate'
    installer.check_destination(runtime)
    if os.path.lexists(runtime):
        if runtime.is_symlink() or not (runtime / '.git').is_dir():
            raise RuntimeError(f'Firstmate home exists but is not an independent Git checkout: {runtime}')
        print(f'UNCHANGED Firstmate home {runtime}; use its own update workflow')
    else:
        print(f'CLONE {source} -> {runtime}')
        if not installer.dry_run:
            runtime.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(['git', 'clone', '--no-hardlinks', str(source), str(runtime)], check=True)
            subprocess.run(['git', '-C', str(runtime), 'remote', 'set-url', 'origin',
                            'https://github.com/kunchenguid/firstmate.git'], check=True)
    for name in REPOSITORIES[1:]:
        path = ROOT / 'tools' / name
        if path.exists() and (path / '.git').exists():
            installer.link(path, Path('.local/share/firstmate-companions') / name)
        elif installer.dry_run:
            print(f'PLAN link companion source {name}')
    # Only Firstmate's public standalone skill is intended for global discovery.
    stow = source / 'skills/stow'
    if (stow / 'SKILL.md').is_file():
        installer.link(stow, Path('.claude/skills/stow'))
        installer.codex_skill(stow, 'stow')
    elif installer.dry_run:
        print('PLAN link the public standalone stow skill for Claude and Codex')


def install_tools(installer):
    manifest = json.loads((ROOT / 'setup/firstmate-tools.json').read_text())
    machine = platform.machine().lower()
    architecture = {'x86_64': 'amd64', 'amd64': 'amd64', 'arm64': 'arm64', 'aarch64': 'arm64'}.get(machine)
    system = platform.system().lower()
    if not architecture or system not in ('darwin', 'linux'):
        raise RuntimeError(f'Unsupported Firstmate tool platform: {system}/{machine}')
    for name, config in manifest['binaries'].items():
        asset = config['assets'][system + '-' + architecture]
        destination = installer.target / '.local/bin' / name
        installer.check_destination(destination)
        print(f'INSTALL {name} {config["version"]} -> {destination}')
        if installer.dry_run:
            continue
        with urlopen(asset['url'], timeout=60) as response:
            archive = response.read(100_000_001)
        if len(archive) > 100_000_000 or hashlib.sha256(archive).hexdigest() != asset['sha256']:
            raise RuntimeError(f'Release checksum/size verification failed for {name}')
        with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as tar:
            candidates = [member for member in tar.getmembers() if member.isfile() and Path(member.name).name == name]
            if len(candidates) != 1:
                raise RuntimeError(f'Expected exactly one {name} executable in the release')
            binary = tar.extractfile(candidates[0]).read()
        if destination.is_file() and not destination.is_symlink() and destination.read_bytes() == binary:
            print(f'UNCHANGED {destination}')
            continue
        installer.save_existing(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(binary)
        destination.chmod(0o755)
        subprocess.run([str(destination), '--version'], check=True)
    packages = [f'{name}@{version}' for name, version in manifest['npm'].items()]
    installer.check_destination(installer.target / '.local/lib/node_modules/package')
    command = ['npm', 'install', '--global', '--prefix', str(installer.target / '.local'),
               '--registry=https://registry.npmjs.org/', *packages]
    print('RUN ' + ' '.join(command))
    if not installer.dry_run:
        # Do not inherit the dotfiles checkout's project-local npm prefix settings.
        subprocess.run(command, cwd=installer.target / '.local', check=True)
    print('Tool installation does not enable global hooks or start agents.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=Path, default=Path.home())
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--tools', action='store_true', help='Also install the pinned release binaries and npm tools')
    args = parser.parse_args()
    installer = Installer(args.target, args.dry_run)
    install_sources(installer)
    if args.tools:
        install_tools(installer)


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
