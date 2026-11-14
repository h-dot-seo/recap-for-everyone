"""Bridge verified local source occurrences to a retained-turn title proposal."""
from recaplib.errors import add_json_errors_argument, exit_error
from recaplib.cli_errors import safe_diagnostic
import argparse
import json
import sqlite3
from pathlib import Path
from recaplib.conversation_view import conversation as archive_conversation
from recaplib.replay_local import reconstruct_bytes
from recaplib.session_workflow import _normalize_bytes
from recaplib.title_proposal import content_fingerprint
from recaplib.title_suggestion import excerpt
from recaplib.title_rules import validate_title
from recaplib.strict_json import loads
from recaplib.source_text import physical_lines


def replay_evidence(db, source, conversation, path):
    """Return verified retained rows, the whole archive digest, and descriptive context."""
    path = Path(path)
    raw = path.read_bytes()
    projection = reconstruct_bytes(raw)
    if not projection['supported']:
        raise ValueError('unsupported projection: ' + projection['reason_code'])
    if projection['conversation'] != conversation:
        raise ValueError('projection does not match the selected conversation')
    normalized = _normalize_bytes(raw, path.name, 'local-codex')
    archive = archive_conversation(db, source, conversation)
    # Resolve physical occurrences, never infer archive identity from projection_id.
    occurrence_index = {}
    for message in archive['messages']:
        for origin in message['export_provenance']:
            if origin['original_sha256'] == projection['original_sha256'] and origin['parent_id'] is None:
                occurrence_index.setdefault(origin['locator'], {})[message['message_id']] = message
    by_locator = {}
    source_lines = physical_lines(raw)
    for original in normalized:
        if original['conversation_id'] != conversation:
            raise ValueError('export normalization contains another conversation')
        candidates = occurrence_index.get(original['origin_locator'], {})
        if len(candidates) != 1:
            raise ValueError('source occurrence must match exactly one archived message; import the original export or resolve duplicate identities')
        stored = next(iter(candidates.values()))
        if any(stored[key] != original[key] for key in ('role', 'text', 'timestamp')):
            raise ValueError('source occurrence differs from archived content')
        line_number = int(original['origin_locator'].split(':')[1])
        source_id = loads(source_lines[line_number - 1])['payload'].get('id')
        if source_id is not None and source_id != stored['message_id']:
            raise ValueError('explicit source ID differs from archived identity')
        by_locator[original['origin_locator']] = stored
    selected = []
    mappings = []
    for turn in projection['turns']:
        for message in turn['messages']:
            stored = by_locator.get(message['origin_locator'])
            if stored is None or any(stored[key] != message[key] for key in ('role', 'text')):
                raise ValueError('retained projection text lacks matching source evidence')
            if message['message_id'] is not None and message['message_id'] != stored['message_id']:
                raise ValueError('explicit source ID differs from archived identity')
            selected.append(dict(message_id=stored['message_id'], role=stored['role'], text=stored['text']))
            mappings.append(dict(projection_id=message['projection_id'], archive_message_id=stored['message_id'],
                                 source_message_id=message['message_id'], origin_locator=message['origin_locator']))
    rows = [dict(message_id=m['message_id'], role=m['role'], text=m['text']) for m in archive['messages']]
    context = dict(projection_context=dict(contract=projection['contract'], original_sha256=projection['original_sha256'],
                    retained_turns=projection['retained_turns'], rolled_back_turns=projection['rolled_back_turns'],
                    evidence_mappings=mappings,
                    full_model_history_reconstructed=False),
                scope='one conversation-wide local display title, selected from verified retained text turns',
                warning='Pinned source snapshot; review before apply. Projection context is descriptive, not authenticated. Raw archive history remains unchanged.')

    return selected, content_fingerprint(rows), context


def suggest_replay(db, source, conversation, path, message_id=None):
    if message_id is not None and (not isinstance(message_id, str) or not message_id):
        raise ValueError('selected message ID must be nonempty text')
    selected, digest, context = replay_evidence(db, source, conversation, path)
    if message_id is not None:
        # Occurrence/projection verification still covers all source messages,
        # including removed turns. Select only one resolved retained user row.
        selected = [row for row in selected if row['message_id'] == message_id]
        if len(selected) != 1 or selected[0]['role'] != 'user':
            raise ValueError('selected message must identify one user message in the retained projection')
        context['evidence_selection'] = dict(mode='explicit_user_message', message_id=message_id,
                                            scope='verified retained local turns')
    suggestion = excerpt(selected)
    validate_title(suggestion['title'])
    projection = context['projection_context']
    projection['evidence_mappings'] = [m for m in projection['evidence_mappings']
                                       if m['archive_message_id'] in suggestion['evidence_message_ids']]
    return dict(source=source, conversation=conversation, provider='local-extractive',
                content_sha256=digest, **suggestion, **context)


def main():
    from recaplib.title_document_output import add_output_argument, save_if_requested
    parser = argparse.ArgumentParser(description=__doc__)
    add_json_errors_argument(parser)
    parser.add_argument('--db', required=True); parser.add_argument('--source', required=True)
    parser.add_argument('--conversation', required=True); parser.add_argument('input')
    parser.add_argument('--message', help='use exactly this archived user message inside the verified retained turns, not a projection ID')
    add_output_argument(parser)
    args = parser.parse_args()
    try:
        result = suggest_replay(args.db, args.source, args.conversation, args.input, args.message)
        result = save_if_requested(result, args, 'proposal')
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as error:
        exit_error(parser, args, error)
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
