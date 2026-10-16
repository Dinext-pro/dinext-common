"""Build an isolated bench from public code and run the owning app's tests."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

support = Path(__file__).resolve().parent
source = Path(sys.argv[1]).resolve()
config = json.loads((source / '.github/dinext-ci.json').read_text())
catalog = json.loads((support / 'public-apps.json').read_text())
app = config['app']
assert app in catalog
bench = Path(os.environ['RUNNER_TEMP']) / 'dinext-test-bench'
assert not bench.exists(), 'Each CI run requires a fresh bench'
site = 'ci.test'

def run(*args, cwd=None, timeout=1800):
    print('+', ' '.join(str(x) for x in args), flush=True)
    subprocess.run([str(x) for x in args], cwd=cwd or bench, check=True, timeout=timeout)

def dependency_order(name, active=None, done=None):
    active = set() if active is None else active
    done = [] if done is None else done
    if name in done:
        return done
    if name in active:
        raise RuntimeError('Dependency cycle: ' + name)
    active.add(name)
    for dependency in catalog[name].get('dependencies', []) + catalog[name].get('test_dependencies', []):
        dependency_order(dependency, active, done)
    active.remove(name)
    done.append(name)
    return done

order = dependency_order(app)
for post in config.get('post_install', []):
    dependency_order(post, done=order)
if config['mode'] == 'platform-smoke':
    dependency_order('erpnext', done=order)
def pinned_checkout(name):
    spec = catalog[name]
    destination = Path(os.environ['RUNNER_TEMP']) / 'dinext-ci-inputs' / name
    destination.mkdir(parents=True)
    run('git', 'init', str(destination), cwd=destination.parent)
    revision = spec.get('ci_sha') or spec['branch']
    run('git', 'fetch', '--no-tags', '--depth=1', spec['repository'], revision, cwd=destination)
    run('git', 'checkout', '--detach', 'FETCH_HEAD', cwd=destination)
    run('git', 'update-ref', 'refs/heads/dinext-ci-pinned', 'HEAD', cwd=destination)
    return destination

framework_source = source if app == 'frappe' else pinned_checkout('frappe')
run('git', 'update-ref', 'refs/heads/dinext-ci-input', 'HEAD', cwd=framework_source)
arguments = ['bench', 'init', str(bench), '--frappe-path', str(framework_source),
    '--frappe-branch', 'dinext-ci-input',
    '--skip-assets', '--skip-redis-config-generation', '--python', sys.executable]
run(*arguments, cwd=bench.parent)
common = bench / 'sites/common_site_config.json'
settings = json.loads(common.read_text())
settings.update({'db_host': '127.0.0.1', 'db_port': 3306,
    'redis_cache': 'redis://127.0.0.1:6379/0', 'redis_queue': 'redis://127.0.0.1:6379/1',
    'redis_socketio': 'redis://127.0.0.1:6379/2', 'server_script_enabled': 1,
    'pause_scheduler': 1, 'mute_emails': True})
common.write_text(json.dumps(settings))
for name in order:
    if name == 'frappe':
        continue
    # Keep the tested app at its exact PR merge commit. Dependencies use the
    # original GitLab CI's pinned revisions, translated through sanitized SHA maps.
    location = source if name == app else pinned_checkout(name)
    run('bench', 'get-app', '--skip-assets', name, str(location))
run(bench / 'env/bin/python', '-m', 'pip', 'install', 'unittest-xml-reporting~=3.2.0')
run('bench', 'setup', 'requirements', '--dev')
run('bench', 'new-site', site, '--db-host', '127.0.0.1', '--no-mariadb-socket',
    '--mariadb-root-password', 'ci', '--admin-password', 'ci-admin')
for name in order:
    if name != 'frappe':
        run('bench', '--site', site, 'execute', 'frappe.cache_manager.clear_global_cache')
        run('bench', '--site', site, 'install-app', name)
run('bench', '--site', site, 'set-config', 'allow_tests', 'true')
run('bench', '--site', site, 'migrate')
run('bench', 'build')
run('bench', '--site', site, 'execute', 'frappe.ping')
if config['mode'] == 'platform-smoke':
    print('Platform pair installed and offline smoke passed.', flush=True)
else:
    run(bench / 'env/bin/python', support / 'site_seed.py', site, cwd=bench / 'sites')
    report = Path(os.environ['RUNNER_TEMP']) / (app + '-unit.xml')
    arguments = ['bench', '--site', site, 'run-tests', '--app', app, '--junit-xml-output=' + str(report)]
    if config.get('skip_test_records'):
        arguments.append('--skip-test-records')
    run(*arguments)
    assert report.is_file(), 'Unit runner did not produce a JUnit report'
    tree = ET.parse(report)
    suites = list(tree.iter('testsuite'))
    assert tree.getroot().tag in {'testsuite', 'testsuites'}, 'Invalid JUnit report root'
    failures = sum(int(s.get('failures', 0)) + int(s.get('errors', 0)) for s in suites)
    total = sum(int(s.get('tests', 0)) for s in suites)
    assert not failures, f'{failures} unit failures/errors'
    print(f'Unit tests complete: {total} tests.', flush=True)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as output:
            output.write(f'### App tests\n\n`{app}`: {total} tests; failures/errors: {failures}.\n')
