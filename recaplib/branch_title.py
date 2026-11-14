"""Generate a local excerpt from a verified archived web-export path, read-only."""
from recaplib.errors import add_json_errors_argument, exit_error
from recaplib.cli_errors import safe_diagnostic
import argparse
import json
import sqlite3
from recaplib.conversation_view import conversation as archive_conversation
from recaplib.title_proposal import content_fingerprint
from recaplib.title_suggestion import excerpt
from recaplib.title_rules import validate_title
from recaplib.web_branch import branch_view


def verify_export_messages(messages, archive):
    by_id = {message['message_id']: message for message in archive['messages']}
    for message in messages:
        stored = by_id.get(message['message_id'])
        if stored is None or any(stored[key] != message[key] for key in ('role', 'text', 'timestamp')):
            raise ValueError('export text does not match the archived conversation')
        expected = dict(original_sha256=message['origin_sha256'],
                        locator=message['origin_locator'], parent_id=message.get('parent_id'))
        if expected not in stored['export_provenance']:
            raise ValueError('export lacks matching archived export provenance; import the original export first')


def branch_evidence(db, source, conversation, path, node=None):
    """Return verified branch rows, the whole archive digest, and descriptive context."""
    branch = branch_view(path, conversation, node)
    # One archive read transaction covers message contents and both provenance ledgers.
    archive = archive_conversation(db, source, conversation)
    verify_export_messages(branch['messages'], archive)
    rows = [dict(message_id=m['message_id'], role=m['role'], text=m['text']) for m in archive['messages']]
    selected = [dict(message_id=m['message_id'], role=m['role'], text=m['text'])
                for m in branch['messages']]
    context = dict(branch_context=dict(original_sha256=branch['original_sha256'],
                                    selection=branch['selection'], selected_node=branch['selected_node'],
                                    node_ids=branch['node_ids'],
                                    message_ids=[m['message_id'] for m in branch['messages']],
                                    selected_nodes_without_text=branch['selected_nodes_without_text'],
                                    excluded_nodes=branch['excluded_nodes']),
                scope='proposal for one conversation-wide local display title, selected from a pinned export branch',
                warning='Review before applying; branch context is descriptive, not authenticated. This does not track later export or current_node changes.')

    return selected, content_fingerprint(rows), context


def suggest_branch(db, source, conversation, path, node=None, message_id=None):
    if message_id is not None and (not isinstance(message_id, str) or not message_id):
        raise ValueError('selected message ID must be nonempty text')
    selected, digest, context = branch_evidence(db, source, conversation, path, node)
    if message_id is not None:
        # Verify the entire selected branch first. A later evidence choice must
        # not bypass mismatches elsewhere on the path or select an alternate fork.
        selected = [row for row in selected if row['message_id'] == message_id]
        if len(selected) != 1 or selected[0]['role'] != 'user':
            raise ValueError('selected message must identify one user message in the verified branch')
        context['evidence_selection'] = dict(mode='explicit_user_message', message_id=message_id,
                                            scope='verified web export branch')
    proposal = excerpt(selected)
    validate_title(proposal['title'])
    return dict(source=source, conversation=conversation, content_sha256=digest,
                provider='local-extractive', **proposal, **context)


def main():
    from recaplib.title_document_output import add_output_argument, save_if_requested
    parser = argparse.ArgumentParser(description=__doc__)
    add_json_errors_argument(parser)
    parser.add_argument('--db', required=True); parser.add_argument('--source', required=True)
    parser.add_argument('--conversation', required=True); parser.add_argument('--node')
    parser.add_argument('--message', help='use exactly this archived user message inside the verified selected branch')
    parser.add_argument('input')
    add_output_argument(parser)
    args = parser.parse_args()
    try:
        result = suggest_branch(args.db, args.source, args.conversation, args.input, args.node, args.message)
        result = save_if_requested(result, args, 'proposal')
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as error:
        exit_error(parser, args, error)
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
