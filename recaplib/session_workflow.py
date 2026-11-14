"""Explicit export adapters and reversible local title organization (no network)."""
from recaplib.errors import add_json_errors_argument, exit_error
from recaplib.errors import SourceChanged, Stale, UnknownIdentity
from recaplib.cli_errors import safe_diagnostic
import argparse
import hashlib
import json
import math
import sqlite3
from contextlib import closing
from collections import Counter
from pathlib import Path
from recaplib.local_parser import parse_jsonl_bytes
from recaplib.archive import _validate_source, ingest_bytes, readonly, _ingest_adapter_rows
from recaplib.archive import _normalized_bytes as _serialize_normalized_rows
from recaplib.strict_json import loads
from recaplib.title_rules import validate_title
from recaplib.title_excerpt import excerpt
from recaplib.source_text import BOM_UTF8, decode_source
from recaplib.source_identity import aliased_identity


def _validate_mapping(mapping):
    for node_id, node in mapping.items():
        if not isinstance(node_id, str) or not node_id or not isinstance(node, dict):
            raise ValueError('mapping nodes require nonempty IDs and object values')
        parent = node.get('parent')
        if parent is not None and (not isinstance(parent, str) or parent not in mapping):
            raise ValueError('mapping parent must reference an existing node')
    # Iterative parent walks avoid recursion limits on long, valid conversations.
    complete = set()
    for node_id in mapping:
        path = set()
        current = node_id
        while current is not None and current not in complete:
            if current in path:
                raise ValueError('mapping parent graph must not contain cycles')
            path.add(current)
            current = mapping[current].get('parent')
        complete.update(path)



def _web_text(content, coverage):
    """Explicit text-bearing shapes only; never stringify attachment metadata."""
    kind = content.get('content_type')
    # Missing tags retain the parts-based compatibility path. A malformed
    # supplied discriminator must not silently erase a text-field request.
    if 'content_type' in content and (not isinstance(kind, str) or not kind.strip()):
        raise ValueError('message content_type must be nonempty text')
    if kind in ('code', 'execution_output'):
        text = content.get('text')
        if not isinstance(text, str):
            raise ValueError('code and execution_output content require text')
        if 'parts' in content:
            raise ValueError('text-field content must not also contain parts')
        coverage['text_field_messages'] += 1
        return text
    parts = content.get('parts', [])
    if not isinstance(parts, list):
        raise ValueError('message content parts must be an array')
    coverage['nontext_parts_skipped'] += sum(not isinstance(part, str) for part in parts)
    if 'text' in content:
        coverage['unsupported_text_fields'] += 1
    return '\n'.join(part for part in parts if isinstance(part, str))


def _read_export_bytes(path, expected_export_sha256=None):
    if expected_export_sha256 is not None and (not isinstance(expected_export_sha256, str) or
            len(expected_export_sha256) != 64 or any(ch not in '0123456789abcdef' for ch in expected_export_sha256)):
        raise ValueError('expected export hash must be a lowercase SHA-256 hex digest')
    raw = Path(path).read_bytes()
    if expected_export_sha256 is not None and hashlib.sha256(raw).hexdigest() != expected_export_sha256:
        raise SourceChanged('export changed after inspection; inspect and select again')
    return raw


def normalize(path, kind, include_report=False, conversation=None, expected_export_sha256=None, *, _topology=None):
    path = Path(path)
    raw = _read_export_bytes(path, expected_export_sha256)
    rows, report = _normalize_selected_bytes(raw, path.name, kind, conversation, _topology)
    if expected_export_sha256 is not None:
        # Preserve the path API's historical JSON key order as well as values.
        selection = report.pop('selection', None)
        report['expected_export_sha256'] = expected_export_sha256
        if selection is not None:
            report['selection'] = selection
    return (rows, report) if include_report else rows


def _normalize_selected_bytes(raw, label, kind, conversation=None, topology=None):
    collected=[] if topology is not None or conversation is not None else None
    rows, report = _normalize_bytes(raw, label, kind, include_report=True, _topology=collected)
    if conversation is not None:
        if not isinstance(conversation, str) or not conversation:
            raise ValueError('selected conversation must be a nonempty string')
        if kind == 'web':
            # Reuse topology from the same decode, not a second parse/read. Selecting
            # one identity must not silently combine duplicate export records.
            matches = sum(record['conversation']==conversation for record in collected)
            if matches != 1:
                raise ValueError('selected conversation must identify exactly one web export record')
        selected = [row for row in rows if row['conversation_id'] == conversation]
        if not selected:
            raise ValueError('no extracted messages for selected conversation; inspect the full export')
        report['selection'] = dict(conversation=conversation, selected_messages=len(selected),
                                  excluded_messages=len(rows)-len(selected),
                                  selected_role_counts=dict(sorted(Counter(row['role'] for row in selected).items())),
                                  coverage_scope='all other coverage counts and warnings describe the entire input file',
                                  policy='only this conversation; preserve all extracted branches or raw local records')
        rows = selected
    if topology is not None:
        topology.extend(record for record in collected if conversation is None or record['conversation']==conversation)
    return rows, report


def _normalize_bytes(raw, source_name, kind, include_report=False, *, _topology=None):
    digest = hashlib.sha256(raw).hexdigest()
    rows = []
    report = dict(format=kind, original_sha256=digest, original_bytes=len(raw))
    if raw.startswith(BOM_UTF8):
        report['utf8_bom_present'] = True
    if kind in ('local', 'local-codex'):
        # Parse the already-hashed snapshot directly: inspection and scoped title
        # reads must not need a second plaintext file in the temporary directory.
        parsed = parse_jsonl_bytes(raw, source_name, content_profile='codex' if kind == 'local-codex' else 'legacy')
        report.update(local_content_profile='codex' if kind == 'local-codex' else 'legacy',
                      skipped_content_parts=parsed.skipped_content_parts,
                      rollout_context=dict(parsed.context_counts),
                      messages_without_explicit_id=sum(not m.explicit_id for m in parsed.messages),
                      effective_history_reconstructed=False,
                      observed_records=parsed.observed_record_count,
                      sessions_in_metadata=len({session.session_id for session in parsed.sessions}),
                      parser_admission_status=parsed.admission_status, reason_code=parsed.reason_code,
                      records_without_extracted_message=parsed.observed_record_count - len(parsed.messages))
        for m in parsed.messages:
            rows.append(dict(conversation_id=m.session_id, message_id=m.message_key,
                             role=m.role, timestamp=m.timestamp_utc or 'unknown', text=m.text,
                             origin_locator=f'line:{m.line_number}'))
    elif kind == 'web':
        data = loads(decode_source(raw))
        if not isinstance(data, list):
            raise ValueError('web export must be an array of conversations with mapping nodes')
        report.update(conversations_in_export=len(data), mapping_nodes=0,
                      text_field_messages=0, nontext_parts_skipped=0,
                      unsupported_text_fields=0, forked_conversations=0,
                      branch_policy='all mapping nodes in export order; current_node is not selected')
        for conv in data:
            if not isinstance(conv, dict) or not isinstance(conv.get('mapping'), dict):
                raise ValueError('conversation must contain a mapping object')
            cid = aliased_identity(conv, 'conversation_id')
            if conv.get('title') is not None and not isinstance(conv['title'], str):
                raise ValueError('conversation title must be text or null')
            _validate_mapping(conv['mapping'])
            if _topology is not None:
                pointer=conv.get('current_node')
                valid=isinstance(pointer,str) and bool(pointer) and pointer in conv['mapping']
                _topology.append(dict(conversation=cid,original_hash=digest,current_node=pointer if valid else None,
                    current_node_state='valid' if valid else ('absent' if 'current_node' not in conv else 'invalid'),
                    nodes=[(node_id,node.get('parent'),ordinal) for ordinal,(node_id,node) in enumerate(conv['mapping'].items())]))
            report['mapping_nodes'] += len(conv['mapping'])
            children = Counter(node.get('parent') for node in conv['mapping'].values()
                               if node.get('parent') is not None)
            report['forked_conversations'] += int(any(count > 1 for count in children.values()))
            for node_id, node in conv['mapping'].items():
                m = node.get('message')
                if m is None:
                    continue
                if not isinstance(m, dict) or not isinstance(m.get('content'), dict):
                    raise ValueError('message content must be an object')
                author = m.get('author')
                if not isinstance(author, dict) or author.get('role') not in ('user', 'assistant', 'system', 'tool'):
                    raise ValueError('message author must contain a supported role')
                timestamp = m.get('create_time')
                if timestamp is not None and (timestamp == '' or isinstance(timestamp, bool) or
                        not isinstance(timestamp, (str, int, float)) or
                        isinstance(timestamp, float) and not math.isfinite(timestamp)):
                    raise ValueError('message create_time must be text or a finite number')
                text = _web_text(m['content'], report)
                if not text.strip():
                    continue
                rows.append(dict(conversation_id=cid, message_id=node_id,
                                 role=author['role'], timestamp='unknown' if timestamp is None else str(timestamp),
                                 text=text, title=conv.get('title') or '',
                                 parent_id=node.get('parent'), origin_locator=f'mapping:{node_id}'))
    else:
        raise ValueError('unsupported format')
    if _topology is not None:
        # Exact extracted-row membership, not raw content/parts presence. The
        # original hash plus node identifies text retained from this export.
        text_nodes={(row['conversation_id'],row['message_id']) for row in rows}
        for graph in _topology:
            graph['nodes']=[(node,parent,ordinal,int((graph['conversation'],node) in text_nodes))
                            for node,parent,ordinal in graph['nodes']]
    for row in rows:
        row['origin_sha256'] = digest
    report.update(extracted_messages=len(rows),
                  conversations_with_text=len({row['conversation_id'] for row in rows}),
                  role_counts=dict(sorted(Counter(row['role'] for row in rows).items())),
                  contains_message_text=False,
                  limitations='Text extraction only; nontext content is not extracted. Counts do not establish completeness.')
    if kind == 'web':
        report['nodes_without_extracted_text'] = report['mapping_nodes'] - len(rows)
    report['warnings'] = ['No messages extracted; inspect the supported format and source before importing.'] if not rows else []
    if kind in ('local', 'local-codex'):
        context = report['rollout_context']
        if context.get('compacted_records') or context.get('rollback_events'):
            report['warnings'].append('Compaction or rollback markers are present; archived text is raw record order, not effective replay history.')
        if any(context.get(key) for key in ('fork_metadata_records', 'referenced_history_records', 'parent_thread_records', 'paginated_history_records')):
            report['warnings'].append('Fork, parent or paginated history metadata is present; inherited history is not resolved and may be incomplete.')
        if any(context.get(key) for key in ('event_msg_records', 'nonmessage_response_items', 'skipped_role_messages', 'other_records')):
            report['warnings'].append('Some event, nonmessage, unsupported-role or unknown records are not extracted as messages.')
        if report['messages_without_explicit_id']:
            report['warnings'].append('Some message IDs depend on source basename and line number; renaming or rearranging the export changes those identities.')
        if context.get('content_attribution_records'):
            report['warnings'].append('Per-content source metadata is present but raw imports do not filter by it; inspect the source-attributed title workflow when supported. Presence does not establish valid or authenticated attribution.')
    if kind == 'local-codex' and report['skipped_content_parts']:
        report['warnings'].append('Nontext or unsupported local content parts were not extracted.')
    if kind == 'web':
        if report['forked_conversations']:
            report['warnings'].append('Forked conversations include all branches; title suggestions may mix alternate paths.')
        if report['unsupported_text_fields']:
            report['warnings'].append('Unsupported text fields were not extracted.')
    return (rows, report) if include_report else rows


def inspect_normalized(path, conversation=None, expected_export_sha256=None):
    # Deliberately separate from normalize/_normalize_bytes: import and title
    # plans must not acquire a new format through a shared dispatcher.
    from recaplib.archive import validate_normalized
    if conversation is not None:
        raise ValueError('normalized format does not support conversation selection')
    raw = _read_export_bytes(path, expected_export_sha256)
    records, report = validate_normalized(raw)
    if expected_export_sha256 is not None:
        report['expected_export_sha256'] = expected_export_sha256
    return [row for row, _, _ in records], report


def inspect_export(path, kind, conversation=None, expected_export_sha256=None):
    if kind == 'normalized':
        _, report = inspect_normalized(path, conversation, expected_export_sha256)
    else:
        _, report = normalize(path, kind, include_report=True, conversation=conversation,
                              expected_export_sha256=expected_export_sha256)
    return dict(report, mode='inspection only; no database access')


def _normalized_bytes(rows, newline=None):
    # Compatibility helper retains exact historical serialization for callers.
    return _serialize_normalized_rows(rows, newline)


def _origin_report(report):
    return dict(format=report['format'],original_sha256=report['original_sha256'],original_bytes=report['original_bytes'],
                selected_conversation=report.get('selection',{}).get('conversation',''))


def import_export(db, source, path, kind, conversation=None, expected_export_sha256=None):
    _validate_source(source)
    topology=[] if kind=='web' else None
    rows, report = normalize(path, kind, include_report=True, conversation=conversation,
                             expected_export_sha256=expected_export_sha256, _topology=topology)
    # Keep original hash/locator/branch metadata in companion provenance tables.
    result = _ingest_adapter_rows(db, source, rows, topology=topology, origin=_origin_report(report))
    result['coverage'] = report
    return result


def import_export_bytes(db, source, raw, label, kind, conversation=None, *, newline):
    """Replay supplied export bytes with explicit label and LF/CRLF serialization.

    Writes the selected archive using normal import transactions. This is not an
    exclusive new-DB/rebuild wrapper and does not read any input path. The caller
    owns object-hash authorization and must supply the original parsing label.
    """
    _validate_source(source)
    if not isinstance(raw, bytes):
        raise ValueError('export input must be immutable bytes')
    if newline not in ('lf', 'crlf'):
        raise ValueError('replay newline must be lf or crlf')
    if kind not in ('web', 'local', 'local-codex'):
        raise ValueError('unsupported format')
    if label is None and kind == 'web':
        parser_label = ''
    else:
        if not isinstance(label, str) or not label:
            raise ValueError('replay label must be nonempty text for local exports')
        try:
            label.encode('utf-8')
        except UnicodeEncodeError:
            raise ValueError('replay label must contain valid Unicode text') from None
        parser_label = label
    topology=[] if kind=='web' else None
    rows, report = _normalize_selected_bytes(raw, parser_label, kind, conversation, topology)
    result = _ingest_adapter_rows(db, source, rows, newline='\n' if newline == 'lf' else '\r\n', topology=topology, origin=_origin_report(report))
    result['coverage'] = report
    # Do not echo the potentially private label or selection in this new block.
    # Existing coverage selection fields retain the import API's prior contract.
    result['replay'] = dict(newline=newline, label_supplied=label is not None,
                            input='supplied immutable export bytes',
                            recovery_verified='NOT_ESTABLISHED',
                            boundary='Import only; no exclusive database creation, replay-plan authorization, '
                                     'title/review recovery or remote backup verification.')
    return result


def titles(db, source, conversation, title=None, expected_revision=None, expected_content_sha256=None):
    # Keep exact text identities: SQLite affinity must not turn booleans/numbers
    # supplied by Python callers into a different conversation's text key.
    _validate_source(source)
    if not isinstance(conversation, str) or not conversation:
        raise ValueError('conversation must be nonempty text')
    if any(0xd800 <= ord(character) <= 0xdfff for character in conversation):
        raise ValueError('conversation must contain valid Unicode text')
    # None remains the documented lower-level API compatibility option. A
    # supplied guard is an exact revision, not Python's bool/float equality.
    if expected_revision is not None and (type(expected_revision) is not int or expected_revision < 0):
        raise ValueError('expected revision must be a nonnegative integer or None')
    if title is not None:
        validate_title(title)
    c = readonly(db) if title is None else sqlite3.connect(Path(db).resolve().as_uri() + '?mode=rw', uri=True)
    try:
        if title is not None:
            c.execute('BEGIN IMMEDIATE')
        else:
            c.execute('BEGIN')
        if expected_content_sha256 is not None:
            content = [dict(zip(('message_id','role','text'), r)) for r in c.execute(
                'SELECT message_id,role,text FROM messages WHERE source_id=? AND conversation_id=? ORDER BY message_pk', (source, conversation))]
            digest = hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            if digest != expected_content_sha256:
                raise Stale('conversation changed after proposal generation')
        messages = c.execute('SELECT role,text,title,message_id FROM messages WHERE source_id=? AND conversation_id=? ORDER BY message_pk', (source, conversation)).fetchall()
        if not messages:
            raise UnknownIdentity('unknown conversation')
        try:
            suggestion = excerpt([dict(role=m[0], text=m[1], message_id=m[3]) for m in messages])['title']
        except ValueError:
            # Informational title reads still work without usable user evidence.
            # Proposal generation remains stricter and never invents evidence.
            suggestion = 'Untitled conversation'
        exists = c.execute("SELECT 1 FROM sqlite_master WHERE name='title_history'").fetchone()
        history = c.execute('SELECT title,id FROM title_history WHERE source=? AND conversation=? ORDER BY id', (source, conversation)).fetchall() if exists else []
        revision = history[-1][1] if history else 0
        current = history[-1][0] if history else messages[0][2]
        if title is not None:
            if expected_revision is not None and expected_revision != revision:
                raise Stale('stale title preview; preview again before applying')
            with c:
                c.execute('CREATE TABLE IF NOT EXISTS title_history (id INTEGER PRIMARY KEY, source TEXT, conversation TEXT, previous TEXT, title TEXT, changed_at TEXT DEFAULT CURRENT_TIMESTAMP)')
                c.execute('CREATE INDEX IF NOT EXISTS title_history_identity ON title_history(source,conversation,id)')
                revision = c.execute('INSERT INTO title_history(source,conversation,previous,title) VALUES(?,?,?,?)', (source, conversation, current, title)).lastrowid
            current = title
        return dict(display_title=current, suggested_title=suggestion, revision=revision, original_title=messages[0][2], prior_titles=[m[0] for m in history], scope='local display only')
    finally:
        c.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    add_json_errors_argument(p)
    p.add_argument('--db')
    sub = p.add_subparsers(dest='command', required=True)
    imp = sub.add_parser('import'); imp.add_argument('path'); imp.add_argument('--format', choices=['web', 'local', 'local-codex'], required=True); imp.add_argument('--source', required=True)
    check = sub.add_parser('inspect'); check.add_argument('path'); check.add_argument('--format', choices=['web', 'local', 'local-codex', 'normalized'], required=True)
    imp.add_argument('--conversation', help='import only this explicit conversation after validating the whole file')
    check.add_argument('--conversation', help='inspect an explicit conversation selection without writing')
    for command in (imp, check):
        command.add_argument('--expected-export-sha256', help='require the exact original whole-file hash from earlier inspection')
    t = sub.add_parser('title'); t.add_argument('--source', required=True); t.add_argument('--conversation', required=True); t.add_argument('--set')
    t.add_argument('--expected-revision', type=int)
    a = p.parse_args()
    try:
        if a.command != 'inspect' and not a.db:
            raise ValueError('--db is required for import and title commands')
        if a.command == 'title' and a.set is not None and a.expected_revision is None:
            raise ValueError('--set requires --expected-revision from a title preview')
        if a.command == 'inspect':
            result = inspect_export(a.path, a.format, a.conversation, a.expected_export_sha256)
        elif a.command == 'import':
            result = import_export(a.db, a.source, a.path, a.format, a.conversation, a.expected_export_sha256)
        else:
            result = titles(a.db, a.source, a.conversation, a.set, a.expected_revision)
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as e:
        exit_error(p, a, e)
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
