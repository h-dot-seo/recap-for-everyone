"""Narrow checked-in CI contract; not a YAML parser or runtime-success claim."""
import ast
import hashlib
import itertools
import re
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
# Exact pre-extension workflow: every existing trigger, pin, permission and step
# stays intact. This fixture intentionally fails on unrelated workflow changes.
BASELINE = 'name: Synthetic tests\non:\n  push:\n    branches: ["main", "codex/core-workflows-20261103"]\n  pull_request:\npermissions:\n  contents: read\njobs:\n  test:\n    runs-on: ${{ matrix.os }}\n    timeout-minutes: 10\n    strategy:\n      fail-fast: false\n      matrix:\n        os: [ubuntu-latest, windows-latest]\n        python: ["3.10", "3.12"]\n    steps:\n      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262\n        with:\n          persist-credentials: false\n      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065\n        with:\n          python-version: ${{ matrix.python }}\n      - run: python -m unittest discover -v\n      - run: python audit_publication.py\n      - run: python verify_manifest.py\n'
SH_FENCES = {'docs/INSTALL.md': '41c15fb0379791df44f9b873a5d88b3d514f84988564e2b06d9c518515cb10e5', 'docs/README.ko.md': '65b38235b8a7d9e128bc2f8bb3d08a936e7dff1e92d75732cfb6a24949008446', 'docs/WORKFLOWS.md': '6e4346365212f8410ee8a7e1c39c8abe830d4b3576c652af8c13a7a6b3c46c94'}


def matrix(text):
    # Only the checked-in compact scalar-list syntax is supported here. This is
    # deliberately not a general YAML parser (no additional dependency in CI).
    os_line=re.search(r'^        os: \[(.*?)\]$',text,re.M)
    py_line=re.search(r'^        python: (\[.*?\])$',text,re.M)
    if not os_line or not py_line:raise ValueError('missing compact matrix')
    systems=[value.strip() for value in os_line.group(1).split(',')]
    versions=ast.literal_eval(py_line.group(1))
    return list(itertools.product(systems,versions))


class CiContractTests(unittest.TestCase):
    def workflow(self):
        return (ROOT/'.github/workflows/tests.yml').read_text(encoding='utf-8')

    def test_six_jobs_preserve_four_existing_combinations(self):
        expected=set(itertools.product(['ubuntu-latest','windows-latest'],['3.10','3.12','3.15']))
        actual=matrix(self.workflow())
        self.assertEqual(len(actual),6);self.assertEqual(set(actual),expected)
        self.assertTrue(set(matrix(BASELINE))<=set(actual))

    def test_only_approved_workflow_changes(self):
        expected=BASELINE.replace('  pull_request:\n','  pull_request:\n  workflow_dispatch:\n').replace('["3.10", "3.12"]','["3.10", "3.12", "3.15"]')
        self.assertEqual(self.workflow(),expected)

    def test_pins_permissions_timeout_and_verification_gates(self):
        text=self.workflow()
        self.assertEqual(re.findall(r'uses: (.*)',text),[
            'actions/checkout@11d5960a326750d5838078e36cf38b85af677262',
            'actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065'])
        self.assertIn('permissions:\n  contents: read\n',text)
        self.assertIn('persist-credentials: false',text)
        self.assertIn('timeout-minutes: 10',text);self.assertIn('fail-fast: false',text)
        self.assertEqual(re.findall(r'- run: (.*)',text),[
            'python -m unittest discover -v','python audit_publication.py','python verify_manifest.py'])
        self.assertIn('branches: ["main", "codex/core-workflows-20261103"]',text)
        self.assertIn('  pull_request:\n  workflow_dispatch:\n',text)

    def test_documented_matrix_and_existing_shell_fences(self):
        for path,digest in SH_FENCES.items():
            raw=(ROOT/path).read_bytes();text=raw.decode('utf-8')
            self.assertEqual(hashlib.sha256(b''.join(re.findall(rb'```sh\n.*?```',raw,re.S))).hexdigest(),digest,path)
            for version in ('3.10','3.12','3.15'):self.assertIn(version,text,path)
            for system in ('Windows',):self.assertIn(system,text,path)
            self.assertIn('../VALIDATION.md',text,path)
            self.assertIn('6개' if path.endswith('README.ko.md') else 'six',text,path)
        self.assertIn('compatibility floor remains', (ROOT/'docs/INSTALL.md').read_text())
        self.assertIn('not a passing-run claim',(ROOT/'docs/WORKFLOWS.md').read_text())

    def test_matrix_oracle_detects_missing_and_duplicate_jobs(self):
        current=self.workflow()
        for changed in (current.replace(', "3.15"',''),current.replace('"3.15"','"3.12"')):
            self.assertNotEqual(set(matrix(changed)),set(matrix(current)))
        with self.assertRaises(ValueError):matrix('matrix: {}')


if __name__=='__main__':unittest.main()
