#!/usr/bin/env python3
"""Local release checks for LeadPilot AI. Does not push, commit, or touch real CRM data."""
from __future__ import annotations
import argparse
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]

FORBIDDEN_PARTS = {'node_modules', '__pycache__', '.venv', '.pytest_cache', '.git', 'recordings', 'leadpilot_audio', 'logs', '.vite', 'coverage', 'backups'}
FORBIDDEN_NAMES = {'credentials.json', 'token.json', 'auth_test.sqlite3', 'leadpilot_data.sqlite3', '.env', 'ngrok.yml', 'ngrok.yaml'}
FORBIDDEN_SUFFIXES = ('.sqlite', '.sqlite3', '.db', '.wav', '.mp3', '.webm', '.ogg', '.flac', '.pem', '.key', '.p12', '.pfx', '.bak', '.orig', '.rej', '.log', '.pyc')
SECRET_PATTERNS = {
    'private key': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'GitHub token': re.compile(rb'gh[pousr]_[A-Za-z0-9_]{20,}'),
    'Google API key': re.compile(rb'AIza[0-9A-Za-z_-]{30,}'),
    'OpenAI-style secret': re.compile(rb'(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{30,}'),
    'Slack token': re.compile(rb'xox[baprs]-[A-Za-z0-9-]{20,}'),
}
IGNORE_SAMPLES = ['.env', '.env.production', 'frontend/node_modules/sample.js', 'frontend/dist/main.js', 'leadpilot_data.sqlite3', 'token.json', 'credentials.json', 'recordings/customer.wav']


def cmd(args: list[str], *, env: dict[str, str] | None = None, cwd: pathlib.Path = ROOT, check: bool = True, capture: bool = False):
    print('>', ' '.join(args), flush=True)
    result = subprocess.run(args, cwd=cwd, env=env, text=False, capture_output=capture)
    if check and result.returncode:
        if capture:
            print((result.stderr or b'').decode('utf-8', errors='replace'))
        raise RuntimeError(f'Command failed with exit code {result.returncode}: {args[0]}')
    return result


def git(*args: str, check: bool = True) -> str:
    result = cmd(['git', *args], check=check, capture=True)
    return (result.stdout or b'').decode('utf-8', errors='replace').strip()


def unsafe_path(path: str) -> str | None:
    p = pathlib.PurePosixPath(path.replace('\\', '/'))
    parts = [s.lower() for s in p.parts]
    name = p.name.lower()
    if any(s in FORBIDDEN_PARTS for s in parts):
        return 'runtime/generated folder'
    if name in FORBIDDEN_NAMES or (name.startswith('.env.') and name != '.env.example'):
        return 'credential or local data filename'
    if name.startswith('client_secret') and name.endswith('.json'):
        return 'OAuth client secret'
    if 'service-account' in name and name.endswith('.json'):
        return 'service account key'
    if name.endswith(FORBIDDEN_SUFFIXES):
        return 'runtime binary, credential, or backup file'
    if name.startswith('leadpilot_data.sqlite3'):
        return 'CRM database'
    return None


def check_repository():
    if git('rev-parse', '--show-toplevel').lower().replace('\\', '/') != str(ROOT).lower().replace('\\', '/'):
        raise RuntimeError('Script must be located in the root of the LeadPilot Git checkout.')
    remote = git('remote', 'get-url', 'origin')
    if not re.search(r'github\.com[:/]Anujku007/LeadPilot-AI(?:\.git)?$', remote, re.I):
        raise RuntimeError(f'Unexpected origin remote: {remote}; refusing publication.')
    print('Repository:', ROOT)
    print('Origin:', remote)
    branch = git('branch', '--show-current')
    if branch != 'main':
        raise RuntimeError(f'Expected main branch, found {branch!r}.')
    bad_tracked = []
    for path in git('ls-files', '-z').split('\0'):
        if path and (problem := unsafe_path(path)):
            bad_tracked.append((path, problem))
    if bad_tracked:
        print('Blocked: sensitive paths are ALREADY tracked by Git:')
        for path, reason in bad_tracked[:40]: print(' -', path, '—', reason)
        raise RuntimeError('Remove sensitive files from Git tracking before publishing; deleting them from the working tree is not necessary.')
    failed = [p for p in IGNORE_SAMPLES if not subprocess.run(['git', 'check-ignore', '-q', '--no-index', p], cwd=ROOT).returncode == 0]
    if failed:
        raise RuntimeError('Missing ignore rules for: ' + ', '.join(failed))
    print('PASS: Git remote and file-ignore hygiene')


def staged_files() -> list[str]:
    raw = cmd(['git','diff','--cached','--name-only','--diff-filter=ACMR','-z'], capture=True).stdout or b''
    return [p.decode('utf-8', errors='replace') for p in raw.split(b'\0') if p]


def scan_staged():
    paths = staged_files()
    if not paths:
        print('No staged new/modified files found; nothing to scan.')
        return
    bad = []
    for path in paths:
        if problem := unsafe_path(path):
            bad.append(f'{path}: {problem}')
            continue
        blob = cmd(['git','show',f':{path}'], capture=True, check=False)
        if blob.returncode != 0: continue
        content = blob.stdout or b''
        if len(content) > 5 * 1024 * 1024:
            bad.append(f'{path}: file larger than 5 MiB; review before release')
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(content):
                bad.append(f'{path}: possible {label} in staged content')
        if pathlib.PurePosixPath(path).name.lower() == '.env.example':
            for line in content.decode('utf-8', errors='ignore').splitlines():
                if line.startswith('#') or not line.strip() or '=' not in line: continue
                key, value = line.split('=', 1)
                if ('KEY' in key or 'TOKEN' in key or 'SECRET' in key or 'PASSWORD' in key) and value.strip():
                    bad.append(f'{path}: {key} should be blank in the public example')
    if bad:
        print('BLOCKED staged changes:')
        for issue in bad: print(' -', issue)
        raise RuntimeError('Review staged files. Nothing was committed or pushed.')
    print('PASS: Staged safety scan,', len(paths), 'new/changed files checked')


def full_checks():
    python = sys.executable
    cmd([python, '-m', 'compileall', '-q', 'leadpilot_ai', 'leadpilot_api.py'])
    if not (ROOT/'frontend'/'package.json').exists():
        raise RuntimeError('frontend/package.json missing')
    # Run the test suite in a NEW process with an isolated DB. Never point tests at production CRM.
    with tempfile.TemporaryDirectory(prefix='leadpilot-release-check-') as t:
        dbfile = (pathlib.Path(t)/'test_leadpilot.sqlite3').as_posix()
        env = os.environ.copy()
        env['LEADPILOT_DATABASE_URL'] = 'sqlite:///' + dbfile
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        print('Test DB isolation:', dbfile, flush=True)
        cmd([python, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_leadpilot_*.py', '-q'], env=env)
    npm = shutil.which('npm.cmd') or shutil.which('npm')
    if not npm: raise RuntimeError('npm not found on PATH')
    cmd([npm, 'run', 'build'], cwd=ROOT/'frontend')
    print('\nPASS: Full local Python tests and React build (release candidate)')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--full', action='store_true', help='Run Python suite + React Vite build')
    ap.add_argument('--staged-scan', action='store_true', help='Check staged blobs for sensitive file names and likely secrets')
    args = ap.parse_args()
    try:
        check_repository()
        if args.staged_scan: scan_staged()
        if args.full: full_checks()
        if not args.full and not args.staged_scan: print('PASS: Release repository hygiene. Use --full before publication.')
        return 0
    except (RuntimeError, OSError) as exc:
        print('RELEASE CHECK FAILED:', exc)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
