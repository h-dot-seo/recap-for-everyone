"""Validate externally supplied title proposals; this module calls no model."""
from recaplib.cli_errors import safe_diagnostic
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from recaplib.archive import readonly
from recaplib.session_workflow import titles
from recaplib.strict_json import loads
from recaplib.title_rules import validate_title
from recaplib.title_review import assess_title
from recaplib.conversation_view import _inventory
from recaplib.title_evidence import review_evidence
from recaplib.source_text import decode_source


def _freeze_document(value):
    """Detach a JSON document before validation or I/O, including nested metadata.

    This is a local value snapshot, not a signature or proof of human review.
    Never retain caller-owned mutable evidence lists or provider context.
    """
    try:
        return loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except (ValueError, TypeError, RecursionError):
        raise ValueError('title document must contain valid finite JSON data') from None


def read_document(path):
    """Read strict UTF-8 title JSON, tolerating one initial UTF-8 signature."""
    try:
        return loads(decode_source(Path(path).read_bytes()))
    except RecursionError:
        raise ValueError('title document nesting is too deep') from None


def content_fingerprint(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _validate_identity(source, conversation):
    if (not isinstance(source, str) or not source.strip() or
            not isinstance(conversation, str) or not conversation):
        raise ValueError('source and conversation must be nonempty text identities')


def _snapshot_rows(connection, source, conversation):
    rows = [dict(r) for r in connection.execute(
        'SELECT message_id,role,text FROM messages WHERE source_id=? AND conversation_id=? ORDER BY message_pk',
        (source, conversation))]
    if not rows:
        raise ValueError('unknown conversation')
    return rows, content_fingerprint(rows)


def snapshot(db, source, conversation):
    _validate_identity(source, conversation)
    c = readonly(db)
    try:
        return _snapshot_rows(c, source, conversation)
    finally:
        c.close()


def validate_against_snapshot(proposal, rows, digest):
    """Validate the proposal contract against already-read evidence, without I/O."""
    if not isinstance(proposal, dict):
        raise ValueError('title proposal must be a JSON object')
    if proposal.get('content_sha256') != digest:
        raise ValueError('proposal refers to a different conversation snapshot')
    title = proposal['title']
    validate_title(title)
    ids = proposal.get('evidence_message_ids')
    users = {r['message_id'] for r in rows if r['role'] == 'user'}
    if not isinstance(ids, list) or not ids or any(not isinstance(i, str) or i not in users for i in ids):
        raise ValueError('title evidence must reference user messages in this conversation')
    if proposal.get('provider') not in ('operator', 'external-adapter', 'synthetic-mock', 'local-extractive'):
        raise ValueError('explicit proposal provider required')


def preview(db, proposal, replacement_title=None, with_evidence=False):
    if type(with_evidence) is not bool:
        raise ValueError('with_evidence must be boolean')
    proposal = _freeze_document(proposal)
    if not isinstance(proposal, dict):
        raise ValueError('title proposal must be a JSON object')
    source, conversation = proposal['source'], proposal['conversation']
    _validate_identity(source, conversation)
    c = readonly(db)
    try:
        # Content, current title and optional evidence/provenance must agree,
        # including when another connection imports or renames during preview.
        c.execute('BEGIN')
        rows, digest = _snapshot_rows(c, source, conversation)
        validate_against_snapshot(proposal, rows, digest)
        ids = proposal['evidence_message_ids']
        if replacement_title is not None:
            validate_title(replacement_title)
            # Explicit human wording is not an extractive/model-generated label.
            # Keep only the checked identity/evidence contract.
            proposal = dict(source=source, conversation=conversation, content_sha256=digest,
                            title=replacement_title, evidence_message_ids=list(ids), provider='operator')
        current = _inventory(c, source, conversation, limit=1)[0]
        result = dict(proposal=proposal, title_advisory=assess_title(proposal), previous_title=current['display_title'], expected_revision=current['revision'],
                    semantic_validation='NOT_PERFORMED', remote_mutation=False)
        if with_evidence:
            result['review_evidence'] = review_evidence(c, proposal, rows, digest)
        return result
    finally:
        c.close()


def apply_preview(db, reviewed):
    reviewed = _freeze_document(reviewed)
    if not isinstance(reviewed, dict) or type(reviewed.get('expected_revision')) is not int or reviewed['expected_revision'] < 0:
        raise ValueError('reviewed preview requires a nonnegative integer expected_revision')
    proposal = reviewed['proposal']
    # Revalidate the content fingerprint immediately before writing the title.
    preview(db, proposal)
    return titles(db, proposal['source'], proposal['conversation'], proposal['title'], reviewed['expected_revision'], proposal['content_sha256'])


def main():
    from recaplib.title_document_output import add_output_argument, save_if_requested
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db', required=True)
    s = p.add_subparsers(dest='command', required=True)
    export = s.add_parser('snapshot'); export.add_argument('--source', required=True); export.add_argument('--conversation', required=True)
    for name in ('preview', 'apply'):
        command = s.add_parser(name); command.add_argument('input', type=Path)
        if name == 'preview':
            add_output_argument(command)
            command.add_argument('--title', help='explicit replacement title; reclassified as operator wording')
            command.add_argument('--with-evidence', action='store_true', help='include bounded raw user-message excerpts and provenance for private review')
    a = p.parse_args()
    try:
        if a.command == 'snapshot':
            rows, digest = snapshot(a.db, a.source, a.conversation)
            result = dict(source=a.source, conversation=a.conversation, content_sha256=digest, messages=rows,
                          warning='Private local content; no external transmission is performed')
        else:
            value = read_document(a.input)
            result = preview(a.db, value, a.title, a.with_evidence) if a.command == 'preview' else apply_preview(a.db, value)
        result = save_if_requested(result, a, 'preview')
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as e:
        p.exit(1, safe_diagnostic(e) + '\n')
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
