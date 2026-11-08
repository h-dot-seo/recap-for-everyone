"""Synthetic advisory categories and explicit human wording, no secret corpus."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from recap import ingest
from session_workflow import titles
from title_suggestion import suggest
from title_proposal import preview, apply_preview
from title_review import assess_title


class TitleReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/'archive.sqlite';self.path=Path(self.tmp.name)/'synthetic.jsonl'
        self.address='invented'+'@'+'example.invalid'
        row=dict(conversation_id='synthetic',message_id='u',role='user',timestamp='synthetic',
                 text='Discuss synthetic contact '+self.address,title='New chat')
        self.path.write_text(json.dumps(row)+'\n');ingest(self.db,'demo',self.path)
        self.proposal=suggest(self.db,'demo','synthetic')

    def test_privacy_flags_are_categories_only_and_deterministic(self):
        cases=[(self.address,'EMAIL_LIKE'),('https://'+'example.invalid/path','URL_LIKE'),
               ('123 456 7890','LONG_DIGIT_SEQUENCE'),('A'*32,'LONG_IDENTIFIER_LIKE'),
               ('invented\u200b'+'@'+'example.invalid','FORMAT_CHARACTERS_PRESENT')]
        for text,expected in cases:
            result=assess_title(dict(title=text))
            self.assertIn(expected,result['privacy_flags']);self.assertNotIn(text,json.dumps(result))
            self.assertEqual(result,assess_title(dict(title=text)))
            self.assertFalse(result['matched_values_included'])
        safe=assess_title(dict(title='Synthetic orchard planning'))
        self.assertEqual(safe['privacy_flags'],[]);self.assertEqual(safe['assessment'],'HEURISTIC_ONLY')
        self.assertIn('not privacy clearance',safe['warning'])

    def test_length_and_generation_hints_are_explicit_not_verified_quality(self):
        result=assess_title(dict(title='검토 '*30,truncated=True,selection_method='first_user_greeting_fallback'))
        self.assertEqual(result['character_count'],90);self.assertEqual(result['maximum_characters'],200)
        self.assertEqual(result['quality_flags'],['OVER_LOCAL_EXCERPT_LENGTH','REPORTED_TRUNCATION','REPORTED_GREETING_FALLBACK'])
        self.assertFalse(result['generation_metadata_verified'])
        self.assertNotIn('score',result)
        self.assertEqual(assess_title(dict(title='합성',truncated='true'))['quality_flags'],[])
        with self.assertRaises(ValueError):assess_title(dict(title='x'*201))

    def test_replacement_preserves_binding_and_relabels_operator_without_old_metadata(self):
        original=copy.deepcopy(self.proposal);before=self.db.read_bytes()
        reviewed=preview(self.db,self.proposal,'Synthetic contact planning')
        self.assertEqual(self.proposal,original);self.assertEqual(before,self.db.read_bytes())
        replacement=reviewed['proposal']
        self.assertEqual(replacement['provider'],'operator')
        self.assertEqual(replacement['content_sha256'],original['content_sha256'])
        self.assertEqual(replacement['evidence_message_ids'],original['evidence_message_ids'])
        self.assertNotIn('selection_method',replacement);self.assertNotIn('truncated',replacement)
        self.assertEqual(reviewed['title_advisory']['privacy_flags'],[])
        apply_preview(self.db,reviewed)
        self.assertEqual(titles(self.db,'demo','synthetic')['display_title'],'Synthetic contact planning')
        self.assertIn(self.address,self.path.read_text())

    def test_replacement_cannot_bypass_original_validation_or_stale_review(self):
        for altered in (dict(self.proposal,content_sha256='0'*64),dict(self.proposal,evidence_message_ids=['missing']),
                        dict(self.proposal,provider='unconfigured')):
            with self.assertRaises(ValueError):preview(self.db,altered,'Synthetic replacement')
        for title in ('','x'*201,'line\nbreak'):
            with self.assertRaises(ValueError):preview(self.db,self.proposal,title)
        reviewed=preview(self.db,self.proposal,'Synthetic replacement')
        titles(self.db,'demo','synthetic','Newer title',0)
        with self.assertRaises(ValueError):apply_preview(self.db,reviewed)

    def test_advisories_do_not_claim_redaction_or_automatically_block_explicit_apply(self):
        before=self.db.read_bytes();reviewed=preview(self.db,self.proposal)
        self.assertIn('EMAIL_LIKE',reviewed['title_advisory']['privacy_flags'])
        self.assertEqual(before,self.db.read_bytes())
        reviewed['title_advisory']={'privacy_flags':[]}  # unsigned display hints are not an access control
        result=apply_preview(self.db,reviewed)
        self.assertEqual(result['display_title'],self.proposal['title'])

    def test_unicode_normalization_and_title_only_scan(self):
        result=assess_title(dict(title='ｗｗｗ．ｅｘａｍｐｌｅ．ｉｎｖａｌｉｄ'))
        self.assertIn('URL_LIKE',result['privacy_flags'])
        reviewed=preview(self.db,self.proposal,'Useful synthetic title')
        self.assertEqual(reviewed['title_advisory']['privacy_flags'],[])  # source contains synthetic address
        self.assertEqual(reviewed['title_advisory']['scanned_scope'],'proposed title only')

    def test_cli_queue_review_revise_apply_and_standalone_equivalence(self):
        def call(script,*args):
            result=subprocess.run([sys.executable,script,'--db',str(self.db),*map(str,args)],capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr);return json.loads(result.stdout)
        queue=call('recap.py','review-titles','--source','demo')
        self.assertIn('EMAIL_LIKE',queue['items'][0]['title_advisory']['privacy_flags'])
        saved=Path(self.tmp.name)/'queue.json';saved.write_text(json.dumps(queue))
        reviewed=call('recap.py','preview-title',saved,'--conversation','synthetic','--title','Synthetic contact plan')
        proposal=Path(self.tmp.name)/'proposal.json';proposal.write_text(json.dumps(self.proposal))
        standalone=call('title_proposal.py','preview',proposal,'--title','Synthetic contact plan')
        self.assertEqual(reviewed,standalone)
        saved.write_text(json.dumps(reviewed));call('recap.py','apply-title',saved)
        self.assertEqual(call('recap.py','title','--source','demo','--conversation','synthetic')['display_title'],'Synthetic contact plan')
        self.assertEqual(call('recap.py','find','invented')['total_matches'],1)
