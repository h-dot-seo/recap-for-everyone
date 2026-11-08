"""Export and recheck a manual title-change plan, without remote execution."""
import argparse
import json
import sqlite3
from pathlib import Path
from recaplib.branch_title import verify_export_messages
from recaplib.conversation_view import conversation as archive_conversation
from recaplib.session_workflow import _normalize_bytes
from recaplib.strict_json import loads
from recaplib.title_proposal import content_fingerprint
from recaplib.title_rules import validate_title
from recaplib.source_text import decode_source
from recaplib.source_identity import aliased_identity


SCHEMA = 'recap.manual-title-plan.v2'


def make_plan(db, source, conversation, path, kind):
    path = Path(path)
    raw = path.read_bytes()
    rows, coverage = _normalize_bytes(raw, path.name, kind, include_report=True)
    if kind == 'web':
        matches = [c for c in loads(decode_source(raw))
                   if aliased_identity(c, 'conversation_id') == conversation]
        if len(matches) != 1:
            raise ValueError('conversation must identify exactly one export record')
    selected = [row for row in rows if row['conversation_id'] == conversation]
    if not selected:
        raise ValueError('export contains no text for the selected conversation')
    archive = archive_conversation(db, source, conversation)
    verify_export_messages(selected, archive)
    if archive['revision'] == 0:
        raise ValueError('set and review a local display title before exporting a plan')
    validate_title(archive['display_title'])
    content = [dict(message_id=m['message_id'], role=m['role'], text=m['text']) for m in archive['messages']]
    return dict(schema=SCHEMA, source=source, conversation=conversation, format=kind,
                original_sha256=coverage['original_sha256'], content_sha256=content_fingerprint(content),
                expected_revision=archive['revision'], original_title=archive['original_title'],
                proposed_title=archive['display_title'],
                action='no_change' if archive['display_title'] == archive['original_title'] else 'manual_rename',
                execution_status='NOT_EXECUTED', remote_mutation=False, includes_message_records=False,
                extraction_warnings=coverage['warnings'],
                effective_history_reconstructed=False,
                scope='manual transfer of a local display title; source/conversation IDs are archive identities, not verified remote targets',
                warning='PRIVATE METADATA: titles and identifiers may be sensitive. Recheck before manual use. This plan grants no service access or execution permission.')


def check_plan(db, path, plan):
    if not isinstance(plan, dict) or plan.get('schema') != SCHEMA:
        raise ValueError('unsupported title plan')
    for key in ('source', 'conversation', 'format'):
        if not isinstance(plan.get(key), str) or not plan[key]:
            raise ValueError('title plan requires source, conversation and format')
    current = make_plan(db, plan['source'], plan['conversation'], path, plan['format'])
    if json.dumps(plan, sort_keys=True, ensure_ascii=True) != json.dumps(current, sort_keys=True, ensure_ascii=True):
        raise ValueError('title plan is stale or altered; export and review a new plan')
    return dict(valid=True, schema=SCHEMA, execution_status='NOT_EXECUTED', remote_mutation=False,
                warning='Local consistency check only; remote identity and remote title are not verified.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    export = commands.add_parser('export'); export.add_argument('input')
    export.add_argument('--format', choices=['web', 'local', 'local-codex'], required=True)
    export.add_argument('--source', required=True); export.add_argument('--conversation', required=True)
    check = commands.add_parser('check'); check.add_argument('input'); check.add_argument('plan', type=Path)
    args = parser.parse_args()
    try:
        result = (make_plan(args.db, args.source, args.conversation, args.input, args.format)
                  if args.command == 'export' else check_plan(args.db, args.input, loads(args.plan.read_text(encoding='utf-8'))))
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as error:
        parser.exit(1, str(error) + '\n')
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
