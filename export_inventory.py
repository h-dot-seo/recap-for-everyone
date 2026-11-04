"""List explicit export identities and titles without importing message bodies."""
import argparse
import json
import unicodedata
from collections import Counter
from pathlib import Path

from session_workflow import _normalize_bytes, _read_export_bytes
from strict_json import loads
from source_text import decode_source, physical_lines
from source_identity import aliased_identity
from unicode_search import canonical_fold


def list_export(path, kind, limit=50, offset=0, expected_export_sha256=None, *,
                contains=None, canonical_unicode=False, text_contains=None):
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError('limit must be an integer in 1..1000')
    if type(offset) is not int or not 0 <= offset <= 2**63 - 1:
        raise ValueError('offset must be an integer in 0..9223372036854775807')
    if kind not in ('web', 'local', 'local-codex'):
        raise ValueError('unsupported format')
    if type(canonical_unicode) is not bool:
        raise ValueError('canonical_unicode must be boolean')
    if contains is not None and text_contains is not None:
        raise ValueError('choose either contains or text_contains, not both')
    if contains is None and text_contains is None and canonical_unicode:
        raise ValueError('canonical Unicode matching requires --contains or --text-contains')
    for name, value in (('contains', contains), ('text_contains', text_contains)):
        if value is not None:
            if not isinstance(value, str) or not value.strip() or len(value) > 256:
                raise ValueError(name + ' must be non-whitespace text of at most 256 code points')
            if any(0xd800 <= ord(character) <= 0xdfff for character in value):
                raise ValueError(name + ' must contain valid Unicode text')
    fold = canonical_fold if canonical_unicode else str.casefold
    path = Path(path)
    raw = _read_export_bytes(path, expected_export_sha256)
    rows, coverage = _normalize_bytes(raw, path.name, kind, include_report=True)
    if expected_export_sha256 is not None:
        coverage['expected_export_sha256'] = expected_export_sha256
    items = {}

    def register(identity, title=None):
        item = items.setdefault(identity, dict(conversation=identity, original_titles=[],
            metadata_records=0, extracted_messages=0, role_counts={}))
        item['metadata_records'] += 1
        if title is not None and title not in item['original_titles']:
            item['original_titles'].append(title)

    if kind == 'web':
        for record in loads(decode_source(raw)):
            register(aliased_identity(record, 'conversation_id'), record.get('title') or '')
    else:
        # Mirror local_parser's universal newlines, not Unicode splitlines.
        for line in physical_lines(raw):
            if not line.strip():
                continue
            record = loads(line)
            if record.get('type') == 'session_meta':
                payload = record['payload']
                register(aliased_identity(payload, 'session_id'))
    roles = {}
    matched_roles = {}
    text_needle = fold(text_contains) if text_contains is not None else None
    for row in rows:
        identity = row['conversation_id']
        roles.setdefault(identity, Counter())[row['role']] += 1
        # Count an extracted message occurrence once, not each substring hit.
        # Never join separate messages or limit the original metadata group.
        if text_needle is not None and text_needle in fold(row['text']):
            matched_roles.setdefault(identity, Counter())[row['role']] += 1
    for identity, item in items.items():
        item['role_counts'] = dict(sorted(roles.get(identity, {}).items()))
        item['extracted_messages'] = sum(item['role_counts'].values())
        item['selection_blocker'] = ('AMBIGUOUS_WEB_ID' if kind == 'web' and item['metadata_records'] > 1
                                     else 'NO_EXTRACTED_TEXT' if not item['extracted_messages'] else None)
        item['selection_supported'] = item['selection_blocker'] is None
        if text_contains is not None:
            item['matched_role_counts'] = dict(sorted(matched_roles.get(identity, {}).items()))
            item['matched_messages'] = sum(item['matched_role_counts'].values())
    if text_contains is not None:
        identities = sorted(identity for identity in items if identity in matched_roles)
    elif contains is None:
        identities = sorted(items)
    else:
        needle = fold(contains)
        # Group first: a matching title must never hide another record with the
        # same identity or turn an ambiguous selected import into an allowed one.
        identities = sorted(identity for identity, item in items.items()
                            if needle in fold(identity) or
                            any(needle in fold(title) for title in item['original_titles']))
    selected = [items[key] for key in identities[offset:offset + limit]]
    next_offset = offset + len(selected)
    result = dict(format=kind, original_sha256=coverage['original_sha256'],
        original_bytes=len(raw), total_conversations=len(items), conversations=selected,
        selectable_conversations=sum(item['selection_supported'] for item in items.values()),
        limit=limit, offset=offset, next_offset=next_offset if next_offset < len(identities) else None,
        order='conversation ID, Unicode code-point order', contains_message_text=False,
        coverage=coverage,
        scope='read-only export inventory; full file parsed; no database access or effective-history reconstruction',
        warning='PRIVATE METADATA: titles and IDs may be sensitive. No message body fields are included; titles are not redacted or verified. Selection support describes parser output, not import authorization or conflict-free database insertion.')
    if contains is not None:
        result['filter'] = dict(contains=contains, fields=['conversation', 'original_titles'],
            matching='literal substring within one case-folded metadata field',
            canonical_unicode=canonical_unicode, matched_conversations=len(identities),
            matched_selectable_conversations=sum(items[key]['selection_supported'] for key in identities),
            pagination_scope='matching identities only; total_conversations, selectable_conversations and coverage still describe the whole file',
            warning='The query can be private. No message-body search or local-title inference is performed; filtering does not avoid reading or validating unselected content.')
    elif text_contains is not None:
        result['filter'] = dict(text_contains=text_contains, fields=['extracted_message_text'],
            matching='literal substring within one case-folded extracted message',
            canonical_unicode=canonical_unicode, matched_conversations=len(identities),
            matched_selectable_conversations=sum(items[key]['selection_supported'] for key in identities),
            matched_messages=sum(items[key]['matched_messages'] for key in identities),
            pagination_scope='matching identities only; total_conversations, selectable_conversations and coverage still describe the whole file',
            message_scope='all supported extracted roles; all web branches and raw local records, not effective history or source-attributed user text',
            warning='The echoed query can reveal message text. No extracted message-body fields are returned. Matching counts do not establish human authorship, effective history, import permission or title suitability; the full file is still read and validated.')
    if 'filter' in result and canonical_unicode:
        result['filter'].update(normalization='NFC(NFD(text).casefold())',
                                unicode_version=unicodedata.unidata_version)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input')
    parser.add_argument('--format', choices=['web', 'local', 'local-codex'], required=True)
    parser.add_argument('--limit', type=int, default=50)
    parser.add_argument('--offset', type=int, default=0)
    parser.add_argument('--expected-export-sha256', help='require the same original whole-file hash as an earlier page')
    filters = parser.add_mutually_exclusive_group()
    filters.add_argument('--contains', help='filter IDs or existing web titles by one literal case-insensitive substring before pagination')
    filters.add_argument('--text-contains', help='find IDs by one literal substring in extracted message text; return metadata and match counts, not bodies')
    parser.add_argument('--canonical-unicode', action='store_true', help='match canonical Unicode equivalents; requires --contains or --text-contains')
    args = parser.parse_args()
    try:
        result = list_export(args.input, args.format, args.limit, args.offset, args.expected_export_sha256,
                             contains=args.contains, canonical_unicode=args.canonical_unicode,
                             text_contains=args.text_contains)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(1, str(error) + '\n')
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
