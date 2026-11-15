"""Run sidebar acceptance whenever the PR's scope cannot be verified."""
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen


SIDEBAR_PATHS = {
    'dinext_common/public/css/workspace_sidebar_hover.css',
    'dinext_common/public/js/workspace_sidebar_hover.js',
    'cypress/integration/workspace_sidebar_controls.js',
    'cypress.config.js',
    'cypress.sidebar.config.cjs',
    '.github/workflows/dinext-acceptance.yml',
    '.github/workflows/dinext-validation.yml',
    '.github/ci/sidebar_acceptance_paths.py',
    '.github/ci/public-apps.json',
}


def revisions(pull_request):
    return pull_request['head']['sha'], pull_request['base']['sha']


def requires_acceptance(get, event):
    try:
        path = '/pulls/' + str(int(event['number']))
        expected_revisions = revisions(event['pull_request'])
        before = get(path)
        expected_count = before['changed_files']
        if revisions(before) != expected_revisions or not 0 <= expected_count <= 3000:
            return True

        files = set()
        for page in range(1, (expected_count + 99) // 100 + 1):
            changed = get(f'{path}/files?per_page=100&page={page}')
            for file in changed:
                name = file['filename']
                if name in SIDEBAR_PATHS or file.get('previous_filename') in SIDEBAR_PATHS:
                    return True
                files.add(name)

        after = get(path)
        return (
            len(files) != expected_count
            or after['changed_files'] != expected_count
            or revisions(after) != expected_revisions
        )
    except (OSError, KeyError, TypeError, ValueError):
        return True


def main():
    root = os.environ['GITHUB_API_URL'] + '/repos/' + os.environ['GITHUB_REPOSITORY']
    headers = {
        'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
        'Accept': 'application/vnd.github+json',
    }
    def get(path):
        with urlopen(Request(root + path, headers=headers), timeout=10) as response:
            return json.load(response)

    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    result = 'true' if requires_acceptance(get, event) else 'false'
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        output.write(f'run={result}\n')


if __name__ == '__main__':
    main()
