"""Propose a local title from explicitly source-labeled user text in a pinned export."""
import argparse
import json
import sqlite3
from pathlib import Path

from conversation_view import conversation as archive_conversation
from session_workflow import _normalize_bytes
from strict_json import loads
from title_proposal import content_fingerprint
from title_rules import validate_title
from title_suggestion import excerpt
from source_text import physical_lines

SCHEMA = 'recap.source-attributed-title.v1'


class NoAttributedEvidence(ValueError):
    """Supported attribution was inspected but selected no usable user text."""


def _part_sources(payload):
    """Conservative subset of positional Codex producer attribution, not trust."""
    content = payload['content']
    wrapper = payload.get('internal_chat_message_metadata_passthrough')
    if wrapper is None:
        return ['unknown'] * len(content)
    if not isinstance(wrapper, dict):
        raise ValueError('attribution wrapper must be an object or null')
    entries = wrapper.get('content_item_metadata')
    if entries is None:
        return ['unknown'] * len(content)
    if not isinstance(entries, list) or len(entries) != len(content):
        raise ValueError('attribution array must exactly match all content positions')
    sources = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) - {'provenance', 'harness_injected', 'source_tool_namespace'}:
            raise ValueError('unsupported attribution entry')
        harness = entry.get('harness_injected')
        namespace = entry.get('source_tool_namespace')
        if harness is not None and type(harness) is not bool:
            raise ValueError('legacy attribution flag must be boolean or null')
        if namespace is not None and not isinstance(namespace, str):
            raise ValueError('legacy attribution namespace must be text or null')
        provenance = entry.get('provenance')
        if provenance is None:
            sources.append('tool' if namespace is not None else 'harness' if harness is True else 'unknown')
            continue
        if harness is not None or namespace is not None:
            raise ValueError('mixed explicit and legacy attribution encodings are unsupported')
        if not isinstance(provenance, dict):
            raise ValueError('attribution provenance must be an object or null')
        kind = provenance.get('type')
        allowed = {'unknown': set(), 'user_configured': set(), 'user': set(),
                   'skills': set(), 'agents_md': set(), 'harness': {'hook'},
                   'tool': {'namespace'}, 'developer_instructions': {'from_additional_requirements'}}
        if not isinstance(kind, str) or kind not in allowed or set(provenance) - ({'type'} | allowed[kind]):
            raise ValueError('unsupported attribution provenance')
        if kind == 'harness' and 'hook' in provenance and type(provenance['hook']) is not bool:
            raise ValueError('attribution hook must be boolean')
        if kind == 'tool' and provenance.get('namespace') is not None and not isinstance(provenance['namespace'], str):
            raise ValueError('attribution namespace must be text or null')
        if kind == 'developer_instructions' and type(provenance.get('from_additional_requirements')) is not bool:
            raise ValueError('developer attribution requires a boolean requirements flag')
        sources.append('unknown' if kind == 'user_configured' else kind)
    return sources


def attributed_evidence(db, source, conversation, path):
    """Return verified user-attributed parts, the whole archive digest, and context.

    Each row retains its physical origin_locator because different occurrences
    of the same archive message can label different content parts as user text.
    """
    path = Path(path)
    raw = path.read_bytes()
    normalized, extraction = _normalize_bytes(raw, path.name, 'local-codex', include_report=True)
    selected = [row for row in normalized if row['conversation_id'] == conversation]
    if not selected:
        raise ValueError('export contains no extracted messages for the selected conversation')
    # Match the parser's universal newline handling without treating Unicode
    # separators embedded inside JSON strings as physical record boundaries.
    lines = physical_lines(raw)
    coverage = dict(total_text_parts=0, selected_user_text_parts=0, excluded_text_parts=0,
                    unknown_text_parts=0, non_user_text_parts=0, messages_with_selected_text=0)
    candidates = []
    by_locator = {}
    payloads = {}
    for row in selected:
        locator = row['origin_locator']
        payload = loads(lines[int(locator.split(':')[1]) - 1])['payload']
        payloads[locator] = payload
        if row['role'] != 'user':
            continue
        sources = _part_sources(payload)
        indices, texts = [], []
        for index, part in enumerate(payload['content']):
            if part.get('type') not in ('input_text', 'output_text'):
                continue
            coverage['total_text_parts'] += 1
            if sources[index] == 'user':
                indices.append(index)
                texts.append(part['text'])
                coverage['selected_user_text_parts'] += 1
            else:
                coverage['excluded_text_parts'] += 1
                coverage['unknown_text_parts' if sources[index] == 'unknown' else 'non_user_text_parts'] += 1
        text = '\n'.join(texts)
        if text.strip():
            coverage['messages_with_selected_text'] += 1
            # Physical locators keep repeated archive IDs distinguishable while
            # selecting an excerpt. Returned proposal IDs are resolved below.
            candidates.append(dict(message_id=locator, role='user', text=text))
            by_locator[locator] = indices
    if not candidates:
        raise NoAttributedEvidence('no explicitly user-attributed text for a title proposal')
    archive = archive_conversation(db, source, conversation)
    occurrences = {}
    for message in archive['messages']:
        for origin in message['export_provenance']:
            if origin['original_sha256'] == extraction['original_sha256'] and origin['parent_id'] is None:
                occurrences.setdefault(origin['locator'], {})[message['message_id']] = message
    resolved = {}
    # Verify the full selected raw conversation, including noncandidate messages.
    # The producer label is not a substitute for the archived source association.
    for original in selected:
        locator = original['origin_locator']
        matches = occurrences.get(locator, {})
        if len(matches) != 1:
            raise ValueError('source occurrence must match exactly one archived message; import the original export or resolve duplicate identities')
        stored = next(iter(matches.values()))
        if any(stored[key] != original[key] for key in ('role', 'text', 'timestamp')):
            raise ValueError('source occurrence differs from archived content')
        explicit_id = payloads[locator].get('id')
        if isinstance(explicit_id, str) and explicit_id and explicit_id != stored['message_id']:
            raise ValueError('explicit source ID differs from archived identity')
        resolved[locator] = stored['message_id']
    evidence = [dict(message_id=resolved[locator], origin_locator=locator,
                     content_indices=by_locator[locator]) for locator in by_locator]
    rows = [dict(message_id=resolved[row['message_id']], role=row['role'], text=row['text'],
                 origin_locator=row['message_id']) for row in candidates]
    content = [dict(message_id=m['message_id'], role=m['role'], text=m['text']) for m in archive['messages']]
    context = dict(attribution_context=dict(schema=SCHEMA, original_sha256=extraction['original_sha256'],
                    evidence_parts=evidence, coverage=coverage, producer_attribution_authenticated=False,
                    coverage_scope='extracted user-role messages in the selected raw conversation',
                    selection_policy='only typed text parts with explicit producer provenance type user; exact positional metadata alignment'),
                extraction_warnings=extraction['warnings'],
                scope='source-labeled user excerpt for one local display title; raw records, not retained replay history',
                warning='Producer labels and this context are unsigned, not verified human authorship, trust or authorization. Review before apply. No source text is changed or sent externally.')

    return rows, content_fingerprint(content), context


def suggest_attributed(db, source, conversation, path):
    rows, digest, context = attributed_evidence(db, source, conversation, path)
    # Excerpt selection must distinguish occurrences before resolving archive IDs.
    candidates = [dict(message_id=row['origin_locator'], role=row['role'], text=row['text'])
                  for row in rows]
    proposed = excerpt(candidates)
    validate_title(proposed['title'])
    attribution = context['attribution_context']
    attribution['evidence_parts'] = [part for part in attribution['evidence_parts']
                                     if part['origin_locator'] in proposed['evidence_message_ids']]
    proposed['evidence_message_ids'] = [part['message_id'] for part in attribution['evidence_parts']]
    return dict(source=source, conversation=conversation, provider='local-extractive',
                content_sha256=digest, **proposed, **context)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--conversation', required=True)
    parser.add_argument('input')
    args = parser.parse_args()
    try:
        result = suggest_attributed(args.db, args.source, args.conversation, args.input)
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as error:
        parser.exit(1, str(error) + '\n')
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
