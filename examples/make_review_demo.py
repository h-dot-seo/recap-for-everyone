"""Create invented training inputs only, in an explicitly new directory."""
import argparse
import json
from pathlib import Path
import sys
import zipfile


def make_demo(destination):
    destination = Path(destination)
    web, local = [], []
    for index in range(12):
        text = f'Synthetic planning topic {index}'
        if index < 2:
            text = 'Repeated synthetic planning topic'
        role = 'assistant' if index == 3 else 'user'
        web.append({'id': f'web-{index:02}', 'title': 'New chat', 'current_node': 'm2',
                    'mapping': {
                        'm1': {'parent': None, 'message': {'author': {'role': role},
                               'content': {'content_type': 'text', 'parts': [text]}}},
                        'm2': {'parent': 'm1', 'message': {'author': {'role': 'assistant'},
                               'content': {'content_type': 'text', 'parts': ['Synthetic reply']}}}}})
        local.extend([
            {'type': 'session_meta', 'payload': {'id': f'local-{index:02}'}},
            {'type': 'response_item', 'payload': {'type': 'message', 'role': role,
             'id': f'local-message-{index}', 'content': [
                 {'type': 'input_text' if role == 'user' else 'output_text', 'text': text}]}}])
    # Fail if the directory exists, including a symlink. Do not scan or read inputs.
    # Parent must already exist. Failures after mkdir may leave partial demo files.
    destination.mkdir(mode=0o700)
    with zipfile.ZipFile(destination / 'web.zip', 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for part, conversations in ((2, web[6:]), (1, web[:6])):
            archive.writestr(f'conversations-{part:03}.json', json.dumps(conversations))
    with (destination / 'local.jsonl').open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(''.join(json.dumps(record) + '\n' for record in local))
    return {'synthetic_only': True, 'web_conversations': 12, 'local_conversations': 12,
            'files_created': ['web.zip', 'local.jsonl'], 'database_created': False,
            'remote_mutation': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', help='new directory; parent must already exist')
    args = parser.parse_args()
    try:
        result = make_demo(args.destination)
    except (OSError, ValueError):
        print('Demo creation failed. Use a new directory with an existing writable parent. '
              'Any partially created demo files are left for inspection; no existing directory is reused.', file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
