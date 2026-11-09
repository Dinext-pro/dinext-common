"""Consumer generation preserves CI events and isolates reusable concurrency."""
from pathlib import Path
import tempfile
import unittest
import yaml
from install_release_workflows import enable_release_events, release_caller, load_workflow

class WorkflowGenerationTests(unittest.TestCase):
    def test_protected_environment_key_is_explicitly_forwarded_only_to_writer(self):
        secret='DINEXT_RELEASE_APP_PRIVATE_KEY'
        publisher=load_workflow((Path(__file__).parents[1]/'workflows/dinext-release-publish.yml').read_text())
        contract=publisher['on']['workflow_call'].get('secrets',{})
        self.assertEqual(set(contract),{secret})
        self.assertTrue(contract[secret]['required'])
        caller=load_workflow(release_caller('a'*40,True))
        self.assertEqual(caller['jobs']['publish'].get('secrets'),{secret:'${{ secrets.'+secret+' }}'})
        for name,job in caller['jobs'].items():
            if name!='publish':self.assertNotIn('secrets',job)

    def test_preserves_branches_and_adds_call_and_tags(self):
        original="name: CI\n'on':\n  push:\n    branches: [main, develop]\n  pull_request: {}\n  workflow_dispatch: {}\npermissions:\n  contents: read\njobs: {}\n"
        text=enable_release_events(original)
        data=load_workflow(text)
        self.assertEqual(data['on']['push']['branches'],['main','develop'])
        self.assertEqual(data['on']['push']['tags'],['v*','dinext/**'])
        self.assertIn('workflow_call',data['on']);self.assertIn('pull_request',data['on'])
        self.assertEqual(enable_release_events(text),text)

    def test_acceptance_without_push_gains_tag_trigger(self):
        text=enable_release_events('name: Acceptance\non:\n  pull_request: {}\n  workflow_dispatch: {}\njobs: {}\n')
        self.assertIn('push',load_workflow(text)['on'])

    def test_existing_tag_patterns_are_not_removed(self):
        text=enable_release_events('on:\n  push:\n    tags: [old/*]\n  workflow_dispatch: {}\njobs: {}\n')
        self.assertIn('old/*',load_workflow(text)['on']['push']['tags'])

    def test_tag_source_job_is_gated_on_native_tag_context(self):
        text=enable_release_events('on:\n  push:\n    branches: [main]\njobs: {}\n')
        data=load_workflow(text)
        context=data['jobs']['release-context']
        self.assertEqual(context['name'],'Tag source context')
        self.assertIn("github.ref_type == 'tag'",context['if'])
        self.assertIn("github.event_name == 'push'",context['if'])

    def test_native_booleans_and_on_key(self):
        data=load_workflow('on: {}\nflag: false\n')
        self.assertEqual(data,{'on':{},'flag':False})

    def test_caller_waits_for_all_checks_and_defaults_to_dry_run(self):
        data=load_workflow(release_caller('a'*40,True))
        self.assertTrue(data['on']['workflow_dispatch']['inputs']['dry-run']['default'])
        self.assertEqual(set(data['jobs']['publish']['needs']),{'preflight','validation','acceptance'})
        self.assertEqual(data['jobs']['acceptance']['uses'],'./.github/workflows/dinext-acceptance.yml')
        self.assertFalse(data['concurrency']['cancel-in-progress'])
        self.assertEqual(data['permissions']['contents'],'read')

    def test_repository_without_acceptance_does_not_invent_job(self):
        data=load_workflow(release_caller('a'*40,False))
        self.assertNotIn('acceptance',data['jobs'])
        self.assertNotIn('acceptance',data['jobs']['publish']['needs'])

if __name__=='__main__':unittest.main()
