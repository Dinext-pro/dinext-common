"""Publish through native GitHub APIs/CLI after the read-only release gates."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.parse import quote
import zipfile
from release_policy import (GitHub, Rejected, inspect_release, inspect_postchecks, registry_files,
                            request_from_environment, require_jobs, scope, verify_prechecks,
                            verify_tag, write_record, WORKFLOW)


def gh(args, binary=False):
    result = subprocess.run(['gh', *args], check=True, capture_output=True)
    return result.stdout if binary else result.stdout.decode()


def validate_origin(request, proof, artifact, raw):
    record = json.loads(raw)
    for key in ('repository', 'commit', 'version', 'run_id'):
        if proof.get(key) != request[key] or record.get(key) != request[key]:
            raise Rejected('Existing tag belongs to a different release operation')
    if proof.get('kind') != 'dinext-release-v1' or artifact.get('expired') or artifact['id'] != proof['artifact_id']:
        raise Rejected('Origin evidence is unavailable or expired')
    origin = artifact.get('workflow_run', {})
    if origin.get('id') != request['run_id'] or origin.get('head_sha') != request['commit']:
        raise Rejected('Preparation artifact is not from the exact release run')
    if hashlib.sha256(raw).hexdigest() != proof['sha256']:
        raise Rejected('Preparation evidence digest mismatch')
    if record['workflow_ref'] != request['workflow_ref'] or record['workflow_sha'] != request['workflow_sha']:
        raise Rejected('Original workflow identity changed')
    return record


def recover(api, request):
    tag = verify_tag(api, request)
    try:
        proof = json.loads(tag['message'])
    except (ValueError, KeyError) as error:
        raise Rejected('Existing tag has no release workflow origin') from error
    root = '/repos/' + request['repository']
    artifact = api.request('GET', root + '/actions/artifacts/' + str(proof.get('artifact_id', 0)))
    if artifact.get('expired'):
        raise Rejected('Original preparation artifact expired; use a new version')
    raw_zip = gh(['api', root + '/actions/artifacts/' + str(artifact['id']) + '/zip'], binary=True)
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as archive:
        if archive.namelist() != ['release-preparation.json']:
            raise Rejected('Unexpected preparation artifact files')
        raw = archive.read('release-preparation.json')
    record = validate_origin(request, proof, artifact, raw)
    run = api.request('GET', root + '/actions/runs/' + str(request['run_id']))
    if run['path'] != WORKFLOW or run['head_sha'] != request['commit'] or run['event'] != 'workflow_dispatch':
        raise Rejected('Recovery requires the original trusted release workflow run')
    return record, tag


def prepare(api, request, registry, acceptance):
    root, policy = scope(api, request, registry)
    refs = api.request('GET', root + '/git/matching-refs/tags/' + quote(request['version'], safe='/'))
    exists = any(r['ref'] == 'refs/tags/' + request['version'] for r in refs)
    if exists:
        record, tag = recover(api, request)
        name = request['repository'].split('/')[1]
        if (record['own'] != policy['own'] or record['validation_checks'] != ['Repository checks'] + policy['executed_checks']
                or record['acceptance_checks'] != acceptance.get(name)):
            raise Rejected('Reviewed release profile changed since original preparation')
        return record, tag
    return inspect_release(api, request, registry, acceptance), None


def verify_credential(api, record, app_id, selected):
    if len(selected) != 1 or selected[0]['full_name'] != record['repository']:
        raise Rejected('App token must be scoped to exactly this repository')
    root = '/repos/' + record['repository']
    rules = api.pages(root + '/rulesets')
    creation = []
    immutable = []
    for summary in rules:
        if summary['target'] != 'tag' or summary['enforcement'] != 'active':
            continue
        detail = api.request('GET', root + '/rulesets/' + str(summary['id']))
        types = {r['type'] for r in detail['rules']}
        if 'creation' in types:
            creation.append(detail)
            allowed = any(a['actor_type'] == 'Integration' and a['actor_id'] == app_id
                          and a['bypass_mode'] == 'always' for a in detail.get('bypass_actors', []))
            allowed = allowed or detail.get('current_user_can_bypass') in {'always', 'exempt'}
            if not allowed:
                raise Rejected('Release App cannot bypass active tag creation restriction')
        if summary['name'] == 'Dinext immutable tags':
            immutable.append(detail)
            if (not {'update', 'deletion'} <= types or detail.get('bypass_actors')
                    or detail.get('current_user_can_bypass', 'never') != 'never'):
                raise Rejected('Immutable tag safety must have no bypass')
    if not creation or len(immutable) != 1:
        raise Rejected('Expected creation and immutable tag rules are missing')


def create_tag(api, record, artifact_id, digest, evidence):
    require_jobs(evidence, record['validation_checks'] + record['acceptance_checks'])
    root = '/repos/' + record['repository']
    stable = api.request('GET', root + '/commits/' + quote(record['branch'], safe=''))
    if stable['sha'] != record['commit']:
        raise Rejected('Stable branch moved immediately before tag creation')
    proof = {'kind': 'dinext-release-v1', 'repository': record['repository'], 'version': record['version'],
             'commit': record['commit'], 'run_id': record['run_id'], 'artifact_id': int(artifact_id), 'sha256': digest}
    obj = api.request('POST', root + '/git/tags', {'tag': record['version'], 'object': record['commit'],
                     'type': 'commit', 'message': json.dumps(proof, sort_keys=True)})
    ref = api.request('POST', root + '/git/refs', {'ref': 'refs/tags/' + record['version'], 'sha': obj['sha']})
    if ref['object']['sha'] != obj['sha']:
        raise Rejected('GitHub returned an unexpected tag object')
    return {'object_sha': obj['sha'], 'commit': record['commit'], 'origin': proof}


def release_marker(record):
    return '<!-- dinext-release:' + str(record['run_id']) + ':' + record['commit'] + ' -->'


def validate_existing_release(record, release, app_slug):
    author = release.get('author', {})
    if (release['tag_name'] != record['version'] or release['name'] != record['version']
            or author.get('login') != app_slug + '[bot]' or author.get('type') != 'Bot'
            or release_marker(record) not in release.get('body', '')):
        raise Rejected('Existing Release belongs to a different operation or author')


def prepare_content(writer, record):
    if 'release_notes' in record:
        if not record['release_notes'].strip():
            raise Rejected('Prepared release notes are empty')
        return record
    notes = writer.request('POST', '/repos/' + record['repository'] + '/releases/generate-notes',
                           {'tag_name': record['version'], 'target_commitish': record['commit']})
    body = notes['body'].strip()
    if not body:
        raise Rejected('GitHub generated empty release notes')
    return {**record, 'release_notes': body}


def publish_release(command, record, notes, assets, verify_assets, existing=None):
    repo = record['repository']
    tag = record['version']
    if existing is None:
        command(['release', 'create', tag, '--repo', repo, '--draft', '--verify-tag',
                 '--title', tag, '--notes-file', str(notes)])
    elif not existing['draft']:
        if verify_assets:
            verify_assets()
        return
    command(['release', 'upload', tag, '--repo', repo, *[str(p) for p in assets], '--clobber'])
    if verify_assets:
        verify_assets()
    command(['release', 'edit', tag, '--repo', repo, '--draft=false', '--latest=' + ('true' if record['own'] else 'false')])


def release_assets(api, record, paths, notes=None):
    root = '/repos/' + record['repository']
    releases = api.pages(root + '/releases')
    matches = [r for r in releases if r['tag_name'] == record['version']]
    if len(matches) != 1 or matches[0]['name'] != record['version']:
        raise Rejected('Release metadata does not match the version tag')
    release = matches[0]
    if notes is not None and release.get('body', '').replace('\r\n', '\n').strip() != Path(notes).read_text().replace('\r\n', '\n').strip():
        raise Rejected('Release notes differ from the frozen preparation')
    assets = api.pages(root + '/releases/' + str(release['id']) + '/assets')
    by_name = {a['name']: a for a in assets}
    for path in paths:
        digest = 'sha256:' + hashlib.sha256(Path(path).read_bytes()).hexdigest()
        asset = by_name.get(Path(path).name)
        if not asset or asset['size'] != Path(path).stat().st_size or asset.get('digest') != digest:
            raise Rejected('Uploaded Release evidence failed digest verification: ' + Path(path).name)
    return release


def notes_and_manifest(api, record, post, directory):
    directory.mkdir(parents=True, exist_ok=True)
    body = record['release_notes'].strip()
    if not body:
        raise Rejected('Prepared release notes are empty')
    manifest = {'schema_version': 1, 'repository': record['repository'], 'branch': record['branch'],
                'tag': record['version'], 'commit': record['commit'], 'tree': record['tree'],
                'initiator': record['actor'], 'pull_request': record['pull_request'],
                'release_run': 'https://github.com/' + record['repository'] + '/actions/runs/' + str(record['run_id']),
                'coverage': record['validation_checks'] + record['acceptance_checks']}
    if not record['own']:
        manifest['upstream_version'] = record['version'].removeprefix('dinext/').rsplit('-dinext.', 1)[0]
    write_record(directory / 'release-manifest.json', manifest)
    write_record(directory / 'release-verification.json', post)
    (directory / 'release-notes.md').write_text(body + '\n\nCommit: `' + record['commit'] + '`\n\n'
        + 'Validation: ' + ', '.join(manifest['coverage']) + '.\n\n' + manifest['release_run'] + '\n\n' + release_marker(record) + '\n')
    return directory / 'release-notes.md', [directory / 'release-manifest.json', directory / 'release-verification.json']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['prepare', 'tag', 'postcheck', 'publish', 'credential'])
    parser.add_argument('--record', default='release-preparation.json')
    parser.add_argument('--artifact-id', type=int)
    parser.add_argument('--digest')
    args = parser.parse_args()
    api = GitHub(os.environ.get('GITHUB_TOKEN', os.environ['GH_TOKEN']))
    writer = GitHub(os.environ['GH_TOKEN'])
    registry, acceptance = registry_files()
    request = request_from_environment()
    if args.phase == 'prepare':
        record, tag = prepare(api, request, registry, acceptance)
        write_record(args.record, record)
        output = os.environ.get('GITHUB_OUTPUT')
        if output:
            with open(output, 'a') as stream:
                stream.write('sha256=' + hashlib.sha256(Path(args.record).read_bytes()).hexdigest() + '\n')
        print('Release preparation verified; no writes.')
        return
    record = json.loads(Path(args.record).read_text())
    # Every phase revalidates live scope, stable source and initial/rerun permissions.
    scope(api, request, registry)
    for key in ('repository', 'version', 'commit', 'run_id', 'workflow_ref', 'workflow_sha'):
        if record[key] != request[key]:
            raise Rejected('Preparation differs from this release request')
    if args.phase == 'credential':
        verify_prechecks(api, record)
        selected = json.loads(gh(['api', '/installation/repositories']))['repositories']
        verify_credential(writer, record, int(os.environ['RELEASE_APP_ID']), selected)
        record = prepare_content(writer, record)
        write_record(args.record, record)
        output = os.environ.get('GITHUB_OUTPUT')
        if output:
            with open(output, 'a') as stream:
                stream.write('sha256=' + hashlib.sha256(Path(args.record).read_bytes()).hexdigest() + '\n')
        print('Release App credential and generated notes verified; no persistent writes.')
    elif args.phase == 'tag':
        evidence = verify_prechecks(api, record)
        refs = api.request('GET', '/repos/' + record['repository'] + '/git/matching-refs/tags/' + quote(record['version'], safe='/'))
        if any(r['ref'] == 'refs/tags/' + record['version'] for r in refs):
            original, tag = recover(api, request)
            if original != record:
                raise Rejected('Recovered preparation changed')
            receipt = {'object_sha': tag['object_sha'], 'commit': record['commit'], 'recovered': True}
        else:
            if not args.artifact_id or not args.digest or hashlib.sha256(Path(args.record).read_bytes()).hexdigest() != args.digest:
                raise Rejected('Preparation artifact and SHA256 are required')
            receipt = create_tag(writer, record, args.artifact_id, args.digest, evidence)
        receipt['prechecks'] = evidence
        write_record('release-tag-receipt.json', receipt)
    elif args.phase == 'postcheck':
        deadline = time.monotonic() + 150 * 60
        while True:
            tag = verify_tag(api, record)
            result = inspect_postchecks(api, record)
            if result['state'] == 'success':
                result['tag'] = tag
                write_record('release-postchecks.json', result)
                break
            if time.monotonic() >= deadline:
                raise Rejected('Timed out waiting for exact tag validation')
            print(result['reason'], flush=True)
            time.sleep(20)
    else:
        tag = verify_tag(api, record)
        post = json.loads(Path('release-postchecks.json').read_text())
        fresh = inspect_postchecks(api, record)
        if post['state'] != 'success' or fresh['state'] != 'success' or post['tag']['object_sha'] != tag['object_sha']:
            raise Rejected('Post-tag evidence changed before publication')
        notes, assets = notes_and_manifest(writer, record, {**fresh, 'tag': tag}, Path('release-assets'))
        existing = [r for r in writer.pages('/repos/' + record['repository'] + '/releases') if r['tag_name'] == record['version']]
        if len(existing) > 1:
            raise Rejected('Conflicting Releases')
        if existing:
            validate_existing_release(record, existing[0], os.environ['RELEASE_APP_SLUG'])
        if existing and not existing[0]['draft']:
            # Published evidence must already match; an owned draft can refill missing assets.
            previous = Path('prior-manifest')
            previous.mkdir(exist_ok=True)
            gh(['release', 'download', record['version'], '--repo', record['repository'], '--pattern', 'release-manifest.json', '--dir', str(previous), '--clobber'])
            old = json.loads((previous / 'release-manifest.json').read_text())
            current = json.loads(assets[0].read_text())
            if old != current:
                raise Rejected('Existing Release belongs to a different operation')
        publish_release(gh, record, notes, assets, lambda: release_assets(writer, record, assets, notes), existing[0] if existing else None)
        result = release_assets(writer, record, assets, notes)
        if result['draft']:
            raise Rejected('Release was not published')
        print(result['html_url'])


if __name__ == '__main__':
    main()
