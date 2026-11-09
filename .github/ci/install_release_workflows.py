"""Generate native release callers while retaining existing CI definitions."""
import argparse
import copy
from pathlib import Path
import re
import yaml


class WorkflowLoader(yaml.SafeLoader):
    yaml_implicit_resolvers = copy.deepcopy(yaml.SafeLoader.yaml_implicit_resolvers)


for key, resolvers in WorkflowLoader.yaml_implicit_resolvers.items():
    WorkflowLoader.yaml_implicit_resolvers[key] = [(tag, regex) for tag, regex in resolvers
                                                  if tag != 'tag:yaml.org,2002:bool']
WorkflowLoader.add_implicit_resolver('tag:yaml.org,2002:bool', re.compile(r'^(?:true|false)$', re.I), list('tTfF'))


def load_workflow(text):
    return yaml.load(text, Loader=WorkflowLoader)


def enable_release_events(text):
    data = load_workflow(text)
    if not isinstance(data.get('on'), dict):
        raise ValueError('Expected explicit workflow event mapping')
    events = data['on']
    if 'workflow_call' not in events:
        text, count = re.subn(r"(?m)^(['\"]?on['\"]?:)[ \t]*$", r'\1\n  workflow_call: {}', text, count=1)
        if count != 1:
            raise ValueError('Could not locate native workflow event block')
    push = events.get('push')
    if push is None:
        text = re.sub(r"(?m)^(['\"]?on['\"]?:)[ \t]*$", r"\1\n  push:\n    tags: ['v*', 'dinext/**']", text, count=1)
    elif not isinstance(push, dict):
        raise ValueError('Unexpected push filter')
    elif 'tags' not in push:
        text = re.sub(r'(?m)^  push:[ \t]*$', "  push:\n    tags: ['v*', 'dinext/**']", text, count=1)
    else:
        tags = list(dict.fromkeys(push['tags'] + ['v*', 'dinext/**']))
        text, count = re.subn(r'(?m)^    tags:.*$', '    tags: ' + str(tags), text, count=1)
        if not count:
            raise ValueError('Unsupported existing multiline tag filter')
    if 'release-context' not in data.get('jobs', {}):
        context_job = """jobs:
  release-context:
    name: Tag source context
    if: github.event_name == 'push' && github.ref_type == 'tag'
    runs-on: ubuntu-24.04
    timeout-minutes: 2
    steps:
      - name: Verify native tag context
        run: |
          test "$GITHUB_REF_TYPE" = tag
          test "$GITHUB_REF" = "refs/tags/$GITHUB_REF_NAME"
"""
        text, count = re.subn(r'(?m)^jobs:[ \t]*(?:\{\})?[ \t]*$', context_job.rstrip(), text, count=1)
        if count != 1:
            raise ValueError('Could not locate workflow jobs mapping')
    # A release workflow_call must not be cancelled by a separate branch validation run.
    text = re.sub(r'(?m)^(\s+group: dinext-(?:validation|acceptance)-)(?!\$\{\{ github.workflow)(.*)$',
                  r'\1${{ github.workflow }}-\2', text)
    return text


def release_caller(support_ref, acceptance):
    if not re.fullmatch(r'[0-9a-f]{40}', support_ref):
        raise ValueError('Shared workflows require an immutable full SHA')
    common = 'Dinext-pro/dinext-common/.github/workflows/'
    jobs = {
        'preflight': {'name': 'Release preflight', 'uses': common + 'dinext-release-preflight.yml@' + support_ref,
                      'with': {'support-ref': support_ref, 'version': '${{ inputs.version }}', 'commit': '${{ inputs.commit }}'}},
        'validation': {'name': 'Release validation', 'needs': 'preflight',
                       'uses': './.github/workflows/dinext-validation.yml'},
    }
    needs = ['preflight', 'validation']
    if acceptance:
        jobs['acceptance'] = {'name': 'Release acceptance', 'needs': 'preflight',
                              'uses': './.github/workflows/dinext-acceptance.yml'}
        needs.append('acceptance')
    jobs['publish'] = {'name': 'Publish verified release', 'needs': needs,
                       'uses': common + 'dinext-release-publish.yml@' + support_ref,
                       'secrets': {'DINEXT_RELEASE_APP_PRIVATE_KEY': '${{ secrets.DINEXT_RELEASE_APP_PRIVATE_KEY }}'},
                       'with': {'support-ref': support_ref, 'version': '${{ inputs.version }}',
                                'commit': '${{ inputs.commit }}', 'dry-run': '${{ inputs.dry-run }}',
                                'artifact-id': '${{ needs.preflight.outputs.artifact-id }}',
                                'preparation-sha256': '${{ needs.preflight.outputs.sha256 }}'}}
    workflow = {'name': 'Release', 'on': {'workflow_dispatch': {'inputs': {
        'version': {'description': 'Version tag to release', 'required': True, 'type': 'string'},
        'commit': {'description': 'Full 40-character stable branch SHA', 'required': True, 'type': 'string'},
        'dry-run': {'description': 'Validate only; create no tag or GitHub Release', 'type': 'boolean', 'default': True}}}},
        'permissions': {'contents': 'read', 'actions': 'read'},
        'concurrency': {'group': 'dinext-release-${{ github.repository }}', 'cancel-in-progress': False}, 'jobs': jobs}
    return '# Shared release policy is pinned; deploy is outside this workflow.\n' + yaml.safe_dump(workflow, sort_keys=False, width=120)


def install(root, support_ref):
    directory = Path(root) / '.github/workflows'
    validation = directory / 'dinext-validation.yml'
    if not validation.is_file():
        raise ValueError('Reviewed validation workflow is missing')
    acceptance = directory / 'dinext-acceptance.yml'
    for path in [validation] + ([acceptance] if acceptance.exists() else []):
        path.write_text(enable_release_events(path.read_text()))
    (directory / 'dinext-release.yml').write_text(release_caller(support_ref, acceptance.exists()))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root')
    parser.add_argument('--support-ref', required=True)
    args = parser.parse_args()
    install(args.root, args.support_ref)
