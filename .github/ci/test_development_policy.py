"""Regression tests for lifecycle bypasses and stale/skipped evidence."""
import unittest
from development_policy import Rejected, validate_route, validate_checks, needs_acceptance, current_checks


def pr(source, target, foreign=False):
    return {'head': {'ref': source, 'repo': {'full_name': 'outsider/app' if foreign else 'Dinext-pro/app'}},
            'base': {'ref': target, 'repo': {'full_name': 'Dinext-pro/app'}}}


def check(name, conclusion='success', app=15368):
    return {'name': name, 'status': 'completed', 'conclusion': conclusion, 'app': {'id': app}}


OWN = {'own': True, 'executed_checks': ['App unit tests']}
FORK = {'own': False, 'branches': ['dinext/main/v3'], 'legacy_branches': ['main/v3'], 'executed_checks': []}


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
        validate_route(pr('dinext/upgrade/3.0', 'dinext/main/v3'), FORK, False)

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


    def test_external_patch_branch_remains_allowed(self):
        validate_route(pr('patch-1', 'dinext/main/v3', True), FORK, False)

    def test_internal_head_requires_prefix(self):
        with self.assertRaises(Rejected):
            validate_route(pr('feature/task', 'dinext/main/v3'), FORK, False)

    def test_double_prefix_rejected(self):
        with self.assertRaises(Rejected):
            validate_route(pr('dinext/dinext/feature/task', 'dinext/main/v3'), FORK, False)

    def test_unregistered_major_and_vendor_rejected(self):
        for target in ('dinext/main/v99', 'dinext/vendor/v3', 'dinext/main/v3/extra'):
            with self.subTest(target=target), self.assertRaises(Rejected):
                validate_route(pr('dinext/feature/task', target), FORK, False)

    def test_prefixed_frozen_branch_rejected(self):
        with self.assertRaises(Rejected):
            validate_route(pr('dinext/develope', 'dinext/main/v3'), FORK, False)

    def test_legacy_allowed_only_before_repository_transition(self):
        proposal = pr('dinext/feature/task', 'main/v3')
        proposal['base']['repo']['default_branch'] = 'main/v3'
        validate_route(proposal, FORK, False)
        proposal['base']['repo']['default_branch'] = 'dinext/main/v3'
        with self.assertRaises(Rejected):
            validate_route(proposal, FORK, False)

    def test_prefix_does_not_waive_runtime_or_ui_evidence(self):
        for label in ('Compatibility acceptance', 'Cypress acceptance'):
            evidence = [check('Compatibility acceptance'), check('Cypress acceptance')]
            for c in evidence:
                if c['name'] == label:
                    c['conclusion'] = 'skipped'
            self.assertTrue(validate_checks(['app/public/js/form.js'], FORK, evidence))

    def test_future_release_ref_format_and_historical_alias_separation(self):
        from prepare_release import validate_tag, historical_alias
        validate_tag('dinext/v3.4.0-dinext.1', False)
        validate_tag('dinext/v3.4.0', False)
        validate_tag('v26.10.20-01', True)
        for tag in ('v3.4.0', 'dinext/dinext/v3.4.0', 'dinext/v.2.2.2-dinext.1'):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                validate_tag(tag, False)
        import json
        from pathlib import Path
        aliases = json.loads(Path(__file__).with_name('historical-tag-aliases.json').read_text())
        for alias in aliases:
            self.assertEqual(historical_alias(alias['repository'], alias['old_tag'], alias['object_sha']), alias['alias'])
        with self.assertRaises(ValueError):
            historical_alias(aliases[0]['repository'], aliases[0]['old_tag'], '0' * 40)


if __name__ == '__main__':
    unittest.main()
