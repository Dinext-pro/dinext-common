import importlib.util
from pathlib import Path
import unittest


class TestDependencyRevisions(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).with_name('dependency_revisions.py')
        if not path.exists():
            self.fail('CI dependency override selection is not implemented')
        spec = importlib.util.spec_from_file_location('dependency_revisions', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.select = module.select_dependency_revisions
        self.catalog = {
            'frappe': {'ci_sha': 'f' * 40, 'branch': 'dinext/main/v15'},
            'dinext_common': {'ci_sha': 'b' * 40, 'branch': 'main'},
            'dinext_projects': {'branch': 'develop'},
        }
        self.order = ['frappe', 'dinext_common', 'dinext_projects']

    def test_explicit_dependency_sha_replaces_only_that_catalogue_pin(self):
        result = self.select(self.catalog, self.order, 'dinext_projects', {'dinext_common': 'a' * 40})
        self.assertEqual(result, {'frappe': 'f' * 40, 'dinext_common': 'a' * 40})

    def test_default_catalogue_pins_and_branch_fallback_are_retained(self):
        self.catalog['dinext_common'].pop('ci_sha')
        result = self.select(self.catalog, self.order, 'dinext_projects', {})
        self.assertEqual(result, {'frappe': 'f' * 40, 'dinext_common': 'main'})

    def test_bootstrap_frappe_is_selected_when_catalogue_dependencies_omit_it(self):
        result = self.select(self.catalog, ['dinext_common', 'dinext_projects'], 'dinext_projects', {})
        self.assertEqual(result, {'frappe': 'f' * 40, 'dinext_common': 'b' * 40})

    def test_own_app_and_unknown_dependency_cannot_be_overridden(self):
        for name in ['dinext_projects', 'unknown']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.select(self.catalog, self.order, 'dinext_projects', {name: 'a' * 40})

    def test_override_must_be_a_full_commit_sha(self):
        for value in ['develop', 'abc123', '--upload-pack=bad', '', None]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.select(self.catalog, self.order, 'dinext_projects', {'dinext_common': value})
        with self.assertRaises(ValueError):
            self.select(self.catalog, self.order, 'dinext_projects', ['a' * 40])


if __name__ == '__main__':
    unittest.main()
