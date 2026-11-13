"""Illustrate one invented foreign format; not a vendor adapter or reuse license."""
import argparse
import hashlib
import json
from pathlib import Path


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON member')
        result[key] = value
    return result


def _constant(value):
    raise ValueError('nonfinite JSON numbers are unsupported')


def _text(value):
    if not isinstance(value, str) or not value:
        raise ValueError('required fields must be nonempty text')
    if any(0xd800 <= ord(character) <= 0xdfff for character in value):
        raise ValueError('text must contain valid Unicode')
    return value


def convert(source, output):
    """Validate one explicit synthetic-shape file, then exclusively create JSONL.

    Whole files are held in memory; no discovery, database or network access.
    This deliberately narrow illustration rejects unknown members, unlike ingest.
    """
    raw = Path(source).read_bytes()
    try:
        document = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_pairs,
                              parse_constant=_constant)
    except (ValueError, RecursionError) as error:
        raise ValueError('invalid UTF-8 foreign JSON document') from error
    if (not isinstance(document, dict) or set(document) != {'format', 'threads'} or
            document['format'] != 'invented-chat-demo.v1' or not isinstance(document['threads'], list)):
        raise ValueError('unsupported invented foreign format')
    rows, identities = [], set()
    for thread in document['threads']:
        if not isinstance(thread, dict) or set(thread) != {'key', 'label', 'entries'}:
            raise ValueError('thread requires exactly key, label and entries')
        conversation = _text(thread['key'])
        title = thread['label']
        if not isinstance(title, str):
            raise ValueError('thread label must be text')
        if title:
            _text(title)
        if conversation in identities:
            raise ValueError('duplicate thread key')
        identities.add(conversation)
        if not isinstance(thread['entries'], list):
            raise ValueError('thread entries must be an array')
        messages = set()
        for entry in thread['entries']:
            if not isinstance(entry, dict) or set(entry) != {'key', 'speaker', 'when', 'body'}:
                raise ValueError('entry requires exactly key, speaker, when and body')
            message = _text(entry['key'])
            if message in messages:
                raise ValueError('duplicate message key within thread')
            messages.add(message)
            role = _text(entry['speaker'])
            if role not in ('user', 'assistant', 'system', 'tool'):
                raise ValueError('unsupported speaker; no role inference')
            rows.append(dict(conversation_id=conversation, message_id=message,
                             role=role, timestamp=_text(entry['when']),
                             text=_text(entry['body']), title=title))
    normalized = ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows).encode('utf-8')
    # Build all bytes before touching output. 'xb' refuses an existing file,
    # directory or final symlink. Parent must exist; an I/O failure may leave a
    # partial new file, which is not a successful conversion and is not deleted.
    with Path(output).open('xb') as stream:
        stream.write(normalized)
    return dict(schema='recap.adapter-illustration-receipt.v1',
                source_sha256=hashlib.sha256(raw).hexdigest(), source_bytes=len(raw),
                normalized_sha256=hashlib.sha256(normalized).hexdigest(),
                normalized_bytes=len(normalized), records=len(rows),
                database_access=False, remote_mutation=False,
                warning='Keep the original, normalized file and receipt privately. Later ingest provenance is the normalized hash and physical line, not the original foreign file. Hash linkage is not authenticity or completeness.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input')
    parser.add_argument('--output', required=True, help='new JSONL file; existing parent required')
    args = parser.parse_args()
    try:
        result = convert(args.input, args.output)
    except (OSError, ValueError, RecursionError):
        # Do not echo input content, IDs or local paths from exception details.
        parser.exit(1, 'Conversion failed. Check the invented format and use a new output file. Any partial new output is left for inspection.\n')
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
