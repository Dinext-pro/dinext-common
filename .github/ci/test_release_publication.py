"""Publication transactions preserve immutable refs and unpublished failures."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from release_policy import Rejected
from release_publication import create_tag, validate_origin, publish_release, verify_credential, main, validate_existing_release, prepare_content, release_assets
from test_release_policy import FixtureAPI, ROOT, SHA, TAG_OBJECT, TREE, request, job, fixtures, OWN
from release_policy import inspect_release, verify_prechecks

class WriterAPI(FixtureAPI):
    def request(self, method, path, data=None):
        if method=='POST':
            self.calls.append((method,path,data))
            return {'sha': TAG_OBJECT} if path.endswith('/git/tags') else {'ref':data['ref'],'object':{'sha':data['sha'],'type':'tag'}}
        return super().request(method,path,data)


def record():
    return {**request(),'schema_version':1,'tree':TREE,'own':True,'pull_request':7,
            'validation_checks':['Repository checks','App unit tests'],'acceptance_checks':[],
            'prepared_at':'2026-11-09T00:00:00+00:00'}

class PublicationTests(unittest.TestCase):
    def test_create_annotated_tag_only_after_prechecks_and_head_recheck(self):
        r=record();api=WriterAPI({ROOT+'/commits/main':{'sha':SHA}})
        with self.assertRaises(Rejected):create_tag(api,r,13,'f'*64,[])
        self.assertFalse(any(x[0]=='POST' for x in api.calls))
        evidence=[job('Repository checks'),job('App unit tests',jid=2)]
        receipt=create_tag(api,r,13,'f'*64,evidence)
        self.assertEqual(receipt['object_sha'],TAG_OBJECT)
        writes=[x for x in api.calls if x[0]=='POST']
        self.assertEqual([x[1] for x in writes],[ROOT+'/git/tags',ROOT+'/git/refs'])
        self.assertEqual(writes[0][2]['object'],SHA)
        self.assertEqual(writes[1][2]['ref'],'refs/tags/'+r['version'])
        self.assertEqual(json.loads(writes[0][2]['message'])['artifact_id'],13)

    def test_verified_precheck_record_can_authorize_tag_creation(self):
        api=WriterAPI(fixtures())
        r=inspect_release(api,request(),{'app':OWN},{'app':[]})
        evidence=verify_prechecks(api,r)
        self.assertEqual(create_tag(api,r,13,'f'*64,evidence)['object_sha'],TAG_OBJECT)

    def test_head_drift_prevents_tag_write(self):
        api=WriterAPI({ROOT+'/commits/main':{'sha':'f'*40}})
        with self.assertRaises(Rejected):create_tag(api,record(),13,'f'*64,[job('Repository checks'),job('App unit tests',jid=2)])
        self.assertFalse(any(x[0]=='POST' for x in api.calls))

    def test_origin_must_match_current_run_repo_sha_and_artifact(self):
        r=record();raw=json.dumps(r).encode()
        proof={'kind':'dinext-release-v1','run_id':100,'repository':r['repository'],'commit':SHA,
               'version':r['version'],'artifact_id':13,'sha256':hashlib.sha256(raw).hexdigest()}
        artifact={'id':13,'expired':False,'workflow_run':{'id':100,'head_sha':SHA}}
        self.assertEqual(validate_origin(r,proof,artifact,raw)['commit'],SHA)
        for change in [{'run_id':101},{'commit':'e'*40},{'repository':'Dinext-pro/foreign'}]:
            with self.subTest(change=change),self.assertRaises(Rejected):validate_origin(r,{**proof,**change},artifact,raw)
        with self.assertRaises(Rejected):validate_origin(r,proof,{**artifact,'expired':True},raw)
        with self.assertRaises(Rejected):validate_origin(r,proof,artifact,raw+b' ')

    def test_credential_requires_creation_bypass_and_immutable_safety(self):
        r=record()
        rules=[{'id':1,'name':'Dinext controlled tag creation','target':'tag','enforcement':'active'},
               {'id':2,'name':'Dinext immutable tags','target':'tag','enforcement':'active'}]
        api=FixtureAPI({ROOT+'/rulesets':rules,
           ROOT+'/rulesets/1':{'rules':[{'type':'creation'}],'bypass_actors':[{'actor_type':'Integration','actor_id':55,'bypass_mode':'always'}]},
           ROOT+'/rulesets/2':{'rules':[{'type':'update'},{'type':'deletion'}],'bypass_actors':[]}})
        verify_credential(api,r,55,[{'full_name':r['repository']}])
        api.data[ROOT+'/rulesets/1']['bypass_actors']=[]
        with self.assertRaises(Rejected):verify_credential(api,r,55,[{'full_name':r['repository']}])
        with self.assertRaises(Rejected):verify_credential(api,r,55,[{'full_name':'Dinext-pro/other'}])

    def test_runtime_app_can_verify_effective_bypass_without_admin_actor_list(self):
        r=record()
        rules=[{'id':1,'name':'Dinext controlled tag creation','target':'tag','enforcement':'active'},
               {'id':2,'name':'Dinext immutable tags','target':'tag','enforcement':'active'}]
        api=FixtureAPI({ROOT+'/rulesets':rules,
           ROOT+'/rulesets/1':{'rules':[{'type':'creation'}],'current_user_can_bypass':'always'},
           ROOT+'/rulesets/2':{'rules':[{'type':'update'},{'type':'deletion'}],'current_user_can_bypass':'never'}})
        verify_credential(api,r,55,[{'full_name':r['repository']}])
        api.data[ROOT+'/rulesets/2']['current_user_can_bypass']='always'
        with self.assertRaises(Rejected):verify_credential(api,r,55,[{'full_name':r['repository']}])

    def test_dry_run_rejects_skipped_required_job_before_activation(self):
        r=record(); data=fixtures()
        data[ROOT+'/actions/runs/100/jobs?filter=latest']['jobs'][1]['conclusion']='skipped'
        data[ROOT+'/rulesets']=[{'id':1,'name':'Dinext controlled tag creation','target':'tag','enforcement':'active'},
                              {'id':2,'name':'Dinext immutable tags','target':'tag','enforcement':'active'}]
        data[ROOT+'/rulesets/1']={'rules':[{'type':'creation'}],'bypass_actors':[{'actor_type':'Integration','actor_id':55,'bypass_mode':'always'}]}
        data[ROOT+'/rulesets/2']={'rules':[{'type':'update'},{'type':'deletion'}],'bypass_actors':[]}
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'preparation.json';path.write_text(json.dumps(r))
            with patch('sys.argv',['release','credential','--record',str(path)]), \
                 patch.dict(os.environ,{'GH_TOKEN':'fake','RELEASE_APP_ID':'55'}), \
                 patch('release_publication.GitHub',return_value=FixtureAPI(data)), \
                 patch('release_publication.request_from_environment',return_value=request()), \
                 patch('release_publication.registry_files',return_value=({'app':OWN},{'app':[]})), \
                 patch('release_publication.gh',return_value=json.dumps({'repositories':[{'full_name':r['repository']}]})):
                with self.assertRaisesRegex(Rejected,'Required job'):main()

    def test_own_draft_without_manifest_can_resume_but_foreign_draft_cannot(self):
        r=record(); marker='<!-- dinext-release:100:'+SHA+' -->'
        draft={'draft':True,'name':r['version'],'tag_name':r['version'],
               'body':'notes\n'+marker,'author':{'login':'dinext-release[bot]','type':'Bot'},'assets':[]}
        validate_existing_release(r,draft,'dinext-release')
        for change in [{'author':{'login':'someone','type':'User'}},{'body':'foreign draft'}, {'name':'unrelated'}]:
            with self.subTest(change=change),self.assertRaises(Rejected):
                validate_existing_release(r,{**draft,**change},'dinext-release')

    def test_notes_are_generated_before_tag_and_remain_frozen_on_retry(self):
        r=record();api=WriterAPI({})
        original_request=api.request
        def generate(method,path,data=None):
            if path==ROOT+'/releases/generate-notes':return {'body':'Native generated notes'}
            return original_request(method,path,data)
        api.request=generate
        content=prepare_content(api,r)
        self.assertEqual(content['release_notes'],'Native generated notes')
        api.request=lambda *args: self.fail('Retry must not regenerate notes')
        self.assertEqual(prepare_content(api,content),content)

    def test_release_assets_reject_notes_changed_after_creation(self):
        r=record()
        with tempfile.TemporaryDirectory() as d:
            notes=Path(d)/'notes.md';notes.write_text('frozen notes')
            asset=Path(d)/'release-manifest.json';asset.write_text('{}')
            data={ROOT+'/releases':[{'id':1,'name':r['version'],'tag_name':r['version'],'body':'tampered notes'}],
                  ROOT+'/releases/1/assets':[{'name':asset.name,'size':2,'digest':'sha256:'+hashlib.sha256(b'{}').hexdigest()}]}
            with self.assertRaises(Rejected):release_assets(FixtureAPI(data),r,[asset],notes)
            data[ROOT+'/releases'][0]['body']='frozen notes'
            self.assertEqual(release_assets(FixtureAPI(data),r,[asset],notes)['id'],1)

    def test_release_stays_draft_if_upload_fails(self):
        calls=[]
        def gh(args,**kwargs):
            calls.append(args)
            if args[:2]==['release','upload']:raise RuntimeError('upload failed')
            return ''
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'notes.md';p.write_text('Approved release notes')
            with self.assertRaises(RuntimeError):publish_release(gh,record(),p,[p],None)
        self.assertEqual(calls[0][:2],['release','create'])
        self.assertIn('--draft',calls[0]);self.assertIn('--verify-tag',calls[0])
        self.assertFalse(any(x[:2]==['release','edit'] for x in calls))

    def test_native_release_created_uploaded_verified_then_published(self):
        calls=[]
        def gh(args,**kwargs):calls.append(args);return ''
        def verify():calls.append(['verify-assets'])
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'notes.md';p.write_text('Approved release notes')
            publish_release(gh,record(),p,[p],verify)
        self.assertEqual([x[:2] for x in calls],[['release','create'],['release','upload'],['verify-assets'],['release','edit']])
        self.assertIn('--draft=false',calls[-1]);self.assertIn('--latest=true',calls[-1])
        self.assertIn('--notes-file',calls[0])

if __name__=='__main__':unittest.main()
