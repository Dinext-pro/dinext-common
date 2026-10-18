"""Read-only release preparation; never creates a tag, Release or deployment."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from development_policy import GitHub, evidence_present


def validate_tag(tag, own):
    pattern = r'v\d{2}\.\d{2}\.\d{2}-\d{2}' if own else r'v?\d+(?:\.\d+){1,3}(?:[-.][A-Za-z0-9.]+)?'
    if not re.fullmatch(pattern, tag):
        raise ValueError('Version does not match the repository release convention')
    if own:
        datetime.strptime(tag[1:9], '%y.%m.%d')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--branch', required=True)
    parser.add_argument('--sha', required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    registry = json.loads(Path(__file__).with_name('development-repositories.json').read_text())
    name = args.repository.removeprefix('Dinext-pro/')
    if args.repository != 'Dinext-pro/' + name or name not in registry:
        raise ValueError('Repository is outside the reviewed release registry')
    policy = registry[name]
    validate_tag(args.tag, policy['own'])
    if not re.fullmatch('[0-9a-f]{40}', args.sha):
        raise ValueError('An immutable full commit SHA is required')
    if policy['own'] and args.branch != 'main' or not policy['own'] and not args.branch.startswith('main/'):
        raise ValueError('Release must identify the stable Dinext line')
    api = GitHub(os.environ['GH_TOKEN'])
    root = '/repos/' + args.repository
    commit = api.request('GET', root + '/commits/' + args.branch)
    if commit['sha'] != args.sha:
        raise ValueError('Stable branch changed; review the new SHA')
    existing = api.request('GET', root + '/git/matching-refs/tags/' + args.tag)
    if any(x['ref'] == 'refs/tags/' + args.tag for x in existing):
        raise ValueError('Tag already exists and must remain immutable')
    checks = api.pages(root + '/commits/' + args.sha + '/check-runs', 'check_runs')
    for required in policy['executed_checks'] + ['Repository checks']:
        if not evidence_present(checks, required):
            raise ValueError('Required executed check missing: ' + required)
    record = {'repository': args.repository, 'branch': args.branch, 'commit': args.sha,
              'proposed_tag': args.tag, 'tree': commit['commit']['tree']['sha'],
              'prepared_at': datetime.now(timezone.utc).isoformat(), 'published': False,
              'next_step': 'Review release notes, compatibility evidence, manifest and owner publishing authorization.'}
    Path(args.output).write_text(json.dumps(record, indent=2) + '\n')
    print('Release preparation saved. No tag, Release or deployment was created.')


if __name__ == '__main__':
    main()
