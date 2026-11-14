# Rebuild a synthetic archive from retained normalized objects

This rehearsal creates a second database from the retained JSONL, rather than
copying SQLite pages or checking the live archive against itself. It exercises
`ingest` creating new message rows and a new FTS index, followed by the existing
read-only manifest checks. There is no `rebuild-archive` command yet.

## Run the normalized-object rehearsal

Use an existing empty `OUTPUT` directory outside the repository. Confirm that
both database paths are absent before starting: `ingest` writes to an existing
database if one is supplied. These commands are **not** an exclusive database
creation wrapper. Run from the repository root with your Python launcher.
All conversation data in this example is fictional and synthetic.

```sh
python recap.py --db OUTPUT/archive.sqlite ingest examples/conversations.jsonl --source demo
python recap.py --db OUTPUT/archive.sqlite declare-recovery --output OUTPUT/rebuild-manifest.json --declared-at 2026-11-14
python recap.py --db OUTPUT/rebuilt.sqlite ingest examples/conversations.jsonl --source demo
python recap.py rehearse-recovery OUTPUT/rebuild-manifest.json --restored-db OUTPUT/rebuilt.sqlite --output OUTPUT/rebuild-receipt.json --objects examples
```

The first ingest creates the reference archive. The declaration records its
logical rows and artifacts. The second ingest reads the retained object into a
separate database with a newly built FTS index; it does not read the first DB.
The final command verifies the second DB against the declaration and should
return `RECOVERY_REHEARSAL_PASSED`, exit 0. Its `artifact_rows`,
`messages_digest`, `fts_rows` and `fts_match_sample` checks should pass. The
original archive is never modified after declaration. Retain the manifest,
receipt and original objects privately; paths, source labels and hashes are
private metadata even though receipts omit message bodies.

The exact normalized bytes, source identity and ingestion sequence must be
retained. Normalized ingest can be replayed on each supported platform because
it reads the object's bytes, not platform-translated text. This is not a promise
that arbitrary old archives rebuild under changed parsers or schemas. The
synthetic walkthrough is exercised on the supported Ubuntu/Windows and Python
matrix. DB file hashes need not match: logical checks, not SQLite page layout,
are the comparison contract.

## Boundaries and failures

- This tests retained **normalized JSONL**, not automatic export reconstruction.
  Adapter imports require reproducing format, selected conversations, source,
  label, ordering and platform newline behavior. The current manifest does not
  record a complete replay plan. Do not infer those parameters from hashes or
  claim a cross-platform adapter replay from this example.
- Title changes/history, review state and other local-only records are not
  recreated by ingesting message objects. Declared title history can therefore
  make the rehearsal fail. Review-state and other undeclared tables remain
  outside this manifest's checks; a pass does not establish their recovery.
  Use [copy restoration checks](RECOVERY_REHEARSAL.md) and retain an actual
  database backup when those records matter.
- A changed/missing object, different source or changed parser may fail checks.
  Do not edit a declaration, recovered row or source object merely to get PASS.
  Investigate the failure and keep the failed receipt. A replay failure may
  leave a partial new DB; no rollback/publication wrapper is provided here.
- The existing receipt still reports `clean_destination_verified`,
  `remote_backup_verified`, `decryption_keys_verified` and
  `future_restore_verified` as `NOT_ESTABLISHED`. It does not attest that the
  operator used a fresh directory or DB. This guide's fresh-path requirement is
  an operator step, not a new receipt claim.
- FTS checks count indexed rows and sample one token, not every possible query.
  No live DB repair, remote backup, transport, decryption, authentication,
  automatic checkpoint, replay plan or new provenance is created.
- Rehearsal receipts/manifests use exclusive output files. Repeating these exact
  commands in the same directory is not a fresh rehearsal; choose another empty
  directory rather than overwriting evidence or an existing database.
