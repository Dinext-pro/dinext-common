"""Trusted PR admission. Inspect proposed data; never execute proposed code."""
import base64
import fnmatch
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request


class Rejected(RuntimeError):
    pass


FROZEN = {'client-develop', 'client-release', 'dinord-develop', 'develope'}
FEATURE = ('feature/*', 'feat/*', 'ISS-*', 'hotfix/*', 'bug/*', 'fix/*')


def branch_class(target, own):
    if not own:
        return 'integration'
    if target == 'main':
        return 'main'
    if target == 'develop':
        return 'develop'
    if target.startswith('release/'):
        return 'release'
    raise Rejected('Target is not a maintained application line')


def validate_route(pr, policy, accepted_in_develop):
    source, target = pr['head']['ref'], pr['base']['ref']
    if source in FROZEN or target in FROZEN:
        raise Rejected('Legacy branch is frozen')
    if not policy['own']:
        if not any(fnmatch.fnmatchcase(target, p) for p in policy['branches']):
            raise Rejected('Target is not a maintained integration line')
        return
    kind = branch_class(target, True)
    if kind == 'develop':
        if not any(fnmatch.fnmatchcase(source, p) for p in FEATURE):
            raise Rejected('Develop accepts reviewed feature/fix branches')
    else:
        same_repository = pr['head']['repo']['full_name'] == pr['base']['repo']['full_name']
        allowed = source.startswith('release/') if kind == 'main' else source == 'develop'
        if not same_repository or not allowed:
            raise Rejected('Promotion requires develop -> release -> main')
        if not accepted_in_develop:
            raise Rejected('Release revision has not been accepted in develop')


def needs_acceptance(paths, own):
    runtime = [p for p in paths if not p.startswith(('.github/', '.cursor/', 'openspec/', 'docs/', 'tests/', 'cypress/'))
               and not p.lower().endswith(('.md', '.rst', '.txt')) and Path(p).name not in {'AGENTS.md', 'LICENSE'}]
    ui = any(p.endswith(('.js', '.mjs', '.ts', '.tsx', '.jsx', '.vue', '.css', '.scss', '.html'))
             or ('/doctype/' in p or '/workspace/' in p or '/page/' in p or '/report/' in p) and p.endswith('.json')
             or Path(p).name in {'client_script.json', 'web_page.json'} for p in runtime)
    return ui, bool(runtime) and not own


def evidence_present(checks, label):
    return any(c.get('app', {}).get('id') == 15368 and c.get('status') == 'completed'
               and c.get('conclusion') == 'success'
               and (c.get('name') == label or c.get('name', '').endswith(' / ' + label)) for c in checks)


def current_checks(checks, revisions):
    latest = {}
    for check in checks:
        if check.get('head_sha') not in revisions:
            continue
        key = (check['name'], check.get('app', {}).get('id'))
        if key not in latest or check['id'] > latest[key]['id']:
            latest[key] = check
    return list(latest.values())


def validate_checks(paths, policy, checks):
    ui, compatibility = needs_acceptance(paths, policy['own'])
    missing = []
    if ui and not evidence_present(checks, 'Cypress acceptance'):
        missing.append('Cypress acceptance for this PR revision')
    if compatibility and not evidence_present(checks, 'Compatibility acceptance'):
        missing.append('Compatibility acceptance for this PR revision')
    for name in policy.get('executed_checks', []):
        if not evidence_present(checks, name):
            missing.append(name + ' must execute successfully (not skip)')
    return missing


class GitHub:
    def __init__(self, token):
        self.token = token

    def request(self, method, path, data=None):
        if not path.startswith('/repos/Dinext-pro/') or '..' in urllib.parse.urlsplit(path).path.split('/'):
            raise Rejected('API request outside approved organization')
        request = urllib.request.Request('https://api.github.com' + path,
            data=None if data is None else json.dumps(data).encode(), method=method,
            headers={'Authorization': 'Bearer ' + self.token, 'Accept': 'application/vnd.github+json',
                     'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'Dinext-development-policy'})
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)

    def pages(self, path, key=None):
        rows = []
        for page in range(1, 31):
            result = self.request('GET', path + ('&' if '?' in path else '?') + f'per_page=100&page={page}')
            part = result[key] if key else result
            rows.extend(part)
            if len(part) < 100:
                return rows
        raise Rejected('Pagination limit exceeded; no partial validation')


def inspect_pr(api, repo, number, registry):
    root = '/repos/' + repo
    pr = api.request('GET', root + '/pulls/' + str(number))
    if pr['state'] != 'open':
        return
    policy = registry[repo.split('/')[1]]
    kind = branch_class(pr['base']['ref'], policy['own'])
    context = 'Dinext policy / ' + kind
    sha = pr['head']['sha']
    status_path = root + '/statuses/' + sha
    url = os.environ['GITHUB_SERVER_URL'] + '/' + repo + '/actions/runs/' + os.environ['GITHUB_RUN_ID']

    def report(state, description):
        # The status belongs to the inspected exact PR head, never the base SHA.
        api.request('POST', status_path, {'state': state, 'context': context,
                    'description': description[:140], 'target_url': url})

    report('pending', 'Inspecting current PR, accepted history and exact-revision evidence')
    try:
        accepted = False
        if policy['own'] and pr['base']['ref'] != 'develop':
            comparison = api.request('GET', root + '/compare/' + sha + '...develop')
            accepted = comparison['status'] in {'ahead', 'identical'}
        validate_route(pr, policy, accepted)
        config = api.request('GET', root + '/contents/.github/dinext-ci.json?ref=' + sha)
        config = json.loads(base64.b64decode(config['content']))
        if config.get('mode') != policy['mode'] or bool(config.get('frontend_tests')) != policy['frontend_tests']:
            raise Rejected('Proposed CI profile differs from the trusted registry')
        paths = [x['filename'] for x in api.pages(root + '/pulls/' + str(number) + '/files')]
        revisions = [sha]
        if pr.get('merge_commit_sha'):
            revisions.append(pr['merge_commit_sha'])
        checks = []
        for revision in revisions:
            checks.extend(api.pages(root + '/commits/' + revision + '/check-runs', 'check_runs'))
        # A failed newer rerun cannot be hidden by an older success.
        missing = validate_checks(paths, policy, current_checks(checks, revisions))
        refreshed = api.request('GET', root + '/pulls/' + str(number))
        if refreshed['head']['sha'] != sha or refreshed['base']['ref'] != pr['base']['ref']:
            raise Rejected('PR changed during validation; waiting for a fresh event')
        if missing:
            report('pending', '; '.join(missing))
            print(repo, number, 'waiting:', '; '.join(missing))
        else:
            report('success', 'Accepted route, trusted CI profile and applicable revision evidence verified')
            print(repo, number, 'policy passed at', sha)
    except Exception as error:
        report('failure', str(error))
        raise


def main():
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    registry = json.loads(Path(__file__).with_name('development-repositories.json').read_text())
    repo = os.environ['GITHUB_REPOSITORY']
    if repo.split('/')[1] not in registry:
        raise Rejected('Repository has no reviewed policy profile')
    api = GitHub(os.environ['GH_TOKEN'])
    if event.get('pull_request'):
        numbers = [event['pull_request']['number']]
    else:
        numbers = [p['number'] for p in api.pages('/repos/' + repo + '/pulls?state=open')]
    failures = []
    for number in numbers:
        try:
            inspect_pr(api, repo, number, registry)
        except Exception as error:
            print('Policy rejected PR', number, str(error), file=sys.stderr)
            failures.append(number)
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
