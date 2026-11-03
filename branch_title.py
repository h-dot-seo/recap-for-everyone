"""Generate a local excerpt from a verified archived web-export path, read-only."""
import argparse
import json
import sqlite3
from conversation_view import conversation as archive_conversation
from title_proposal import content_fingerprint
from title_suggestion import excerpt
from title_rules import validate_title
from web_branch import branch_view


def suggest_branch(db, source, conversation, path, node=None):
    branch = branch_view(path, conversation, node)
    # One archive read transaction covers message contents and both provenance ledgers.
    archive = archive_conversation(db, source, conversation)
    by_id = {message['message_id']: message for message in archive['messages']}
    for message in branch['messages']:
        stored = by_id.get(message['message_id'])
        if stored is None or any(stored[key] != message[key] for key in ('role', 'text', 'timestamp')):
            raise ValueError('selected branch text does not match the archived conversation')
        expected = dict(original_sha256=branch['original_sha256'],
                        locator=message['origin_locator'], parent_id=message['parent_id'])
        if expected not in stored['export_provenance']:
            raise ValueError('selected branch lacks matching archived export provenance; import the original export first')
    proposal = excerpt(branch['messages'])
    validate_title(proposal['title'])
    rows = [dict(message_id=m['message_id'], role=m['role'], text=m['text']) for m in archive['messages']]
    return dict(source=source, conversation=conversation,
                content_sha256=content_fingerprint(rows), provider='local-extractive', **proposal,
                branch_context=dict(original_sha256=branch['original_sha256'],
                                    selection=branch['selection'], selected_node=branch['selected_node'],
                                    node_ids=branch['node_ids'],
                                    message_ids=[m['message_id'] for m in branch['messages']],
                                    selected_nodes_without_text=branch['selected_nodes_without_text'],
                                    excluded_nodes=branch['excluded_nodes']),
                scope='proposal for one conversation-wide local display title, selected from a pinned export branch',
                warning='Review before applying; branch context is descriptive, not authenticated. This does not track later export or current_node changes.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True); parser.add_argument('--source', required=True)
    parser.add_argument('--conversation', required=True); parser.add_argument('--node')
    parser.add_argument('input')
    args = parser.parse_args()
    try:
        result = suggest_branch(args.db, args.source, args.conversation, args.input, args.node)
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as error:
        parser.exit(1, str(error) + '\n')
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
