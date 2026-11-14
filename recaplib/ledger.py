"""Read explicit import metadata, not a retention or recovery declaration."""
import json
from recaplib.archive import readonly, _validate_source
from recaplib.text_summary import summary_text

SCHEMA='recap.archive-ledger.v1'
MAX_OUTPUT_BYTES=16*1024*1024
BOUNDARY=('PRIVATE METADATA: source labels, hashes and selected conversation IDs may be private. '
    'Unledgered means no matching metadata row, not proof an import never occurred. '
    'No origin format, bytes or selection is inferred from legacy provenance or normalized artifacts. '
    'No retention, completeness, authenticity or recovery authorization is established. '
    'The original_exports table is not declared or compared by recovery manifest v1 or v2; '
    'recording a zero-message original hash does not authorize it for object rebuild. '
    'One read-only SQLite snapshot; reads can create WAL/SHM sidecars without intentionally changing main archive bytes. '
    'Output bytes are limited, but SQLite query work and process memory are not security-bounded. '
    'No network access or automatic external transmission.')


def ledger(db,source=None,limit=50,offset=0):
    if source is not None:_validate_source(source)
    if type(limit) is not int or not 1<=limit<=1000:raise ValueError('ledger limit must be an integer in 1..1000')
    if type(offset) is not int or not 0<=offset<=2**63-1:raise ValueError('ledger offset must be an integer in 0..9223372036854775807')
    connection=readonly(db)
    try:
        connection.execute('BEGIN')
        tables={row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        has_origins='original_exports' in tables
        # All SQL identifiers below are fixed program-owned table/column names.
        recorded=('EXISTS(SELECT 1 FROM original_exports x WHERE x.source=a.source_id AND x.normalized_sha256=a.sha256)'
                  if has_origins else '0')
        parts=["SELECT 'artifact' AS kind,a.source_id AS source,NULL AS original_sha256,NULL AS original_bytes,NULL AS format,NULL AS selected_conversation,a.sha256 AS normalized_sha256,NULL AS extracted_messages,a.bytes AS artifact_bytes,a.record_count AS artifact_records,"+recorded+' AS recorded FROM artifacts a']
        if has_origins:
            parts.append("SELECT 'original_export',source,original_sha256,original_bytes,format,selected_conversation,normalized_sha256,extracted_messages,NULL,NULL,1 FROM original_exports")
        provenance=[name for name in ('export_occurrences','export_provenance') if name in tables]
        if provenance:
            hashes=' UNION '.join('SELECT DISTINCT source,original_hash FROM '+name for name in provenance)
            missing=(' WHERE NOT EXISTS(SELECT 1 FROM original_exports x WHERE x.source=h.source AND x.original_sha256=h.original_hash)'
                     if has_origins else '')
            parts.append("SELECT 'unledgered_original_hash',h.source,h.original_hash,NULL,NULL,NULL,NULL,NULL,NULL,NULL,0 FROM ("+hashes+') h'+missing)
        query=' UNION ALL '.join(parts)
        where=' WHERE source=?' if source is not None else ''
        params=(source,) if source is not None else ()
        total=connection.execute('SELECT COUNT(*) FROM ('+query+')'+where,params).fetchone()[0]
        sql=('SELECT * FROM ('+query+')'+where+' ORDER BY source COLLATE BINARY,kind COLLATE BINARY,'
             'original_sha256 COLLATE BINARY,normalized_sha256 COLLATE BINARY,format COLLATE BINARY,selected_conversation COLLATE BINARY LIMIT ? OFFSET ?')
        entries=[]
        for row in connection.execute(sql,(*params,limit,offset)):
            entry=dict(kind=row['kind'],source=row['source'])
            if row['kind']=='artifact':
                entry.update(sha256=row['normalized_sha256'],bytes=row['artifact_bytes'],record_count=row['artifact_records'],
                             origin_status='recorded' if row['recorded'] else 'unledgered',
                             original_sha256=None,original_bytes=None,format=None,selected_conversation=None)
            elif row['kind']=='original_export':
                entry.update({key:row[key] for key in ('original_sha256','original_bytes','format','selected_conversation','normalized_sha256','extracted_messages')})
                if entry['selected_conversation']=='':entry['selected_conversation']=None
            else:
                entry.update(original_sha256=row['original_sha256'],original_bytes=None,format=None,selected_conversation=None)
            entries.append(entry)
        result=dict(schema=SCHEMA,entries=entries,total=total,returned=len(entries),limit=limit,offset=offset,
                    next_offset=offset+len(entries) if offset+len(entries)<total else None,
                    tables_present=sorted(tables & {'artifacts','original_exports','export_occurrences','export_provenance'}),
                    contains_message_text=False,archive_mutation=False,network_access=False,
                    retention_verified='NOT_ESTABLISHED',import_completeness='NOT_ESTABLISHED',
                    scope='one global page of stored import metadata, normalized artifacts and unledgered original hashes; not a source scan or recovery declaration',boundary=BOUNDARY)
        if len(json.dumps(result,ensure_ascii=True,indent=2,allow_nan=False).encode('ascii'))+1>MAX_OUTPUT_BYTES:
            raise ValueError('ledger output exceeds the 16 MiB limit; request a smaller page')
        return result
    finally:
        connection.close()


def render_text(result):
    return summary_text('Archive import ledger',list(result.items()))
