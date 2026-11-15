"""Static schema contract plus real consumer probes; not a schema validator."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from recaplib import rebuild

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / 'schemas' / 'recap.rebuild-plan.v1.schema.json'


def plan_fixture(kind='web', **overrides):
    """Fresh fictional plan, reusable by independent standards-validator checks."""
    step = dict(source='synthetic', kind=kind, object_sha256='a' * 64,
                label='synthetic' if kind in ('local', 'local-codex') else None,
                conversation=None, newline='lf')
    step.update(overrides)
    return {'schema': 'recap.rebuild-plan.v1', 'steps': [step]}


def structural_gap_fixtures():
    """Schema-shaped documents intentionally rejected by the real consumer."""
    return [plan_fixture(source=' \t\n'), plan_fixture('local', label=None),
            plan_fixture('local-codex', label=None),
            plan_fixture('normalized', label='synthetic'),
            plan_fixture('normalized', conversation='synthetic')]


class RebuildPlanSchemaTests(unittest.TestCase):
    def setUp(self):
        self.schema = json.loads(SCHEMA_PATH.read_text(encoding='utf-8'))

    def read(self, document, prefix=b''):
        raw = prefix + json.dumps(document, ensure_ascii=True).encode('ascii')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic-plan.json'
            path.write_bytes(raw)
            before = path.read_bytes()
            # A plan reader must not create/open an archive or mutate its input.
            with mock.patch.object(rebuild.sqlite3, 'connect', side_effect=AssertionError('DB access')):
                result = rebuild._read_plan(path)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(sorted(p.name for p in Path(directory).iterdir()), [path.name])
            self.assertEqual(result, (raw, document))
            return result

    def test_static_metadata_matches_runtime_constants(self):
        schema = self.schema
        self.assertEqual(schema['$schema'], 'https://json-schema.org/draft/2020-12/schema')
        self.assertEqual(schema['type'], 'object')
        self.assertIs(schema['additionalProperties'], False)
        self.assertEqual(set(schema['required']), {'schema', 'steps'})
        self.assertEqual(set(schema['properties']), {'schema', 'steps'})
        self.assertEqual(schema['properties']['schema'], {'const': rebuild.PLAN_SCHEMA})
        steps = schema['properties']['steps']
        self.assertEqual(steps['type'], 'array')
        self.assertEqual(steps['maxItems'], rebuild.MAX_STEPS)
        self.assertNotIn('minItems', steps)
        item = steps['items']
        self.assertEqual(item['type'], 'object')
        self.assertIs(item['additionalProperties'], False)
        self.assertEqual(set(item['required']), rebuild.STEP_FIELDS)
        self.assertEqual(set(item['properties']), rebuild.STEP_FIELDS)
        props = item['properties']
        self.assertEqual(props['source']['type'], 'string')
        self.assertEqual(props['source']['minLength'], 1)
        self.assertNotIn('maxLength', props['source'])
        for name, values in [('kind', ['normalized', 'web', 'local', 'local-codex']),
                             ('newline', ['lf', 'crlf'])]:
            self.assertEqual(props[name], {'type': 'string', 'enum': values})
        self.assertEqual(props['object_sha256']['type'], 'string')
        self.assertEqual(props['object_sha256']['pattern'], '^[0-9a-f]{64}$')
        self.assertEqual(props['object_sha256']['minLength'], 64)
        self.assertEqual(props['object_sha256']['maxLength'], 64)
        for name in ('label', 'conversation'):
            self.assertEqual(props[name]['type'], ['string', 'null'])
            self.assertEqual(props[name]['minLength'], 1)

    def test_no_references_or_conditional_runtime_claims(self):
        # Inspect the artifact's keyword inventory, not arbitrary instance validation.
        def keys(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    yield key
                    yield from keys(child)
            elif isinstance(value, list):
                for child in value:
                    yield from keys(child)
        names = set(keys(self.schema))
        self.assertFalse(names & {'$id', '$ref', '$dynamicRef', 'if', 'then', 'else',
                                  'allOf', 'anyOf', 'oneOf', 'format'})
        description = self.schema['description']
        for boundary in ('64 MiB', 'valid Unicode', 'nonblank', 'cross-field',
                         'manifest membership', 'not runtime admission or authorization'):
            self.assertIn(boundary, description)
        self.assertEqual(rebuild.MAX_PLAN_BYTES, 64 * 1024 * 1024)

    def test_valid_kinds_unicode_nullable_bom_and_empty(self):
        for kind in ('normalized', 'web', 'local', 'local-codex'):
            with self.subTest(kind=kind):
                self.read(plan_fixture(kind, source='합성 😀', newline='crlf'))
        self.read(plan_fixture('web', label='합성', conversation='대화 😀'))
        self.read(plan_fixture('web', label=' ', conversation=' '))
        self.read(plan_fixture(), prefix=b'\xef\xbb\xbf')
        self.read({'schema': rebuild.PLAN_SCHEMA, 'steps': []})
        self.read(plan_fixture(source='s' * 10000))

    def test_maximum_steps_inclusive(self):
        plan = plan_fixture()
        plan['steps'] *= rebuild.MAX_STEPS
        self.read(plan)
        plan['steps'].append(copy.deepcopy(plan['steps'][0]))
        with self.assertRaises(ValueError):
            self.read(plan)

    def test_exact_top_and_step_fields(self):
        base = plan_fixture()
        cases = [[], {}, {'schema': 'recap.rebuild-plan.v2', 'steps': []},
                 {'schema': rebuild.PLAN_SCHEMA, 'steps': {},},
                 {'schema': rebuild.PLAN_SCHEMA, 'steps': [None]}]
        for field in base:
            changed = copy.deepcopy(base)
            del changed[field]
            cases.append(changed)
        changed = copy.deepcopy(base)
        changed['extra'] = False
        cases.append(changed)
        for field in rebuild.STEP_FIELDS:
            changed = copy.deepcopy(base)
            del changed['steps'][0][field]
            cases.append(changed)
        changed = copy.deepcopy(base)
        changed['steps'][0]['extra'] = False
        cases.append(changed)
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.read(case)

    def test_scalar_shapes_and_hash_spelling(self):
        values = {
            'source': ['', None, False, 1, [], {}],
            'kind': ['other', None, False, 1, [], {}],
            'object_sha256': ['A' * 64, 'a' * 63, 'a' * 65, 'g' * 64,
                              'a' * 64 + '\n', None, False, 1, [], {}],
            'newline': ['LF', '', None, False, 1, [], {}],
            'label': ['', False, 1, 1.0, [], {}],
            'conversation': ['', False, 1, 1.0, [], {}],
        }
        for field, invalids in values.items():
            for value in invalids:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    self.read(plan_fixture(**{field: value}))

    def test_description_only_semantic_gaps(self):
        for plan in structural_gap_fixtures():
            with self.subTest(plan=plan), self.assertRaises(ValueError):
                self.read(plan)
        for field in ('source', 'label', 'conversation'):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.read(plan_fixture(**{field: '\ud800'}))
        # Structurally correct and reader-admitted does not mean declared membership.
        plan = plan_fixture()
        self.read(plan)
        manifest = {'schema': 'recap.recovery-manifest.v1', 'artifacts': [], 'sources': []}
        with self.assertRaisesRegex(ValueError, 'not declared'):
            rebuild._declared_steps(plan, manifest)

    def test_byte_budget_is_consumer_not_character_constraint(self):
        plan = plan_fixture(source='合成')
        raw = json.dumps(plan, ensure_ascii=False).encode('utf-8')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.json'
            path.write_bytes(raw)
            with mock.patch.object(rebuild, 'MAX_PLAN_BYTES', len(raw)):
                self.assertEqual(rebuild._read_plan(path), (raw, plan))
            with mock.patch.object(rebuild, 'MAX_PLAN_BYTES', len(raw) - 1):
                with self.assertRaisesRegex(ValueError, 'byte limit'):
                    rebuild._read_plan(path)
            self.assertEqual(path.read_bytes(), raw)


if __name__ == '__main__':
    unittest.main()
