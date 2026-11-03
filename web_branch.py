"""Read one explicit web export branch; never open or modify an archive."""
import argparse
import json
from pathlib import Path
from strict_json import loads
from session_workflow import _normalize_bytes


def branch_view(path, conversation, node=None):
    if not isinstance(conversation, str) or not conversation:
        raise ValueError('conversation ID required')
    if node is not None and (not isinstance(node, str) or not node):
        raise ValueError('node ID must be nonempty text')
    path = Path(path)
    raw = path.read_bytes()
    # Both parsing passes use the same immutable bytes, including the original hash.
    rows, coverage = _normalize_bytes(raw, path.name, 'web', include_report=True)
    data = loads(raw.decode('utf-8'))
    matches = [c for c in data if (c.get('id') or c.get('conversation_id')) == conversation]
    if len(matches) != 1:
        raise ValueError('conversation must identify exactly one export record')
    conv = matches[0]
    mapping = conv['mapping']
    selected = node if node is not None else conv.get('current_node')
    if not isinstance(selected, str) or not selected or selected not in mapping:
        raise ValueError('selected node or current_node must reference an existing mapping node')
    # The complete parent graph was validated before selection; no fallback or recursion.
    node_ids = []
    current = selected
    while current is not None:
        node_ids.append(current)
        current = mapping[current].get('parent')
    node_ids.reverse()
    texts = {r['message_id']: r for r in rows if r['conversation_id'] == conversation}
    children = {key: [] for key in mapping}
    for key, value in mapping.items():
        if value.get('parent') is not None:
            children[value['parent']].append(key)
    return dict(conversation=conversation, original_title=conv.get('title') or '',
                original_sha256=coverage['original_sha256'],
                selection='explicit node' if node is not None else 'current_node',
                selected_node=selected, selected_node_is_leaf=not children[selected],
                leaf_nodes=[key for key in mapping if not children[key]],
                continuations=children[selected],
                node_ids=node_ids, selected_nodes=len(node_ids),
                excluded_nodes=len(mapping) - len(node_ids),
                messages=[texts[key] for key in node_ids if key in texts],
                selected_nodes_without_text=sum(key not in texts for key in node_ids),
                forks=[dict(node=key, children=children[key]) for key in node_ids if len(children[key]) > 1],
                scope='read-only export view; no database or remote changes',
                warning='PRIVATE CONTENT: output includes conversation text and node IDs; all supported roles are included, not a UI visibility reconstruction')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input'); parser.add_argument('--conversation', required=True)
    parser.add_argument('--node')
    args = parser.parse_args()
    try:
        result = branch_view(args.input, args.conversation, args.node)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(1, str(error) + '\n')
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
