"""Mock-only title transfer contract. No network transport or credential support."""
from recaplib.errors import Stale
import copy
import hashlib
import json
import threading
from recaplib.title_plan import check_plan
from recaplib.title_rules import validate_title

REQUEST_SCHEMA = 'recap.title-transfer-request.v1'
APPROVAL_SCHEMA = 'recap.title-transfer-approval.v1'
TARGET_FIELDS = {'provider', 'account_id', 'conversation_id', 'revision', 'title'}


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'))


def _digest(value):
    return hashlib.sha256(_canonical(value).encode('ascii')).hexdigest()


def _target(value):
    if not isinstance(value, dict) or set(value) != TARGET_FIELDS:
        raise ValueError('target snapshot requires exactly provider, account_id, conversation_id, revision and title')
    if value['provider'] != 'synthetic-mock':
        raise ValueError('PROVIDER_NOT_CONFIGURED: only the in-memory synthetic mock is available')
    for key in ('account_id', 'conversation_id', 'revision'):
        item = value[key]
        if not isinstance(item, str) or not item.strip() or len(item) > 200 or any(ord(c) < 32 or ord(c) == 127 for c in item):
            raise ValueError('target identifiers and revision must be nonempty bounded strings without ASCII controls')
    validate_title(value['title'])
    return copy.deepcopy(value)


def dry_run(db, path, plan, target):
    """Recheck local evidence, then bind a separately supplied mock target snapshot."""
    check_plan(db, path, plan)
    target = _target(target)
    payload = dict(schema=REQUEST_SCHEMA, plan=copy.deepcopy(plan), target=target,
                   proposed_title=plan['proposed_title'],
                   action='no_change' if target['title'] == plan['proposed_title'] else 'rename',
                   execution_status='NOT_EXECUTED', remote_mutation=False,
                   target_verification='CALLER_SUPPLIED_SYNTHETIC_SNAPSHOT',
                   warning='PRIVATE METADATA. Mock only; no live identity verification or service authorization. Explicit approval must bind this complete request.')
    return dict(payload, request_sha256=_digest(payload))


class MockTitleAdapter:
    """One synthetic target, held in memory; atomic compare-and-set, never persisted."""
    def __init__(self, target):
        self._target = _target(target)
        self._lock = threading.Lock()

    def snapshot(self):
        with self._lock:
            return copy.deepcopy(self._target)

    def compare_and_set(self, expected, title):
        expected = _target(expected)
        validate_title(title)
        with self._lock:
            if _canonical(self._target) != _canonical(expected):
                raise Stale('MOCK_TARGET_STALE: target identity, title or revision changed')
            changed = title != self._target['title']
            if changed:
                # An opaque synthetic revision, not a real platform version/ETag.
                self._target = dict(self._target, title=title,
                                    revision='mock:' + _digest(dict(previous=self._target, title=title)))
            return copy.deepcopy(self._target), changed


def simulate(db, path, request, approval, adapter):
    """Explicit approval + fresh local check + mock target CAS; never real execution."""
    if type(adapter) is not MockTitleAdapter:
        raise ValueError('PROVIDER_NOT_CONFIGURED: only the built-in mock adapter is available')
    if not isinstance(request, dict) or request.get('schema') != REQUEST_SCHEMA:
        raise ValueError('unsupported title transfer request')
    if not isinstance(approval, dict) or set(approval) != {'schema', 'request_sha256', 'approve'}:
        raise ValueError('explicit request-bound approval required')
    if approval['schema'] != APPROVAL_SCHEMA or approval['approve'] is not True:
        raise ValueError('explicit approval must be boolean true')
    # Recreate the entire request; unknown fields, altered hashes and stale local
    # plan state all fail before touching mock state. No live service is contacted.
    current = dry_run(db, path, request.get('plan'), request.get('target'))
    if _canonical(current) != _canonical(request):
        raise Stale('transfer request is stale or altered; create and review a new dry run')
    if approval['request_sha256'] != current['request_sha256']:
        raise ValueError('approval does not match this exact transfer request')
    after, changed = adapter.compare_and_set(current['target'], current['proposed_title'])
    return dict(schema='recap.title-transfer-simulation.v1', request_sha256=current['request_sha256'],
                execution_status='SIMULATED_ONLY', remote_mutation=False,
                mock_state_changed=changed, target_after=after,
                warning='Ephemeral mock result only. No service was contacted or title changed remotely. Approval JSON is unsigned, not proof of human consent.')
