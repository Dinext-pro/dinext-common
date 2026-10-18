"""Regression tests for lifecycle bypasses and stale/skipped evidence."""
import unittest
from development_policy import Rejected, validate_route, validate_checks, needs_acceptance, current_checks


def pr(source, target, foreign=False):
    return {'head': {'ref': source, 'repo': {'full_name': 'outsider/app' if foreign else 'Dinext-pro/app'}},
            'base': {'ref': target, 'repo': {'full_name': 'Dinext-pro/app'}}}


def check(name, conclusion='success', app=15368):
    return {'name': name, 'status': 'completed', 'conclusion': conclusion, 'app': {'id': app}}


OWN = {'own': True, 'executed_checks': ['App unit tests']}
FORK = {'own': False, 'branches': ['main/*'], 'executed_checks': []}


class PolicyTests(unittest.TestCase):
    def test_feature_to_develop(self):
        validate_route(pr('feature/codex-controls', 'develop'), OWN, False)

    def test_foreign_feature_can_be_reviewed(self):
        validate_route(pr('feature/ui', 'develop', True), OWN, False)

    def test_release_name_without_develop_is_rejected(self):
        with self.assertRaises(Rejected):
            validate_route(pr('release/26.10', 'main'), OWN, False)

    def test_accepted_selective_release_is_admitted(self):
        validate_route(pr('release/26.10', 'main'), OWN, True)

    def test_hotfix_shortcut_rejected_even_if_accepted(self):
        with self.assertRaises(Rejected):
            validate_route(pr('hotfix/urgent', 'main'), OWN, True)

    def test_foreign_release_rejected(self):
        with self.assertRaises(Rejected):
            validate_route(pr('release/26.10', 'main', True), OWN, True)

    def test_develop_to_release(self):
        validate_route(pr('develop', 'release/26.10'), OWN, True)

    def test_feature_to_release_rejected(self):
        with self.assertRaises(Rejected):
            validate_route(pr('feature/test', 'release/26.10'), OWN, True)

    def test_frozen_branch_rejected(self):
        with self.assertRaises(Rejected):
            validate_route(pr('develope', 'develop'), OWN, True)

    def test_fork_does_not_require_develop(self):
        validate_route(pr('upgrade/3.0', 'main/v3'), FORK, False)

    def test_wrong_fork_target_rejected(self):
        with self.assertRaises(Rejected):
            validate_route(pr('upgrade/3.0', 'vendor/v3'), FORK, False)

    def test_docs_do_not_require_browser(self):
        self.assertEqual(needs_acceptance(['README.md', 'README.ru.md', '.github/workflows/ci.yml'], True), (False, False))

    def test_ui_requires_cypress(self):
        self.assertIn('Cypress', validate_checks(['app/public/js/form.js'], OWN, [check('App unit tests')])[0])

    def test_doctype_json_is_ui(self):
        self.assertTrue(needs_acceptance(['app/doctype/item/item.json'], True)[0])

    def test_fixture_client_script_is_ui(self):
        self.assertTrue(needs_acceptance(['app/fixtures/client_script.json'], True)[0])

    def test_skipped_unit_is_not_success(self):
        self.assertTrue(validate_checks(['README.md'], OWN, [check('App unit tests', 'skipped')]))

    def test_untrusted_app_cannot_attest(self):
        self.assertTrue(validate_checks(['app/public/js/form.js'], OWN, [check('App unit tests'), check('Cypress acceptance', app=1)]))

    def test_external_code_requires_compatibility(self):
        self.assertIn('Compatibility', validate_checks(['app/api.py'], FORK, [])[0])

    def test_matching_browser_and_compatibility_pass(self):
        self.assertEqual(validate_checks(['app/public/js/form.js'], FORK,
            [check('Acceptance / Cypress acceptance'), check('Compatibility acceptance')]), [])

    def test_stale_revision_does_not_attest(self):
        old = {**check('Cypress acceptance'), 'id': 10, 'head_sha': 'old'}
        self.assertEqual(current_checks([old], ['current', 'current-merge']), [])

    def test_latest_failure_replaces_old_success(self):
        old = {**check('Cypress acceptance'), 'id': 10, 'head_sha': 'current'}
        new = {**check('Cypress acceptance', 'failure'), 'id': 11, 'head_sha': 'current'}
        self.assertEqual(current_checks([new, old], ['current']), [new])

    def test_current_merge_evidence_is_accepted(self):
        merged = {**check('Cypress acceptance'), 'id': 11, 'head_sha': 'current-merge'}
        self.assertEqual(current_checks([merged], ['current', 'current-merge']), [merged])


if __name__ == '__main__':
    unittest.main()
