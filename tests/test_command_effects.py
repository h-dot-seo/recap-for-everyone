"""Real unified CLI effects on fictional DELETE-journal archives only.

This is not a promise about WAL/SHM sidecars, arbitrary filesystems or unhandled
failures. Successful commands must first produce valid JSON; only then are
complete scratch names/types/bytes compared, so refusal cannot pass vacuously.
"""
import contextlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import recap
from recaplib.command_catalog import describe
from recaplib.session_workflow import import_export, titles
from recaplib.title_suggestion import suggest
from recaplib.title_proposal import preview
from recaplib.title_plan import make_plan
from recaplib.title_transfer import dry_run, APPROVAL_SCHEMA
from recaplib.title_review_state import review_state
from recaplib.message_provenance import export_provenance
from recaplib.import_checkpoint import declare_checkpoint

ROOT=Path(__file__).resolve().parents[1]


def tree_bytes(root):
    """Include new/removed directories and every file, not just known inputs."""
    result={}
    for path in sorted(root.rglob('*')):
        name=path.relative_to(root).as_posix()
        if path.is_symlink():
            result[name]=('symlink',str(path.readlink()))
        elif path.is_dir():
            result[name]=('directory',None)
        elif path.is_file():
            result[name]=('file',path.read_bytes())
        else:
            result[name]=('special',None)
    return result


class CommandEffectsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.db=self.root/'archive.sqlite'
        self.web=self.copy('web-export.json')
        self.replay=self.copy('rollback-session.jsonl')
        self.attributed=self.copy('source-attributed-session.jsonl')
        self.unsupported=self.copy('local-session.jsonl')
        for source,path,kind in (('web',self.web,'web'),('replay',self.replay,'local-codex'),('attributed',self.attributed,'local-codex')):
            import_export(self.db,source,path,kind)
        titles(self.db,'web','synthetic-chat','Synthetic reviewed title',0)
        lease=review_state(self.db,'web','synthetic-chat')
        review_state(self.db,'web','synthetic-chat','skipped',lease['state_revision'],lease['expected_title_revision'],lease['expected_content_sha256'])
        proposal=suggest(self.db,'web','synthetic-chat')
        self.proposal=self.write('proposal.json',proposal)
        self.preview=self.write('preview.json',preview(self.db,proposal))
        plan=make_plan(self.db,'web','synthetic-chat',self.web,'web')
        self.plan=self.write('plan.json',plan)
        target=dict(provider='synthetic-mock',account_id='invented-account',conversation_id='separate-target-id',revision='opaque-v1',title='Mock old title')
        self.target=self.write('target.json',target)
        request=dry_run(self.db,self.web,plan,target)
        self.request=self.write('request.json',request)
        self.approval=self.write('approval.json',dict(schema=APPROVAL_SCHEMA,request_sha256=request['request_sha256'],approve=True))
        self.card=self.root/'card.json'
        export_provenance(self.db,'web','synthetic-chat','m1',self.card)
        self.cutoff=self.root/'cutoff.json'
        declare_checkpoint(self.db,'web',self.cutoff)
        self.zip=self.root/'web.zip'
        with zipfile.ZipFile(self.zip,'w',compression=zipfile.ZIP_STORED) as archive:
            archive.writestr('conversations.json',self.web.read_bytes())
        # Negative inputs are also prepared before the immutable baseline.
        changed=json.loads(self.web.read_bytes())
        changed[0]['mapping']['m1']['message']['content']['parts']=['Different synthetic content']
        self.conflict=self.write('conflict.json',changed)
        card=json.loads(self.card.read_bytes());card['text_sha256']='0'*64
        self.stale_card=self.write('stale-card.json',card)
        cutoff=json.loads(self.cutoff.read_bytes());cutoff['messages_sha256']='0'*64
        self.stale_cutoff=self.write('stale-cutoff.json',cutoff)
        connection=sqlite3.connect(self.db)
        try:
            self.assertEqual(connection.execute('PRAGMA journal_mode').fetchone()[0],'delete')
        finally:
            connection.close()
        self.common=['--source','web','--conversation','synthetic-chat']
        self.cases={
            'changed-since':['--source','web','--checkpoint',self.cutoff],
            'check-import':[self.web,'--source','web','--format','web'],
            'check-provenance':[self.card],
            'check-title-plan':[self.web,self.plan],
            'describe':[],
            'describe-schema':[],
            'export-title-plan':[self.web,'--format','web']+self.common,
            'find':['synthetic','--source','web'],
            'inspect':[self.web,'--format','web'],
            'inspect-web-zip':[self.zip],
            'list':['--source','web'],
            'list-export':[self.web,'--format','web'],
            'preview-title':[self.proposal],
            'replay-local':[self.replay],
            'review-state':self.common,
            'review-titles':['--source','web'],
            'search':['synthetic'],
            'show':self.common,
            'stats':[],
            'suggest-attributed-title':[self.attributed,'--source','attributed','--conversation','synthetic-attributed'],
            'suggest-branch-title':[self.web,'--node','m2']+self.common,
            'suggest-replay-title':[self.replay,'--source','replay','--conversation','synthetic-rollout'],
            'suggest-title':self.common,
            'title':self.common,
            'title-adapter-dry-run':[self.web,self.plan,self.target],
            'title-adapter-simulate':[self.web,self.request,self.approval,self.target],
            'title-history':self.common,
            'web-branch':[self.web,'--conversation','synthetic-chat','--node','m2'],
        }
        self.baseline=tree_bytes(self.root)

    def copy(self,name):
        path=self.root/name
        path.write_bytes((ROOT/'examples'/name).read_bytes())
        return path

    def write(self,name,value):
        path=self.root/name
        path.write_text(json.dumps(value,ensure_ascii=True)+'\n',encoding='utf-8')
        return path

    def invoke(self,command,args,expected_code=0):
        stdout,stderr=io.StringIO(),io.StringIO()
        code=0
        with patch.object(sys,'argv',['recap','--db',str(self.db),command]+[str(a) for a in args]),contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):
            try:
                recap.main()
            except SystemExit as error:
                code=error.code
        self.assertEqual(code,expected_code,(command,stderr.getvalue(),stdout.getvalue()))
        self.assertEqual(stderr.getvalue(),'')
        # Invalid JSON or empty stdout is a failed case, never read-only proof.
        result=json.loads(stdout.getvalue())
        self.assertIsInstance(result,(dict,list))
        return result

    def assert_readonly(self,command,args,expected_code=0):
        result=self.invoke(command,args,expected_code)
        self.assertEqual(tree_bytes(self.root),self.baseline,command)
        return result

    def test_complete_default_readonly_catalog_matrix(self):
        entries=describe(recap.build_parser())['commands']
        expected={entry['command'] for entry in entries if not entry['writes']['default']}
        self.assertEqual(expected,set(self.cases))
        self.assertEqual(len(expected),28)
        for command,args in self.cases.items():
            with self.subTest(command=command):
                result=self.assert_readonly(command,args)
                self.assertTrue(result,command)
                if command=='check-provenance':self.assertEqual(result['status'],'PASS')
                if command=='changed-since':self.assertEqual(result['status'],'CUTOFF_VERIFIED')
                if command=='check-import':self.assertFalse(result['conflicts_found'])
                if command=='check-title-plan':self.assertTrue(result['valid'])
                if command=='replay-local':self.assertTrue(result['supported'])
                if command.startswith('suggest-'):self.assertTrue(result['evidence_message_ids'])
                if command=='title-adapter-simulate':self.assertEqual(result['execution_status'],'SIMULATED_ONLY')

    def test_explicit_negative_results_exit_one_are_readonly(self):
        cases=[('check-import',[self.conflict,'--source','web','--format','web'],'conflicts_found',True),
               ('check-provenance',[self.stale_card],'status','STALE'),
               ('changed-since',['--source','web','--checkpoint',self.stale_cutoff],'status','CUTOFF_NOT_VERIFIED'),
               ('replay-local',[self.unsupported],'supported',False)]
        for command,args,key,expected in cases:
            with self.subTest(command=command):
                self.assertEqual(self.assert_readonly(command,args,1)[key],expected)

    def test_conditional_document_writes_only_one_new_file(self):
        entries=describe(recap.build_parser())['commands']
        expected={(entry['command'],condition['flag']) for entry in entries
                  for condition in entry['writes']['conditional'] if condition['flag']!='--set'}
        cases={(name,'--output') for name in ('show','suggest-title','suggest-branch-title','suggest-replay-title','suggest-attributed-title','preview-title','review-titles')}
        cases.add(('check-import','--delta-output'))
        self.assertEqual(cases,expected)
        for command,flag in sorted(cases):
            with self.subTest(command=command,flag=flag):
                output=self.root/'conditional.json'
                self.invoke(command,self.cases[command]+[flag,output])
                found=tree_bytes(self.root)
                self.assertEqual(set(found)-set(self.baseline),{'conditional.json'})
                self.assertEqual({k:v for k,v in found.items() if k!='conditional.json'},self.baseline)
                self.assertIsInstance(json.loads(output.read_bytes()),dict)
                output.unlink()

    def test_conditional_set_changes_only_existing_archive(self):
        entries=describe(recap.build_parser())['commands']
        expected={e['command'] for e in entries if any(c['flag']=='--set' for c in e['writes']['conditional'])}
        self.assertEqual(expected,{'title','review-state'})
        original=self.db.read_bytes()
        lease=review_state(self.db,'web','synthetic-chat')
        cases=[('title',self.common+['--set','New synthetic wording','--expected-revision',str(lease['expected_title_revision'])]),
               ('review-state',self.common+['--set','deferred','--expected-state-revision',str(lease['state_revision']),
                    '--expected-title-revision',str(lease['expected_title_revision']),'--expected-content-sha256',lease['expected_content_sha256']])]
        for command,args in cases:
            with self.subTest(command=command):
                self.invoke(command,args)
                found=tree_bytes(self.root)
                self.assertEqual(set(found),set(self.baseline))
                self.assertNotEqual(found['archive.sqlite'],self.baseline['archive.sqlite'])
                self.assertEqual({k:v for k,v in found.items() if k!='archive.sqlite'},
                                 {k:v for k,v in self.baseline.items() if k!='archive.sqlite'})
                # Every CLI/API connection has closed; reset only synthetic test bytes.
                self.db.write_bytes(original)

    def test_mutation_fault_exit_zero_is_detected(self):
        from recaplib import conversation_view
        original=conversation_view.conversations
        def mutate(*args,**kwargs):
            result=original(*args,**kwargs)
            (self.root/'unexpected.txt').write_bytes(b'synthetic mutation')
            return result
        with patch.object(conversation_view,'conversations',mutate):
            with self.assertRaises(AssertionError):
                self.assert_readonly('list',self.cases['list'])

    def test_existing_input_and_database_mutations_are_detected(self):
        from recaplib import conversation_view
        original=conversation_view.conversations
        for path in (self.web,self.db):
            raw=path.read_bytes()
            def mutate(*args,**kwargs):
                result=original(*args,**kwargs)
                path.write_bytes(raw+b'synthetic mutation')
                return result
            with self.subTest(path=path.name),patch.object(conversation_view,'conversations',mutate):
                with self.assertRaises(AssertionError):
                    self.assert_readonly('list',self.cases['list'])
            path.write_bytes(raw)
        self.assertEqual(tree_bytes(self.root),self.baseline)

    def test_failure_or_empty_success_cannot_pass_vacuously(self):
        from recaplib import conversation_view
        with patch.object(conversation_view,'conversations',side_effect=ValueError('synthetic refusal')):
            with self.assertRaises(AssertionError):
                self.assert_readonly('list',self.cases['list'])
        with patch.object(recap,'main',return_value=None):
            with self.assertRaises(json.JSONDecodeError):
                self.assert_readonly('list',self.cases['list'])
        self.assertEqual(tree_bytes(self.root),self.baseline)


if __name__=='__main__':
    unittest.main()
