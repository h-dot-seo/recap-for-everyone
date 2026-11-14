"""Synthetic outside-tree manifest generation, not release authorization."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build_manifest as build
from verify_manifest import verify


class BuildManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'tree'
        self.root.mkdir()
        self.output = self.root.parent / 'candidate.json'
        self.file = self.root / 'hello.txt'
        self.file.write_bytes(b'hello\n')
        self.meta = dict(project='synthetic', release='old', date='supplied text',
                         private_history_imported=False, actual_corpora_included=False,
                         synthetic_examples_only=True, license_status='NOT_SELECTED', custom={'keep': [1, True, None]})
        self.base = dict(self.meta, files=[self.row(self.file)], file_count=1)
        self.manifest = self.root / build.MANIFEST
        self.save_base()

    def row(self, path):
        raw = path.read_bytes()
        return dict(path=path.relative_to(self.root).as_posix(), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())

    def save_base(self):
        self.manifest.write_bytes((json.dumps(self.base, indent=2) + '\n').encode())

    def publish(self, **kwargs):
        plan = build.plan_manifest(self.root, **kwargs)
        receipt = build.build_manifest(self.root, self.output, plan['plan_sha256'], **kwargs)
        return plan, receipt, json.loads(self.output.read_bytes())

    def test_readonly_deterministic_plan_and_metadata_preserved(self):
        before = self.manifest.read_bytes()
        plan = build.plan_manifest(self.root)
        self.assertEqual(plan, build.plan_manifest(self.root))
        self.assertEqual(plan['added'], [])
        self.assertEqual(plan['removed'], [])
        self.assertEqual(plan['changed'], [])
        self.assertFalse(self.output.exists())
        self.assertEqual(before, self.manifest.read_bytes())
        _, receipt, candidate = self.publish()
        self.assertEqual(candidate, self.base)
        self.assertEqual(receipt['candidate_sha256'], hashlib.sha256(self.output.read_bytes()).hexdigest())
        self.assertEqual(verify(self.root, manifest=candidate), [])
        self.assertEqual(verify(self.root), [])
        self.assertEqual(before, self.manifest.read_bytes())
        self.assertEqual(self.output.read_bytes()[-1:], b'\n')
        self.assertEqual({k: candidate[k] for k in self.meta}, self.meta)
        self.assertNotIn('custom', plan)

    def test_add_remove_change_sorted_rows_and_counts(self):
        deleted=self.root/'removed.txt'; deleted.write_bytes(b'removed\n')
        self.base['files'].append(self.row(deleted)); self.base['file_count']=2; self.save_base()
        deleted.unlink()
        self.file.write_bytes(b'changed\n')
        (self.root/'z.txt').write_bytes(b'z\n')
        (self.root/'a.txt').write_bytes(b'a\n')
        plan, _, candidate=self.publish()
        self.assertEqual(plan['added'], ['a.txt', 'z.txt'])
        self.assertEqual(plan['removed'], ['removed.txt'])
        self.assertEqual(plan['changed'], ['hello.txt'])
        self.assertEqual((plan['added_count'],plan['removed_count'],plan['changed_count']), (2,1,1))
        self.assertEqual([row['path'] for row in candidate['files']], ['a.txt','hello.txt','z.txt'])
        self.assertEqual(verify(self.root,manifest=candidate), [])
        self.assertTrue(verify(self.root))

    def test_release_date_are_explicit_and_bound_to_plan(self):
        old = build.plan_manifest(self.root)
        plan, _, candidate=self.publish(release='new', date='supplied next')
        self.assertNotEqual(old['plan_sha256'],plan['plan_sha256'])
        self.assertEqual(candidate['release'],'new')
        self.assertEqual(candidate['date'],'supplied next')
        for key in set(self.meta)-{'release','date'}:
            self.assertEqual(candidate[key],self.meta[key])
        with self.assertRaises(ValueError):
            build.plan_manifest(self.root,release='')

    def test_supplied_metadata_cannot_bypass_publication_patterns(self):
        clean = build.plan_manifest(self.root)
        private = 'synthetic-contact' + '@' + 'example.invalid'
        for key in ('release', 'date'):
            with self.subTest(key=key), self.assertRaises(ValueError) as error:
                build.plan_manifest(self.root, **{key: private})
            self.assertNotIn(private, str(error.exception))
            with self.assertRaises(ValueError):
                build.build_manifest(self.root, self.output, clean['plan_sha256'], **{key: private})
            self.assertFalse(self.output.exists())

    def test_content_and_base_metadata_stale_even_same_paths(self):
        plan = build.plan_manifest(self.root)
        self.file.write_bytes(b'other\n')
        with self.assertRaises(ValueError):
            build.build_manifest(self.root,self.output,plan['plan_sha256'])
        self.assertFalse(self.output.exists())
        plan = build.plan_manifest(self.root)
        self.base['custom']['keep'].append('changed metadata'); self.save_base()
        with self.assertRaises(ValueError):
            build.build_manifest(self.root,self.output,plan['plan_sha256'])
        self.assertFalse(self.output.exists())

    def test_current_plan_rechecked_before_write(self):
        plan=build.plan_manifest(self.root)
        original=build._prepare
        calls=[]
        def changing(*args,**kwargs):
            value=original(*args,**kwargs)
            calls.append(1)
            if len(calls)==1:
                self.file.write_bytes(b'changed between checks\n')
            return value
        with patch.object(build,'_prepare',changing), self.assertRaises(ValueError):
            build.build_manifest(self.root,self.output,plan['plan_sha256'])
        self.assertFalse(self.output.exists())

    def test_exclusive_outside_tree_and_late_collision(self):
        plan=build.plan_manifest(self.root)
        for path in (self.root/'new.json',self.manifest,self.root):
            with self.assertRaises(ValueError): build.build_manifest(self.root,path,plan['plan_sha256'])
        self.output.write_bytes(b'keep\n')
        with self.assertRaises(FileExistsError): build.build_manifest(self.root,self.output,plan['plan_sha256'])
        self.assertEqual(self.output.read_bytes(),b'keep\n')
        self.output.unlink()
        publish=build._publish_new_file
        def race(path,raw,prefix):
            Path(path).write_bytes(b'race\n')
            return publish(path,raw,prefix)
        with patch.object(build,'_publish_new_file',race), self.assertRaises(FileExistsError):
            build.build_manifest(self.root,self.output,plan['plan_sha256'])
        self.assertEqual(self.output.read_bytes(),b'race\n')
        self.assertFalse(list(self.root.parent.glob('.recap-*')))

    def test_cr_and_publication_asset_and_pattern_gates(self):
        for raw in (b'a\r\nb', b'a\rb', b'\xff'):
            self.file.write_bytes(raw)
            with self.assertRaises(ValueError): build.plan_manifest(self.root)
        self.file.write_bytes(b'hello\n')
        for name in ('.env.local','archive.sqlite','private/secret.txt'):
            bad=self.root/name; bad.parent.mkdir(exist_ok=True); bad.write_bytes(b'synthetic\n')
            with self.assertRaises(ValueError): build.plan_manifest(self.root)
            bad.unlink()
            if bad.parent != self.root: bad.parent.rmdir()
        # Construct the synthetic matching pattern without embedding it verbatim.
        self.file.write_text('gh'+'p_'+'x'*32,encoding='utf-8')
        with self.assertRaises(ValueError): build.plan_manifest(self.root)

    def test_unsafe_windows_and_case_collisions(self):
        for name in ('NUL.txt','COM1.txt','LPT¹.txt','trailing.','space ','a:b','a\\b','../escape','/absolute','a//b'):
            self.assertFalse(build._safe_name(name),name)
        duplicate=copy.deepcopy(self.base)
        duplicate['files'].append(dict(duplicate['files'][0],path='HELLO.TXT'))
        duplicate['file_count']=2
        self.base=duplicate; self.save_base()
        with self.assertRaises(ValueError): build.plan_manifest(self.root)

    def test_symlink_special_and_cache_exclusions(self):
        cache=self.root/'__pycache__'; cache.mkdir(); (cache/'module.pyc').write_bytes(b'\x00\xff')
        self.assertEqual(build.plan_manifest(self.root)['file_count'],1)
        (cache/'not-cache.txt').write_bytes(b'private synthetic\n')
        with self.assertRaises(ValueError): build.plan_manifest(self.root)
        (cache/'not-cache.txt').unlink()
        link=self.root/'link.txt'
        try: link.symlink_to(self.file)
        except (OSError,NotImplementedError): pass
        else:
            with self.assertRaises(ValueError): build.plan_manifest(self.root)
            link.unlink()
        if hasattr(os,'mkfifo'):
            fifo=self.root/'fifo'; os.mkfifo(fifo)
            try:
                with self.assertRaises(ValueError): build.plan_manifest(self.root)
            finally: fifo.unlink()

    def test_audit_and_verifier_required_and_cli_arguments(self):
        with patch.object(build,'audit',return_value={'pass':False}), self.assertRaises(ValueError):
            build.plan_manifest(self.root)
        with patch.object(build,'verify',return_value=['synthetic failure']), self.assertRaises(ValueError):
            build.plan_manifest(self.root)
        import contextlib
        import io
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(build.main(['--root',str(self.root)]),0)
        self.assertEqual(json.loads(output.getvalue()),build.plan_manifest(self.root))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            build.main(['--root',str(self.root),'--write',str(self.output)])


if __name__ == '__main__':
    unittest.main()
