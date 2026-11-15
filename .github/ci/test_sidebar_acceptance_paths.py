import unittest

from sidebar_acceptance_paths import requires_acceptance


PR = '/pulls/7'
EVENT = {'number': 7, 'pull_request': {'base': {'sha': 'base'}, 'head': {'sha': 'head'}}}
MATCH = 'dinext_common/public/js/workspace_sidebar_hover.js'
OTHER = 'docs/other.md'


def metadata(count, head='head', base='base'):
    return {'base': {'sha': base}, 'head': {'sha': head}, 'changed_files': count}


def files(*names):
    return [{'filename': name} for name in names]


class SidebarAcceptancePathsTests(unittest.TestCase):
    def test_matching_path_after_first_page(self):
        requests = {
            PR: metadata(101),
            PR + '/files?per_page=100&page=1': files(*(f'docs/{index}.md' for index in range(100))),
            PR + '/files?per_page=100&page=2': files(MATCH),
        }
        self.assertTrue(requires_acceptance(requests.__getitem__, EVENT))

    def test_unrelated_paths(self):
        requests = {PR: metadata(1), PR + '/files?per_page=100&page=1': files(OTHER)}
        self.assertFalse(requires_acceptance(requests.__getitem__, EVENT))

    def test_renamed_out_of_scope_path(self):
        requests = {
            PR: metadata(1),
            PR + '/files?per_page=100&page=1': [{'filename': OTHER, 'previous_filename': MATCH}],
        }
        self.assertTrue(requires_acceptance(requests.__getitem__, EVENT))

    def test_incomplete_file_list(self):
        requests = {PR: metadata(2), PR + '/files?per_page=100&page=1': files(OTHER)}
        self.assertTrue(requires_acceptance(requests.__getitem__, EVENT))

    def test_duplicate_file_cannot_hide_a_missing_file(self):
        requests = {PR: metadata(2), PR + '/files?per_page=100&page=1': files(OTHER, OTHER)}
        self.assertTrue(requires_acceptance(requests.__getitem__, EVENT))

    def test_revision_changes_during_evaluation(self):
        for new_metadata in (metadata(1, head='moved'), metadata(1, base='moved'), metadata(2)):
            with self.subTest(metadata=new_metadata):
                snapshots = iter([metadata(1), new_metadata])
                def get(path):
                    return next(snapshots) if path == PR else files(OTHER)
                self.assertTrue(requires_acceptance(get, EVENT))

    def test_api_failure_and_truncation(self):
        def unavailable(path):
            raise OSError('unavailable')
        self.assertTrue(requires_acceptance(unavailable, EVENT))
        self.assertTrue(requires_acceptance(lambda _path: metadata(3001), EVENT))


if __name__ == '__main__':
    unittest.main()
