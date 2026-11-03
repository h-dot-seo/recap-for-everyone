"""Fail-closed text-only projection of a narrow, explicit local turn grammar."""
import argparse
import hashlib
import json
from pathlib import Path
from strict_json import loads


class Unsupported(ValueError):
    def __init__(self, code, line):
        self.code, self.line = code, line


def _require(condition, code, line):
    if not condition:
        raise Unsupported(code, line)


def _project(raw):
    try:
        text = raw.decode('utf-8')
    except UnicodeError:
        raise Unsupported('INVALID_UTF8', 0) from None
    session = None
    active = None
    turns = []
    turn_ids, message_ids = set(), set()
    removed_turns = 0
    records = 0
    for line_number, line in enumerate(text.split('\n'), 1):
        if not line.strip():
            continue
        records += 1
        try:
            record = loads(line)
        except ValueError:
            raise Unsupported('INVALID_JSON', line_number) from None
        _require(isinstance(record, dict) and isinstance(record.get('payload'), dict), 'INVALID_RECORD', line_number)
        kind, payload = record.get('type'), record['payload']
        if kind == 'session_meta':
            _require(session is None and records == 1, 'MULTIPLE_OR_LATE_SESSION', line_number)
            session = payload.get('id')
            _require(isinstance(session, str) and bool(session), 'INVALID_SESSION_ID', line_number)
            _require(not any(payload.get(key) is not None for key in
                     ('history_base', 'forked_from_id', 'parent_thread_id', 'history_mode',
                      'subagent_history_start_ordinal', 'forked_from_ordinal_exclusive',
                      'thread_source')), 'UNRESOLVED_HISTORY', line_number)
            _require(payload.get('attached_thread') is None or payload.get('attached_thread') is False,
                     'UNRESOLVED_HISTORY', line_number)
            allowed_meta = {'id', 'session_id', 'source', 'timestamp', 'cwd', 'originator',
                            'cli_version', 'model_provider', 'base_instructions', 'git',
                            'history_base', 'forked_from_id', 'parent_thread_id', 'history_mode',
                            'subagent_history_start_ordinal', 'forked_from_ordinal_exclusive',
                            'thread_source', 'attached_thread'}
            _require(set(payload) <= allowed_meta, 'SESSION_METADATA_UNSUPPORTED', line_number)
            _require(payload.get('session_id') in (None, session), 'UNRESOLVED_HISTORY', line_number)
            _require(payload.get('source') in (None, 'cli', 'vscode', 'exec'), 'SESSION_SOURCE_UNSUPPORTED', line_number)
            continue
        _require(session is not None, 'MISSING_SESSION', line_number)
        if kind == 'compacted':
            raise Unsupported('COMPACTION_UNSUPPORTED', line_number)
        if kind == 'event_msg':
            event = payload.get('type')
            if event in ('task_started', 'turn_started'):
                identity = payload.get('turn_id')
                _require(active is None, 'NESTED_TURN', line_number)
                _require(isinstance(identity, str) and bool(identity) and identity not in turn_ids,
                         'INVALID_OR_REUSED_TURN_ID', line_number)
                _require(payload.get('turn_attribution') is None, 'TURN_ATTRIBUTION_UNSUPPORTED', line_number)
                _require(payload.get('root_turn_id') in (None, identity), 'UNRESOLVED_HISTORY', line_number)
                turn_ids.add(identity)
                active = dict(turn_id=identity, start_line=line_number, messages=[], user_event=None)
            elif event in ('task_complete', 'turn_complete'):
                _require(active is not None and payload.get('turn_id') == active['turn_id'],
                         'UNMATCHED_TURN_COMPLETION', line_number)
                _require(bool(active['messages']) and active['messages'][0]['role'] == 'user',
                         'MISSING_USER_MESSAGE', line_number)
                _require(payload.get('root_turn_id') in (None, active['turn_id']), 'UNRESOLVED_HISTORY', line_number)
                _require(payload.get('error') is None, 'FAILED_TURN_UNSUPPORTED', line_number)
                _require(active['user_event'] is not None, 'MISSING_USER_EVENT', line_number)
                _require(active['user_event'] == active['messages'][0]['text'], 'USER_EVENT_MISMATCH', line_number)
                active.pop('user_event')
                active['end_line'] = line_number
                turns.append(active); active = None
            elif event == 'user_message':
                _require(active is not None and active['user_event'] is None, 'UNSCOPED_USER_EVENT', line_number)
                _require(payload.get('turn_id') in (None, active['turn_id']), 'MESSAGE_TURN_MISMATCH', line_number)
                _require(isinstance(payload.get('message'), str), 'INVALID_USER_EVENT', line_number)
                media_fields = ('images', 'local_images', 'text_elements', 'file_ids', 'audio',
                                'audio_references', 'audio_order', 'local_audio', 'image_details',
                                'file_id_details', 'image_order', 'local_image_details')
                _require(set(payload) <= {'type', 'message', 'turn_id', *media_fields},
                         'USER_EVENT_FIELDS_UNSUPPORTED', line_number)
                _require(all(payload.get(key) is None or payload.get(key) == [] for key in media_fields),
                         'NON_TEXT_UNSUPPORTED', line_number)
                active['user_event'] = payload['message']
            elif event == 'thread_rolled_back':
                count = payload.get('num_turns')
                _require(active is None, 'ROLLBACK_INSIDE_TURN', line_number)
                _require(type(count) is int and 0 <= count <= min(len(turns), 2**32 - 1),
                         'UNRESOLVED_ROLLBACK_COUNT', line_number)
                if count:
                    del turns[-count:]
                    removed_turns += count
            else:
                raise Unsupported('EVENT_UNSUPPORTED', line_number)
        elif kind == 'response_item':
            _require(active is not None, 'MESSAGE_OUTSIDE_TURN', line_number)
            _require(payload.get('type') == 'message' and payload.get('role') in ('user', 'assistant'),
                     'RESPONSE_UNSUPPORTED', line_number)
            for owner in (record, payload):
                _require(owner.get('turn_id') in (None, active['turn_id']), 'MESSAGE_TURN_MISMATCH', line_number)
            identity = payload.get('id')
            _require(isinstance(identity, str) and bool(identity) and identity not in message_ids,
                     'INVALID_OR_REUSED_MESSAGE_ID', line_number)
            role = payload['role']
            _require((role == 'user') == (not active['messages']), 'AMBIGUOUS_USER_BOUNDARY', line_number)
            parts = payload.get('content')
            _require(isinstance(parts, list) and bool(parts), 'INVALID_TEXT_CONTENT', line_number)
            _require(all(isinstance(part, dict) and part.get('type') in ('input_text', 'output_text')
                         and isinstance(part.get('text'), str) for part in parts), 'NON_TEXT_UNSUPPORTED', line_number)
            body = '\n'.join(part['text'] for part in parts)
            _require(bool(body.strip()), 'EMPTY_TEXT_UNSUPPORTED', line_number)
            message_ids.add(identity)
            active['messages'].append(dict(message_id=identity, role=role, text=body,
                                           origin_locator=f'line:{line_number}'))
        else:
            raise Unsupported('RECORD_UNSUPPORTED', line_number)
    _require(session is not None, 'MISSING_SESSION', 0)
    _require(active is None, 'INCOMPLETE_TURN', active['start_line'] if active else 0)
    _require(bool(turn_ids), 'NO_COMPLETE_TURNS', 0)
    return dict(conversation=session, turns=turns, retained_turns=len(turns),
                rolled_back_turns=removed_turns, observed_records=records)


def reconstruct(path):
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return dict(supported=False, reason_code='SOURCE_ERROR', line=0)
    digest = hashlib.sha256(raw).hexdigest()
    try:
        result = _project(raw)
    except Unsupported as error:
        return dict(supported=False, reason_code=error.code, line=error.line, original_sha256=digest,
                    partial_output=False)
    except (ValueError, TypeError, RecursionError):
        return dict(supported=False, reason_code='INVALID_RECORD', line=0, original_sha256=digest, partial_output=False)
    return dict(supported=True, contract='completed-turn-text-projection.v1', original_sha256=digest,
                **result, full_model_history_reconstructed=False,
                scope='read-only text projection; no database, title or remote mutation',
                warning='PRIVATE TEXT: only the supported grammar is projected; model context, tools, hidden state and UI visibility are not reconstructed')


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('input')
    args = parser.parse_args(); result = reconstruct(args.input)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    if not result['supported']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
