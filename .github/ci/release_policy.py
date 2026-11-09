"""Read-only Dinext release gates; GitHub Actions owns orchestration."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import quote
from development_policy import GitHub, Rejected

WORKFLOW = '.github/workflows/dinext-release.yml'
VALIDATION = '.github/workflows/dinext-validation.yml'
ACCEPTANCE = '.github/workflows/dinext-acceptance.yml'


def validate_version(tag, own):
    if own:
        if not re.fullmatch(r'v\d{2}\.\d{2}\.\d{2}-(?:0[1-9]|[1-9]\d)', tag):
            raise Rejected('Own releases require vYY.MM.DD-XX with positive sequence')
        try:
            datetime.strptime(tag[1:9], '%y.%m.%d')
        except ValueError as error:
            raise Rejected('Release date is invalid') from error
    else:
        if not re.fullmatch(r'dinext/v?\d+(?:\.\d+){1,3}(?:[-.][A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*)?', tag):
            raise Rejected('External releases require a dinext/ upstream-derived version')
        match = re.search(r'-dinext\.(\d+)$', tag)
        if match and int(match[1]) < 1:
            raise Rejected('Dinext patch number must be positive')


def validate_request(repository, policy, metadata, branch, sha, workflow_sha, actors):
    if not re.fullmatch(r'Dinext-pro/[A-Za-z0-9_.-]+', repository):
        raise Rejected('Repository outside Dinext-pro')
    if metadata.get('full_name') != repository or metadata.get('private') is not False or metadata.get('archived') is not False:
        raise Rejected('Release requires a currently active public repository')
    stable = ['main'] if policy['own'] else policy['branches']
    if branch not in stable:
        raise Rejected('Release source must be an exact reviewed stable branch')
    if not re.fullmatch(r'[0-9a-f]{40}', sha) or workflow_sha != sha:
        raise Rejected('Requested full SHA must equal the trusted workflow source revision')
    if not actors or any(role != 'admin' and not (actor == 'russsik1' and role == 'maintain') for actor, role in actors.items()):
        raise Rejected('Initial and rerun actors must be russsik1 or current repository administrators')


def require_jobs(jobs, labels):
    selected = []
    for label in labels:
        matching = [j for j in jobs if j['name'] == label or j['name'].endswith(' / ' + label)]
        if not matching:
            raise Rejected('Required executed job missing: ' + label)
        latest = max(matching, key=lambda j: (j.get('run_attempt', 1), j['id']))
        if latest.get('status') != 'completed' or latest.get('conclusion') != 'success':
            raise Rejected('Required job did not execute successfully: ' + label)
        selected.append({k: latest.get(k) for k in ('id', 'name', 'status', 'conclusion', 'run_attempt', 'html_url')})
    return selected


def registry_files():
    root = Path(__file__).parent
    return (json.loads((root / 'development-repositories.json').read_text()),
            json.loads((root / 'release-acceptance.json').read_text()))


def scope(api, request, registry):
    repository = request['repository']
    name = repository.removeprefix('Dinext-pro/')
    if repository != 'Dinext-pro/' + name or name not in registry:
        raise Rejected('Repository has no reviewed release profile')
    policy = registry[name]
    root = '/repos/' + repository
    metadata = api.request('GET', root)
    actors = {actor: api.request('GET', root + '/collaborators/' + quote(actor, safe='') + '/permission')['role_name']
              for actor in {request['actor'], request['triggering_actor']}}
    validate_request(repository, policy, metadata, request['branch'], request['commit'], request['workflow_sha'], actors)
    expected_ref = repository + '/' + WORKFLOW + '@refs/heads/' + request['branch']
    if request['workflow_ref'] != expected_ref:
        raise Rejected('Release must originate in the reviewed stable caller workflow')
    return root, policy


def inspect_release(api, request, registry, acceptance):
    root, policy = scope(api, request, registry)
    name = request['repository'].split('/')[1]
    if name not in acceptance:
        raise Rejected('Release acceptance profile is missing')
    validate_version(request['version'], policy['own'])
    stable = api.request('GET', root + '/commits/' + quote(request['branch'], safe=''))
    if stable['sha'] != request['commit']:
        raise Rejected('Stable branch moved; request its current full SHA')
    refs = api.request('GET', root + '/git/matching-refs/tags/' + quote(request['version'], safe='/'))
    if any(ref['ref'] == 'refs/tags/' + request['version'] for ref in refs):
        raise Rejected('Tag exists; only its original workflow run can resume')
    if any(r['tag_name'] == request['version'] for r in api.pages(root + '/releases')):
        raise Rejected('A GitHub Release already uses this version')
    prs = api.pages(root + '/commits/' + request['commit'] + '/pulls')
    accepted = [p for p in prs if p.get('merged_at') and p['merge_commit_sha'] == request['commit']
                and p['base']['ref'] == request['branch'] and p['base']['repo']['full_name'] == request['repository']]
    if policy['own']:
        accepted = [p for p in accepted if p['head']['ref'].startswith('release/')
                    and p['head']['repo'] and p['head']['repo']['full_name'] == request['repository']]
        accepted = [p for p in accepted if api.request('GET', root + '/compare/' + p['head']['sha'] + '...develop')['status']
                    in {'ahead', 'identical'}]
    if not accepted:
        raise Rejected('Exact stable commit has no accepted release/integration PR route')
    return {**request, 'schema_version': 1, 'tree': stable['commit']['tree']['sha'],
            'pull_request': accepted[0]['number'], 'own': policy['own'],
            'validation_checks': ['Repository checks'] + policy['executed_checks'],
            'acceptance_checks': acceptance[name], 'prepared_at': datetime.now(timezone.utc).isoformat()}


def verify_prechecks(api, record):
    root = '/repos/' + record['repository']
    run = api.request('GET', root + '/actions/runs/' + str(record['run_id']))
    if run['head_sha'] != record['commit'] or run['event'] != 'workflow_dispatch' or run['path'] != WORKFLOW:
        raise Rejected('Pre-tag evidence must come from this exact release run and SHA')
    jobs = api.pages(root + '/actions/runs/' + str(record['run_id']) + '/jobs?filter=latest', 'jobs')
    return require_jobs(jobs, record['validation_checks'] + record['acceptance_checks'])


def inspect_postchecks(api, record):
    root = '/repos/' + record['repository']
    expected = [(VALIDATION, record['validation_checks'])]
    if record['acceptance_checks']:
        expected.append((ACCEPTANCE, record['acceptance_checks']))
    evidence = []
    for workflow, labels in expected:
        path = root + '/actions/workflows/' + workflow.split('/')[-1] + '/runs?event=push&head_sha=' + record['commit']
        runs = api.pages(path, 'workflow_runs')
        matching = [r for r in runs if r['head_sha'] == record['commit'] and r['head_branch'] == record['version']
                    and r['event'] == 'push' and r['path'] == workflow]
        if not matching:
            return {'state': 'pending', 'reason': 'Waiting for tag-triggered ' + workflow}
        run = max(matching, key=lambda r: (r['id'], r.get('run_attempt', 1)))
        if run['status'] != 'completed':
            return {'state': 'pending', 'reason': 'Waiting for run ' + str(run['id'])}
        if run['conclusion'] != 'success':
            raise Rejected('Tag-triggered workflow failed: ' + workflow)
        jobs = api.pages(root + '/actions/runs/' + str(run['id']) + '/jobs?filter=latest', 'jobs')
        evidence.append({'workflow': workflow, 'run_id': run['id'], 'jobs': require_jobs(jobs, labels)})
    return {'state': 'success', 'runs': evidence}


def verify_tag(api, record):
    root = '/repos/' + record['repository']
    ref = api.request('GET', root + '/git/ref/tags/' + quote(record['version'], safe='/'))
    obj = ref['object']
    if obj['type'] != 'tag':
        raise Rejected('Release requires its annotated version tag')
    tag = api.request('GET', root + '/git/tags/' + obj['sha'])
    if (tag['object'].get('type'), tag['object'].get('sha')) != ('commit', record['commit']) or tag['tag'] != record['version']:
        raise Rejected('Remote tag does not identify the requested exact commit')
    return {'object_sha': obj['sha'], 'commit': record['commit'], 'message': tag['message']}


def write_record(path, record):
    Path(path).write_text(json.dumps(record, sort_keys=True, indent=2) + '\n')


def request_from_environment():
    return {'repository': os.environ['GITHUB_REPOSITORY'], 'branch': os.environ['GITHUB_REF_NAME'],
            'workflow_sha': os.environ['GITHUB_SHA'], 'workflow_ref': os.environ['GITHUB_WORKFLOW_REF'],
            'commit': os.environ['RELEASE_COMMIT'], 'version': os.environ['RELEASE_VERSION'],
            'actor': os.environ['GITHUB_ACTOR'], 'triggering_actor': os.environ['GITHUB_TRIGGERING_ACTOR'],
            'run_id': int(os.environ['GITHUB_RUN_ID']), 'run_attempt': int(os.environ['GITHUB_RUN_ATTEMPT'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='release-preparation.json')
    args = parser.parse_args()
    api = GitHub(os.environ['GH_TOKEN'])
    registry, acceptance = registry_files()
    record = inspect_release(api, request_from_environment(), registry, acceptance)
    write_record(args.output, record)
    output = os.environ.get('GITHUB_OUTPUT')
    if output:
        with open(output, 'a') as stream:
            stream.write('sha256=' + hashlib.sha256(Path(args.output).read_bytes()).hexdigest() + '\n')
    print('Release preflight passed; no tag, Release or deployment created.')


if __name__ == '__main__':
    main()
