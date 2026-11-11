"""Select reproducible dependency commits without changing trusted repository URLs."""
import re


def select_dependency_revisions(catalog, order, app, overrides):
    if not isinstance(overrides, dict):
        raise ValueError('dependency_revisions must map dependency names to full commit SHAs')
    dependencies = set(order) - {app}
    for name, revision in overrides.items():
        if name not in dependencies:
            raise ValueError('Revision override is not a dependency: ' + str(name))
        if not isinstance(revision, str) or not re.fullmatch(r'[0-9a-fA-F]{40}', revision):
            raise ValueError('Dependency revision must be a full commit SHA: ' + name)
    return {
        name: overrides[name].lower() if name in overrides else catalog[name].get('ci_sha') or catalog[name]['branch']
        for name in order if name != app
    }
