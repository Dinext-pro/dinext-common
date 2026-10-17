"""Check new public Dinext data without executing repository code or printing it."""
import base64,difflib,hashlib,html,json,os,re,subprocess,sys,urllib.parse,urllib.request,urllib.error
from pathlib import Path

EMAIL=re.compile(r'(?i)(?<!\w)[A-Z0-9_][A-Z0-9._%+-]{0,63}@[A-Z0-9](?:[A-Z0-9.-]*[A-Z0-9])?\.[A-Z]{2,24}\b')
OWNER=re.compile(r'["\x27](?:owner|modified_by)["\x27]\s*:\s*["\x27]([^"\x27\r\n]*)["\x27]')
PHONE=re.compile(r'(?<!\d)\+7[ (.-]*\d{3}[ ).-]*\d{3}[ .-]*\d{2}[ .-]*\d{2}(?!\d)')
ATTRIBUTION=re.compile(r'(?i)(copyright|SPDX|©|original author|upstream author|maintained by)')
SERVICE=re.compile(r'(?i)(\bFrom\b|Reply-To|reply_to|from_email|sender|mailbox|smtp|imap|отправител|адрес.*ответ)')
HASH=re.compile(r'^[0-9a-f]{40}$')
PRIVATE={'Dinext-pro/dinext-docs','Dinext-pro/dinext_control_center'}

class Guard:
 def __init__(self,root,private=None):
  self.root=Path(root).resolve();self.private=private or {};terms=self.private.get('terms',[])
  self.deny=re.compile(r'(?<!\w)(?:'+'|'.join(re.escape(t) for t in sorted(terms,key=len,reverse=True))+r')(?!\w)',re.I) if terms else re.compile(r'(?!)')
  self.issues=[];self.blobs={};self.trees={};self.metadata={}
  assets=Path(__file__).with_name('privacy-approved-assets.json')
  self.assets=set(json.loads(assets.read_text()).get('sha256',[])) if assets.exists() else set()
 def git(self,*args,check=True):
  env={**os.environ,'GIT_TERMINAL_PROMPT':'0','GIT_NO_LAZY_FETCH':'1','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':os.devnull,'GIT_LFS_SKIP_SMUDGE':'1'}
  env.pop('DINEXT_PRIVACY_DENYLIST',None)
  p=subprocess.run(['git','-c','core.hooksPath=/dev/null','-c','credential.helper=','-c','diff.external=','-C',str(self.root),*args],capture_output=True,env=env,timeout=240)
  if check and p.returncode:raise RuntimeError('Git data could not be verified; refresh the approved clean checkout')
  return p.stdout if check else p
 def report(self,category,path,line=None):
  # No original data, credentials or full identifiers enter logs.
  safe=self.deny.sub('Administrator',path)
  safe=''.join(c for c in safe if c.isprintable())[:240]
  self.issues.append({'category':category,'path':safe,'line':line})
 def allowed_email(self,value,line):
  value=value.casefold();local,_,domain=value.partition('@')
  if value in ['administrator@dinext.invalid','noreply@github.com','web-flow@users.noreply.github.com']:return True
  if domain.endswith(('.invalid','.example','.test')) or domain in ['example.com','example.org','example.net','test.com','localhost.localdomain']:return True
  if local=='git' and domain in ['github.com','gitlab.com','gitlab.dinext.ru','git.dinext.ru']:return True
  if domain in ['dinext.ru','dinext.pro'] and local in ['info','support','help','sales','noreply','no-reply','admin','billing','security','hello','bot']:return True
  if value in self.private.get('operational_mailboxes',[]) and SERVICE.search(line):return True
  return bool(ATTRIBUTION.search(line))
 def inspect_text(self,text,path,indices=None):
  for n,line in enumerate(text.splitlines(),1):
   if indices is not None and n-1 not in indices:continue
   line=html.unescape(urllib.parse.unquote(re.sub(r'\\u([0-9a-fA-F]{4})',lambda m:chr(int(m[1],16)),line)))
   if any(not('@' in m.group() and self.allowed_email(m.group(),line)) for m in self.deny.finditer(line)):self.report('personal_identifier_or_customer',path,n)
   if any(not self.allowed_email(m.group(),line) for m in EMAIL.finditer(line)):self.report('personal_email',path,n)
   if any(m[1] not in ['Administrator','Guest',''] for m in OWNER.finditer(line)):self.report('exported_user_metadata',path,n)
   if any(re.sub(r'\D','',m.group())!='70000000000' for m in PHONE.finditer(line)):self.report('personal_phone',path,n)
 def read(self,oid):
  if oid not in self.blobs:
   result=self.git('cat-file','blob',oid,check=False)
   if result.returncode:
    repository=os.environ['GITHUB_REPOSITORY']
    assert re.fullmatch(r'Dinext-pro/[A-Za-z0-9_.-]+',repository) and HASH.fullmatch(oid)
    headers={'Accept':'application/vnd.github.raw+json','X-GitHub-Api-Version':'2022-11-28'}
    if os.environ.get('GH_TOKEN'):headers['Authorization']='Bearer '+os.environ['GH_TOKEN']
    request=urllib.request.Request('https://api.github.com/repos/'+repository+'/git/blobs/'+oid,headers=headers)
    with urllib.request.urlopen(request,timeout=60) as response:
     data=response.read()
     if response.headers.get_content_type()=='application/json':data=base64.b64decode(json.loads(data)['content'])
    assert hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==oid
    self.blobs[oid]=data
   else:self.blobs[oid]=result.stdout
  return self.blobs[oid]
 def files(self,commit):
  if commit not in self.trees:
   result={}
   for row in self.git('ls-tree','-r','-z',commit).split(b'\0'):
    if not row:continue
    fields,path=row.split(b'\t',1);mode,kind,oid=fields.split()
    if kind==b'blob':result[path.decode('utf-8','surrogateescape')]=oid.decode()
   self.trees[commit]=result
  return self.trees[commit]
 def headers(self,commit):
  if commit not in self.metadata:
   header,message=self.git('cat-file','commit',commit).split(b'\n\n',1)
   self.metadata[commit]=(header.splitlines(),message)
  return self.metadata[commit]
 def ensure(self,oid,depth=256):
  assert HASH.fullmatch(oid)
  if self.git('cat-file','-e',oid+'^{commit}',check=False).returncode:
   self.git('fetch','--no-tags','--filter=blob:none','--depth='+str(depth),'origin',oid)
 def ancestor(self,a,b):return self.git('merge-base','--is-ancestor',a,b,check=False).returncode==0
 def choose_range(self,event):
  head=event.get('pull_request',{}).get('head',{}).get('sha') or os.environ['GITHUB_SHA']
  self.ensure(head)
  branch='refs/heads/'+event['pull_request']['base']['ref'] if 'pull_request' in event else os.environ.get('GITHUB_REF','')
  approved=json.loads(os.environ.get('DINEXT_PRIVACY_BASELINES') or '{}').get(branch)
  before=event.get('pull_request',{}).get('base',{}).get('sha') or event.get('before')
  choices=[v for v in [before,approved] if v and HASH.fullmatch(v) and v!='0'*40]
  for depth in [256,2048,10000]:
   for base in choices:
    self.ensure(base,depth)
    if self.ancestor(base,head):return base,head
   self.git('fetch','--no-tags','--filter=blob:none','--deepen='+str(depth),'origin',head)
  raise RuntimeError('No approved clean ancestor; maintainers must update the privacy baseline after review')
 def inherited(self,commits):
  output=self.git('ls-remote','--heads','origin','refs/heads/vendor/*').decode().splitlines()
  vendor=[row.split()[1] for row in output]
  if not vendor:return set()
  self.git('fetch','--no-tags','--filter=blob:none','--depth=512','origin',*['+'+v+':refs/remotes/privacy/'+v.removeprefix('refs/heads/') for v in vendor])
  refs=[r.decode() for r in self.git('for-each-ref','--format=%(refname)','refs/remotes/privacy/').splitlines()]
  return set(self.git('rev-list',*refs).decode().splitlines())&set(commits)
 def inspect_commit(self,oid,upstream):
  if oid in upstream:return
  headers,message=self.headers(oid);parents=[r[7:].decode() for r in headers if r.startswith(b'parent ')]
  for r in headers:
   if r.startswith((b'author ',b'committer ')):
    identity=r.split(b' ',1)[1]
    neutral=identity.startswith(b'Administrator <administrator@dinext.invalid> ')
    service=b'github-actions[bot]' in identity or b'noreply@github.com' in identity
    if not neutral and not service:self.report('own_git_identity_requires_administrator','[commit metadata]')
  self.inspect_text(message.decode('utf-8','replace'),'[commit message]')
  files=self.files(oid);parentfiles=[self.files(p) for p in parents]
  for path,blob in files.items():
   old=[p.get(path) for p in parentfiles]
   if blob in old:continue
   if self.deny.search(path):self.report('personal_path',path)
   data=self.read(blob)
   if b'\0' in data[:8192]:
    if hashlib.sha256(data).hexdigest() not in self.assets:self.report('new_binary_requires_private_review',path)
    continue
   try:text=data.decode('utf-8')
   except UnicodeDecodeError:self.report('new_legacy_encoding_requires_review',path);continue
   lines=text.splitlines();selected=set(range(len(lines)))
   for parent in old:
    if not parent:continue
    try:previous=self.read(parent).decode('utf-8').splitlines()
    except UnicodeDecodeError:continue
    for block in difflib.SequenceMatcher(None,previous,lines,autojunk=False).get_matching_blocks():selected.difference_update(range(block.b,block.b+block.size))
   self.inspect_text(text,path,selected)
 def run(self,event):
  base,head=self.choose_range(event)
  commits=self.git('rev-list','--reverse',base+'..'+head).decode().splitlines();inherited=self.inherited(commits)
  for commit in commits:self.inspect_commit(commit,inherited)
  for issue in self.issues[:50]:print(json.dumps({'privacy_issue':issue},ensure_ascii=False))
  print(json.dumps({'privacy_commits_checked':len(commits),'inherited_commits_preserved':len(inherited),'issues':len(self.issues),'source_values_logged':False}))
  return 1 if self.issues else 0

def main():
 if os.environ.get('GITHUB_REPOSITORY') in PRIVATE:
  print('Private repository: anonymization is excluded by owner policy.');return 0
 root=Path(sys.argv[1] if len(sys.argv)>1 else '.')
 event=json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
 raw=os.environ.pop('DINEXT_PRIVACY_DENYLIST','')
 private=json.loads(raw) if raw else {}
 try:return Guard(root,private).run(event)
 except (RuntimeError,ValueError,subprocess.SubprocessError,urllib.error.URLError):
  print('Privacy verification could not complete safely; a maintainer must review the clean baseline. No source values were logged.');return 1

if __name__=='__main__':raise SystemExit(main())
