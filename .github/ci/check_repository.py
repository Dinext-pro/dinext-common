"""Local repository checks. No credentials or network access are needed."""
import ast
import fnmatch
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib

root = Path(sys.argv[1]).resolve()
config = json.loads((root / '.github/dinext-ci.json').read_text())
assert config['mode'] in {'frappe-app', 'platform-smoke', 'python-project', 'portable', 'repository'}
event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text()) if os.environ.get('GITHUB_EVENT_PATH') else {}
if event.get('pull_request') and config.get('gitflow'):
    pr = event['pull_request']
    source, target = pr['head']['ref'], pr['base']['ref']
    denied = {'client-develop', 'client-release', 'dinord-develop', 'develope'}
    assert source not in denied and target not in denied, 'Legacy branch is frozen'
    patterns = ['release/*'] if target == 'main' else ['feature/*', 'feat/*', 'ISS-*', 'hotfix/*', 'bug/*', 'fix/*'] if target == 'develop' else ['develop'] if target.startswith('release/') else ['*']
    assert any(fnmatch.fnmatchcase(source, pattern) for pattern in patterns), f'Branch policy rejects {source} -> {target}'
if (root / 'pyproject.toml').is_file():
    tomllib.loads((root / 'pyproject.toml').read_text())
package = config.get('package_dir')
count = 0
if package and (root / package).is_dir():
    files = subprocess.check_output(['git', '-C', str(root), 'ls-files', '-z', '--', package]).decode().split('\0')
    for file in files:
        if not file.endswith('.py') or any(part in {'node_modules', 'test_data', 'testdata', 'templates'} for part in Path(file).parts):
            continue
        compile((root / file).read_bytes(), file, 'exec')
        count += 1
print(f'Repository configuration valid; {count} Python files parsed.')
summary = os.environ.get('GITHUB_STEP_SUMMARY')
if summary:
    with open(summary, 'a') as output:
        output.write(f'### Repository checks\n\nMode: `{config["mode"]}`. Python files parsed: {count}.\n')
