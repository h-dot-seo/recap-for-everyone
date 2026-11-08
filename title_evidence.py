"""Opt-in bounded raw evidence for human title review; never approval or a send."""

MAX_MESSAGES = 5
MAX_EXCERPT_CHARACTERS = 2000
MAX_PROVENANCE_OCCURRENCES = 3


def review_evidence(connection, proposal, rows, digest):
    """Use the caller's already-validated rows and active SQLite read snapshot."""
    source, conversation = proposal['source'], proposal['conversation']
    references = proposal['evidence_message_ids']
    identities = list(dict.fromkeys(references))
    selected = identities[:MAX_MESSAGES]
    wanted = set(selected)
    by_id = {row['message_id']: row for row in rows if row['message_id'] in wanted}
    tables = [name for name in ('export_provenance', 'export_occurrences')
              if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()]
    messages = []
    for identity in selected:
        row = by_id[identity]
        original = row['text']
        excerpt = original[:MAX_EXCERPT_CHARACTERS]
        artifact = connection.execute(
            'SELECT source_sha256,source_line FROM messages WHERE source_id=? AND conversation_id=? AND message_id=?',
            (source, conversation, identity)).fetchone()
        provenance, count = [], 0
        if tables:
            query = ' UNION '.join('SELECT original_hash,locator,parent FROM ' + name +
                ' WHERE source=? AND conversation=? AND message=?' for name in tables)
            for origin in connection.execute(query + ' ORDER BY original_hash,locator,parent',
                    (source, conversation, identity) * len(tables)):
                count += 1
                if len(provenance) < MAX_PROVENANCE_OCCURRENCES:
                    provenance.append(dict(original_sha256=origin['original_hash'],
                        locator=origin['locator'], parent_id=origin['parent']))
        messages.append(dict(message_id=identity, role=row['role'], text_excerpt=excerpt,
            excerpt_start=0, excerpt_end=len(excerpt), text_characters=len(original),
            text_truncated=len(excerpt) < len(original), source_sha256=artifact['source_sha256'],
            source_line=artifact['source_line'], export_provenance=provenance,
            export_provenance_count=count, export_provenance_truncated=count > len(provenance)))
    return dict(schema='recap.title-review-evidence.v1', content_sha256=digest,
        messages=messages, total_references=len(references), distinct_messages=len(identities),
        duplicate_references=len(references)-len(identities), returned_messages=len(messages),
        omitted_messages=len(identities)-len(messages), max_messages=MAX_MESSAGES,
        max_excerpt_characters=MAX_EXCERPT_CHARACTERS,
        max_provenance_occurrences=MAX_PROVENANCE_OCCURRENCES, contains_message_text=True,
        scope='raw archived user messages referenced by the proposal; not a branch, replay or content-attribution filter; one archive read snapshot',
        warning='PRIVATE MESSAGE TEXT AND IDENTITIES. Prefix excerpts can omit relevant passages or include harness content or discarded history excluded by scoped generation. Check truncation and omitted counts; use an exact message view for full raw text. Source labels and displayed evidence are unsigned, not proof of semantic support, privacy clearance or human approval. No model call, transmission or title change is performed.')
