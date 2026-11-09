"""Release gates reject stale evidence and unauthorized immutable writes."""
import copy
import unittest
from release_policy import (Rejected, validate_version, validate_request, require_jobs,
                            inspect_release, verify_prechecks, inspect_postchecks, verify_tag)

SHA = 'a' * 40
TREE = 'b' * 40
TAG_OBJECT = 'c' * 40
OWN = {'own': True, 'branches': ['main', 'develop', 'release/*'],
       'mode': 'frappe-app', 'executed_checks': ['App unit tests']}
FORK = {'own': False, 'branches': ['dinext/main/v15'], 'mode': 'repository', 'executed_checks': []}
METADATA = {'full_name': 'Dinext-pro/app', 'private': False, 'archived': False}
ROOT = '/repos/Dinext-pro/app'

def request():
    return {'repository': 'Dinext-pro/app', 'branch': 'main', 'commit': SHA,
            'workflow_sha': SHA, 'version': 'v26.11.09-01', 'actor': 'russsik1',
            'triggering_actor': 'russsik1', 'run_id': 100, 'run_attempt': 1,
            'workflow_ref': 'Dinext-pro/app/.github/workflows/dinext-release.yml@refs/heads/main'}

def job(name, conclusion='success', jid=1):
    return {'id': jid, 'name': name, 'status': 'completed', 'conclusion': conclusion,
            'run_attempt': 1, 'head_sha': SHA, 'html_url': 'https://github.com/run/job/' + str(jid)}

class FixtureAPI:
    def __init__(self, data):
        self.data = data
        self.calls = []
    def request(self, method, path, data=None):
        self.calls.append((method, path, data))
        if method != 'GET':
            raise AssertionError('read-only release inspection attempted a write')
        if path not in self.data:
            raise AssertionError('unexpected request: ' + path)
        return copy.deepcopy(self.data[path])
    def pages(self, path, key=None):
        result = self.request('GET', path)
        return result[key] if key else result


def fixtures():
    pr = {'number': 7, 'merged_at': '2026-11-09T00:00:00Z', 'merge_commit_sha': SHA,
          'head': {'sha': 'd' * 40, 'ref': 'release/test', 'repo': {'full_name': 'Dinext-pro/app'}},
          'base': {'ref': 'main', 'repo': {'full_name': 'Dinext-pro/app'}}}
    return {ROOT: METADATA, ROOT + '/collaborators/russsik1/permission': {'role_name': 'maintain'},
            ROOT + '/commits/main': {'sha': SHA, 'commit': {'tree': {'sha': TREE}}},
            ROOT + '/git/matching-refs/tags/v26.11.09-01': [], ROOT + '/releases': [],
            ROOT + '/commits/' + SHA + '/pulls': [pr],
            ROOT + '/compare/' + 'd' * 40 + '...develop': {'status': 'ahead'},
            ROOT + '/actions/runs/100': {'head_sha': SHA, 'event': 'workflow_dispatch',
                                        'path': '.github/workflows/dinext-release.yml', 'run_attempt': 1},
            ROOT + '/actions/runs/100/jobs?filter=latest': {'jobs': [job('Validation / Repository checks'),
                                                        job('Validation / App unit tests', jid=2)]}}

class ReleasePolicyTests(unittest.TestCase):
    def test_calendar_versions(self):
        validate_version('v26.11.09-01', True)
        for bad in ['v26.02.30-01', 'v26.11.09-00', 'v2026.11.09-01', 'v26.11.09-1', 'v26.11.09-01\n']:
            with self.subTest(bad=bad), self.assertRaises(Rejected): validate_version(bad, True)

    def test_external_versions(self):
        for tag in ['dinext/v15.123.0', 'dinext/v15.123.0-dinext.2', 'dinext/3.0.0-beta.1']:
            validate_version(tag, False)
        for bad in ['v15.123.0', 'dinext/dinext/v1.0.0', 'dinext/v15.1.0-dinext.0', 'dinext/v1.0;echo']:
            with self.subTest(bad=bad), self.assertRaises(Rejected): validate_version(bad, False)

    def validate(self, **changes):
        r=request(); r.update(changes)
        validate_request(r['repository'], OWN, METADATA, r['branch'], r['commit'], r['workflow_sha'],
                         {r['actor']: 'maintain', r['triggering_actor']: 'maintain'})

    def test_authorized_exact_stable_sha(self): self.validate()

    def test_private_archived_and_other_org_rejected(self):
        for change in [{'private': True}, {'archived': True}, {'full_name': 'outsider/app'}]:
            with self.subTest(change=change), self.assertRaises(Rejected):
                validate_request('Dinext-pro/app', OWN, {**METADATA, **change}, 'main', SHA, SHA,
                                 {'russsik1': 'maintain'})

    def test_branch_and_workflow_revision_rejected(self):
        for change in [{'branch': 'develop'}, {'commit': 'short'}, {'workflow_sha': 'b'*40}]:
            with self.subTest(change=change), self.assertRaises(Rejected): self.validate(**change)

    def test_rerun_actor_must_be_authorized(self):
        with self.assertRaises(Rejected): self.validate(triggering_actor='another-maintainer')
        validate_request('Dinext-pro/app', OWN, METADATA, 'main', SHA, SHA, {'owner': 'admin'})

    def test_fork_line_must_be_reviewed(self):
        validate_request('Dinext-pro/app', FORK, METADATA, 'dinext/main/v15', SHA, SHA, {'owner': 'admin'})
        with self.assertRaises(Rejected):
            validate_request('Dinext-pro/app', FORK, METADATA, 'dinext/main/v16', SHA, SHA, {'owner':'admin'})

    def test_skipped_neutral_missing_or_failed_jobs_do_not_pass(self):
        for conclusion in ['skipped','neutral','failure','cancelled',None]:
            with self.subTest(conclusion=conclusion), self.assertRaises(Rejected):
                require_jobs([job('Validation / App unit tests', conclusion)], ['App unit tests'])
        with self.assertRaises(Rejected): require_jobs([], ['App unit tests'])

    def test_latest_failed_attempt_cannot_hide_behind_success(self):
        with self.assertRaises(Rejected):
            require_jobs([job('Validation / App unit tests', jid=1),
                          job('Validation / App unit tests', 'failure', jid=2)], ['App unit tests'])

    def test_pending_job_not_completed(self):
        pending={**job('App unit tests'), 'status':'in_progress'}
        with self.assertRaises(Rejected): require_jobs([pending], ['App unit tests'])

    def test_fully_qualified_job_names_match_exact_suffix(self):
        self.assertEqual(len(require_jobs([job('CI / Validation / App unit tests')], ['App unit tests'])),1)
        with self.assertRaises(Rejected): require_jobs([job('FakeApp unit tests')], ['App unit tests'])

    def test_preflight_is_read_only_and_records_accepted_pr(self):
        api=FixtureAPI(fixtures()); record=inspect_release(api, request(), {'app': OWN}, {'app': []})
        self.assertEqual((record['commit'],record['tree'],record['pull_request']), (SHA,TREE,7))
        self.assertFalse(any(c[0]!='GET' for c in api.calls))

    def test_unregistered_repository_fails_before_api(self):
        api=FixtureAPI({})
        with self.assertRaises(Rejected): inspect_release(api, request(), {}, {})
        self.assertEqual(api.calls,[])

    def test_moving_head_rejected(self):
        data=fixtures();data[ROOT+'/commits/main']['sha']='f'*40
        with self.assertRaises(Rejected):inspect_release(FixtureAPI(data),request(),{'app':OWN},{'app':[]})

    def test_unaccepted_merge_rejected(self):
        data=fixtures();data[ROOT+'/commits/'+SHA+'/pulls'][0]['head']['ref']='hotfix/bypass'
        with self.assertRaises(Rejected):inspect_release(FixtureAPI(data),request(),{'app':OWN},{'app':[]})

    def test_source_not_accepted_in_develop_rejected(self):
        data=fixtures();data[ROOT+'/compare/'+'d'*40+'...develop']['status']='diverged'
        with self.assertRaises(Rejected):inspect_release(FixtureAPI(data),request(),{'app':OWN},{'app':[]})

    def test_existing_tag_requires_recovery(self):
        data=fixtures();data[ROOT+'/git/matching-refs/tags/v26.11.09-01']=[{'ref':'refs/tags/v26.11.09-01'}]
        with self.assertRaises(Rejected):inspect_release(FixtureAPI(data),request(),{'app':OWN},{'app':[]})

    def test_prechecks_read_only_and_same_release_workflow(self):
        api=FixtureAPI(fixtures());record=inspect_release(api,request(),{'app':OWN},{'app':[]})
        self.assertEqual(len(verify_prechecks(api,record)),2)
        api.data[ROOT+'/actions/runs/100']['path']='.github/workflows/fake.yml'
        with self.assertRaises(Rejected):verify_prechecks(api,record)

    def test_acceptance_required_from_reviewed_profile(self):
        api=FixtureAPI(fixtures());record=inspect_release(api,request(),{'app':OWN},{'app':['Cypress acceptance']})
        with self.assertRaises(Rejected):verify_prechecks(api,record)

    def test_acceptance_profile_is_specific_to_stable_line(self):
        api=FixtureAPI(fixtures())
        record=inspect_release(api,request(),{'app':OWN},{'app':{'main':['Cypress acceptance']}})
        self.assertEqual(record['acceptance_checks'],['Cypress acceptance'])
        with self.assertRaises(Rejected):
            inspect_release(api,request(),{'app':OWN},{'app':{'other':[]}})

    def test_postchecks_require_exact_tag_event_sha_workflow(self):
        api=FixtureAPI(fixtures());record=inspect_release(api,request(),{'app':OWN},{'app':[]})
        path=ROOT+'/actions/workflows/dinext-validation.yml/runs?event=push&head_sha='+SHA
        api.data[path]={'workflow_runs':[{'id':200,'head_branch':record['version'],'head_sha':SHA,
             'event':'push','path':'.github/workflows/dinext-validation.yml','status':'completed','conclusion':'success'}]}
        api.data[ROOT+'/actions/runs/200/jobs?filter=latest']={'jobs':[job('Validation / Repository checks'),job('Validation / App unit tests',jid=2),job('Tag source context',jid=3)]}
        self.assertEqual(inspect_postchecks(api,record)['state'],'success')
        api.data[path]['workflow_runs'][0]['head_branch']='main'
        self.assertEqual(inspect_postchecks(api,record)['state'],'pending')

    def test_branch_with_same_name_cannot_impersonate_tag_push(self):
        api=FixtureAPI(fixtures());r=inspect_release(api,request(),{'app':OWN},{'app':[]})
        path=ROOT+'/actions/workflows/dinext-validation.yml/runs?event=push&head_sha='+SHA
        api.data[path]={'workflow_runs':[{'id':201,'head_branch':r['version'],'head_sha':SHA,
             'event':'push','path':'.github/workflows/dinext-validation.yml','status':'completed','conclusion':'success'}]}
        api.data[ROOT+'/actions/runs/201/jobs?filter=latest']={'jobs':[job('Validation / Repository checks'),
            job('Validation / App unit tests',jid=2),job('Tag source context','skipped',jid=3)]}
        self.assertEqual(inspect_postchecks(api,r)['state'],'pending')

    def test_tag_object_must_peel_to_exact_commit(self):
        r=request();api=FixtureAPI({ROOT+'/git/ref/tags/v26.11.09-01':{'object':{'type':'tag','sha':TAG_OBJECT}},
         ROOT+'/git/tags/'+TAG_OBJECT:{'object':{'type':'commit','sha':SHA,'url':'https://api.github.com/repos/Dinext-pro/app/git/commits/'+SHA},'tag':r['version'],'message':'proof'}})
        self.assertEqual(verify_tag(api,r)['object_sha'],TAG_OBJECT)
        api.data[ROOT+'/git/tags/'+TAG_OBJECT]['object']['sha']='f'*40
        with self.assertRaises(Rejected):verify_tag(api,r)

if __name__=='__main__':unittest.main()
