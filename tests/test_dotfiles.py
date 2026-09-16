import contextlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'setup'))
from adapt_skills import DESCRIPTIONS, generate
from install import Installer, install_skills


def run(*command, **kwargs):
    return subprocess.run(command, text=True, capture_output=True, check=True, timeout=30, **kwargs)


class TemporaryTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='dotfiles test ')
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)


class InstallerTests(TemporaryTest):
    def test_dry_run_has_no_filesystem_side_effects(self):
        target = self.directory / 'new home'
        run(sys.executable, str(ROOT / 'setup/install.py'), '--target', str(target), '--dry-run')
        self.assertFalse(target.exists())

    def test_conflicts_are_backed_up_and_reinstallation_is_idempotent(self):
        target = self.directory / 'home'
        (target / '.ssh').mkdir(parents=True)
        (target / '.ssh/config').write_text('original SSH settings')
        (target / '.ssh/known_hosts').write_text('keep known hosts')
        install = Installer(target)
        with contextlib.redirect_stdout(io.StringIO()):
            install.link(ROOT / '.ssh/config', Path('.ssh/config'))
            install.link(ROOT / '.ssh/config', Path('.ssh/config'))
        self.assertEqual((install.backup / '.ssh/config').read_text(), 'original SSH settings')
        self.assertEqual((target / '.ssh/known_hosts').read_text(), 'keep known hosts')
        self.assertTrue((target / '.ssh/config').is_symlink())
        self.assertEqual(len(list((target / '.local/state/dotfiles/backups').iterdir())), 1)

    def test_does_not_write_through_a_linked_parent(self):
        target = self.directory / 'home'
        outside = self.directory / 'outside'
        target.mkdir()
        outside.mkdir()
        (target / '.ssh').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(RuntimeError):
            Installer(target).link(ROOT / '.ssh/config', Path('.ssh/config'))
        self.assertFalse((outside / 'config').exists())

    def test_does_not_replace_the_source_checkout(self):
        with self.assertRaises(RuntimeError):
            Installer(ROOT, dry_run=True).link(ROOT / '.sh_lib', Path('.sh_lib'))


class ShellTests(TemporaryTest):
    def shell_environment(self):
        target = self.directory / 'home'
        run(sys.executable, str(ROOT / 'setup/install.py'), '--target', str(target))
        shared = self.directory / 'shared temp'
        shared.mkdir(mode=0o755)
        brew_prefix = self.directory / 'fake brew'
        (brew_prefix / 'bin').mkdir(parents=True)
        brew = brew_prefix / 'bin/brew'
        brew.write_text('#!/bin/sh\nprintf "%s\\n" "$HOMEBREW_PREFIX"\n')
        brew.chmod(0o755)
        env = {
            'PATH': '/usr/bin:/bin:/usr/sbin:/sbin',
            'HOME': str(target), 'USER': 'fixture', 'LOGNAME': 'fixture',
            'TERM': 'dumb', 'TMPDIR': str(shared),
            'HOMEBREW_PREFIX': str(brew_prefix),
            'SSH_AUTH_SOCK': '/forwarded/agent.sock',
        }
        return target, shared, env

    def test_bash_and_zsh_start_without_calibration_or_environment_damage(self):
        target, shared, env = self.shell_environment()
        original_mode = stat.S_IMODE(shared.stat().st_mode)
        for shell in ('bash', 'zsh'):
            executable = shutil.which(shell)
            if not executable:
                continue
            with self.subTest(shell=shell):
                command = '. "$HOME/.profile"; '
                if shell == 'zsh':
                    command += '. "$HOME/.zshrc"; '
                command += 'printf "\\nRESULT=%s|%s|%s|%s\\n" "$HOME" "$TERM" "$TMPDIR" "$SSH_AUTH_SOCK"'
                flags = ['--noprofile', '--norc'] if shell == 'bash' else ['-d', '-f']
                result = run(executable, *flags, '-ic', command, env=dict(env, SHELL=executable))
                expected = f'RESULT={target}|dumb|{shared}|/forwarded/agent.sock'
                self.assertIn(expected, result.stdout)
                self.assertNotRegex(result.stderr, r'command not found|no such file|No such file|bad substitution|parse error|unbound variable')
                self.assertNotIn('zkbd', result.stdout + result.stderr)
        self.assertEqual(stat.S_IMODE(shared.stat().st_mode), original_mode)

    def test_missing_tmpdir_gets_a_private_directory(self):
        target, shared, env = self.shell_environment()
        env['TMPDIR'] = str(self.directory / 'does not exist')
        result = run('/bin/sh', '-c', '. "$HOME/.sh_env"; printf "%s" "$TMPDIR"', env=env)
        created = Path(result.stdout)
        self.addCleanup(shutil.rmtree, created)
        self.assertTrue(created.name.startswith('kent-dotfiles.'))
        self.assertEqual(stat.S_IMODE(created.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(shared.stat().st_mode), 0o755)


class GitMainTests(TemporaryTest):
    def setUp(self):
        super().setUp()
        self.env = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
                        GIT_AUTHOR_NAME='Fixture', GIT_AUTHOR_EMAIL='fixture@example.invalid',
                        GIT_COMMITTER_NAME='Fixture', GIT_COMMITTER_EMAIL='fixture@example.invalid')
        commands = self.directory / 'bin'
        commands.mkdir()
        for name in ('git-main', 'git-upstream', 'git-remote-upstream'):
            (commands / name).symlink_to(ROOT / 'bin' / name)
        self.env['PATH'] = str(commands) + os.pathsep + os.environ['PATH']
        self.remote = self.directory / 'remote.git'
        self.seed = self.directory / 'seed'
        self.work = self.directory / 'work'
        run('git', 'init', '--bare', '--initial-branch=main', str(self.remote), env=self.env)
        run('git', 'clone', str(self.remote), str(self.seed), env=self.env)
        self.commit(self.seed, 'base')
        run('git', '-C', str(self.seed), 'push', 'origin', 'main', env=self.env)
        run('git', 'clone', str(self.remote), str(self.work), env=self.env)

    def commit(self, repo, name):
        (repo / name).write_text(name)
        run('git', '-C', str(repo), 'add', name, env=self.env)
        run('git', '-C', str(repo), 'commit', '-m', name, env=self.env)
        return run('git', '-C', str(repo), 'rev-parse', 'HEAD', env=self.env).stdout.strip()

    def test_preserves_unpushed_commits(self):
        expected = self.commit(self.work, 'local')
        run('git', 'main', cwd=self.work, env=self.env)
        self.assertEqual(run('git', 'rev-parse', 'HEAD', cwd=self.work, env=self.env).stdout.strip(), expected)

    def test_fast_forwards_a_branch_that_is_behind(self):
        expected = self.commit(self.seed, 'remote')
        run('git', 'push', 'origin', 'main', cwd=self.seed, env=self.env)
        run('git', 'main', cwd=self.work, env=self.env)
        self.assertEqual(run('git', 'rev-parse', 'HEAD', cwd=self.work, env=self.env).stdout.strip(), expected)

    def test_divergence_fails_without_dropping_local_history(self):
        expected = self.commit(self.work, 'local')
        self.commit(self.seed, 'remote')
        run('git', 'push', 'origin', 'main', cwd=self.seed, env=self.env)
        with self.assertRaises(subprocess.CalledProcessError):
            run('git', 'main', cwd=self.work, env=self.env)
        self.assertEqual(run('git', 'rev-parse', 'HEAD', cwd=self.work, env=self.env).stdout.strip(), expected)


class ConfigTests(TemporaryTest):
    def test_ssh_restores_known_host_verification(self):
        result = run('ssh', '-G', '-F', str(ROOT / '.ssh/config'), 'example.invalid')
        values = dict(line.split(' ', 1) for line in result.stdout.splitlines())
        self.assertEqual(values['stricthostkeychecking'], 'ask')
        self.assertNotEqual(values.get('userknownhostsfile'), '/dev/null')
        self.assertNotEqual(values.get('hostkeyalias'), 'garbage')

    def test_difftool_handles_spaces_and_clears_git_context(self):
        binary = self.directory / 'vim'
        captured = self.directory / 'captured.json'
        binary.write_text(f'#!{sys.executable}\nimport json, os, sys\n'
                          'from pathlib import Path\n'
                          'Path(os.environ["CAPTURE"]).write_text(json.dumps([sys.argv[1:], '
                          '[os.environ.get(k) for k in ("GIT_DIR", "GIT_WORK_TREE", "GIT_EXTERNAL_DIFF")]]))\n')
        binary.chmod(0o755)
        command = run('git', 'config', '--file', str(ROOT / '.gitconfig'), 'difftool.vimdiff.cmd').stdout.strip()
        env = dict(os.environ, PATH=str(self.directory) + os.pathsep + os.environ['PATH'],
                   CAPTURE=str(captured), LOCAL='old file.txt', REMOTE='new file.txt',
                   GIT_DIR='wrong', GIT_WORK_TREE='wrong', GIT_EXTERNAL_DIFF='wrong')
        run('/bin/sh', '-c', command, env=env)
        arguments, context = json.loads(captured.read_text())
        self.assertEqual(arguments[-2:], ['old file.txt', 'new file.txt'])
        self.assertEqual(context, [None, None, None])

    @unittest.skipUnless(shutil.which('tmux'), 'tmux not installed')
    def test_tmux_keeps_vi_selection_and_uses_a_tmux_terminal(self):
        command = ['tmux', '-S', str(self.directory / 'socket')]
        try:
            run(*command, '-f', '/dev/null', 'new-session', '-d', '-s', 'test', 'exec sleep 30')
            run(*command, 'source-file', str(ROOT / '.tmux.conf'))
            # tmux 3.7 sends single-key queries to its status line, not stdout.
            bindings = run(*command, 'list-keys', '-T', 'copy-mode-vi').stdout
            self.assertRegex(bindings, r'(?m)^bind-key\s+(?:-r\s+)?-T\s+copy-mode-vi\s+v\s+.*\bbegin-selection\b')
            terminal = run(*command, 'show-options', '-gqv', 'default-terminal').stdout.strip()
            self.assertIn(terminal, ('tmux-256color', 'screen-256color'))
        finally:
            subprocess.run(command + ['kill-server'], capture_output=True)


class SkillTests(TemporaryTest):
    def manager_source(self):
        source = self.directory / 'source'
        for name in DESCRIPTIONS:
            directory = source / 'skills' / name
            directory.mkdir(parents=True)
            (directory / 'SKILL.md').write_text(f'---\nname: {name}\ndescription: fixture\n---\n'
                '# Fixture\n\n## Level Scope Guidelines\nUnique fixture criterion.\n'
                '## Review Process\nProposal fixture criterion.\n'
                '## Heuristics & Edge Cases\nFixture heuristic.\n')
        return source

    def test_generated_skills_preserve_private_criteria_and_have_resolvable_references(self):
        source = self.manager_source()
        output = self.directory / 'output'
        with contextlib.redirect_stdout(io.StringIO()):
            generate(source, output)
        self.assertEqual(len(list(output.glob('*/SKILL.md'))), 6)
        for skill in output.glob('*/SKILL.md'):
            text = skill.read_text()
            self.assertIn('name: ' + skill.parent.name, text)
            for relative in re.findall(r'\]\(([^)]+)\)', text):
                self.assertTrue((skill.parent / relative).exists(), relative)
        self.assertIn('Unique fixture criterion.', (output / 'em-promotion-reviewer/references/guide.md').read_text())
        self.assertIn('does not include it', (output / 'promo-eval/references/eval-rubric.md').read_text())

    def test_codex_install_migrates_legacy_skills_and_preserves_sibling_references(self):
        source = self.manager_source()
        target = self.directory / 'home'
        legacy = target / '.codex/skills/writing-style'
        legacy.mkdir(parents=True)
        (legacy / 'SKILL.md').write_text('previous writing skill')
        unrelated = target / '.codex/skills/unrelated'
        unrelated.mkdir()
        (unrelated / 'SKILL.md').write_text('keep this skill')
        installer = Installer(target)
        with patch('install.MANAGER', source), patch('install.initialize_submodule'), \
                contextlib.redirect_stdout(io.StringIO()):
            install_skills(installer, claude=False, codex=True)
            second = Installer(target)
            install_skills(second, claude=False, codex=True)
        self.assertIsNone(second.backup)
        self.assertFalse(os.path.lexists(legacy))
        self.assertEqual((installer.backup / '.codex/skills/writing-style/SKILL.md').read_text(),
                         'previous writing skill')
        self.assertEqual((unrelated / 'SKILL.md').read_text(), 'keep this skill')
        for name in DESCRIPTIONS:
            skill = target / '.agents/skills' / name / 'SKILL.md'
            for relative in re.findall(r'\]\(([^)]+)\)', skill.read_text()):
                self.assertTrue((skill.parent / relative).exists(), relative)

    def test_skill_generation_does_not_write_through_a_linked_parent(self):
        source = self.manager_source()
        target = self.directory / 'home'
        outside = self.directory / 'outside'
        target.mkdir()
        outside.mkdir()
        (target / '.local').symlink_to(outside, target_is_directory=True)
        with patch('install.MANAGER', source), patch('install.initialize_submodule'), \
                self.assertRaises(RuntimeError):
            install_skills(Installer(target), claude=False, codex=True)
        self.assertEqual(list(outside.iterdir()), [])

    def test_firstmate_wrapper_preserves_arguments_and_uses_its_own_home(self):
        runtime = self.directory / 'firstmate home'
        runtime.mkdir()
        (runtime / 'AGENTS.md').write_text('fixture')
        harness = self.directory / 'codex'
        captured = self.directory / 'launch.json'
        harness.write_text(f'#!{sys.executable}\nimport json, os, sys\nfrom pathlib import Path\n'
                           'Path(os.environ["CAPTURE"]).write_text(json.dumps([os.getcwd(), sys.argv[1:], os.environ["FM_BACKEND"]]))\n')
        harness.chmod(0o755)
        env = dict(os.environ, PATH=str(self.directory) + os.pathsep + os.environ['PATH'],
                   FM_HOME=str(runtime), FM_BACKEND='tmux', CAPTURE=str(captured))
        run(str(ROOT / 'bin/firstmate'), 'codex', '--model', 'model with spaces', env=env)
        self.assertEqual(json.loads(captured.read_text()), [str(runtime.resolve()), ['--model', 'model with spaces'], 'tmux'])
