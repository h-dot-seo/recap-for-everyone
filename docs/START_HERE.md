# Start here: from a file to a findable local title

**This tool organizes a local copy. It does not rename ChatGPT or Codex sessions
in their original app.** No account, API key, model, network or paid service is
required. Titles suggested by default are shortened user-text excerpts, not
semantic summaries. Review their meaning and private details yourself.

For a first run, complete [branch installation and runtime checks](INSTALL.md).
Use the same working launcher throughout: replace leading `python` with `python3`
or `py -3` when that is what your installation provides. The default `main` checkout
does not include all workflow commands shown here.

## Choose the input you actually have

- **Downloaded ChatGPT ZIP:** `inspect-web-zip`, explicitly select a member,
  `prepare-web-export`, then `inspect` and `import --format web` on the prepared JSON.
  See [ZIP selection](WEB_ZIP_INVENTORY.md) for hash binding, size limits and split parts.
- **Already extracted web JSON:** skip ZIP steps; `inspect` and `import --format web`.
  Supported mapping/text shapes are not a guaranteed universal or stable export schema.
- **Codex rollout JSONL:** `inspect` and `import --format local-codex`. This is raw
  extracted text, including records later rolled back. Only use
  [opt-in replay/title projection](TITLE_WALKTHROUGH.md) when its narrow grammar is supported.
- **Generic local session JSONL:** use `--format local` for the supported session/event
  shape. `local` is not a universal JSONL adapter. See [input scope](INPUT_SCOPE.md).
- **Recap-normalized JSONL:** use `ingest --source ...`, not the export import adapters.

Never guess a format from `.jsonl` alone. Inspect coverage/warnings first. Empty or
failed extraction is not permission to fabricate content or collect from an account.
Keep original files. Choose a stable `--source` label and the exact same `--db` when
returning. Source labels are your archive grouping, not verified account identities.
Do not use one label for unrelated inputs with conflicting conversation/message IDs.

Want only one conversation? Use [the export inventory](EXPORT_INVENTORY.md) to
find its exact ID before import. It lists existing web titles and extraction counts
without printing message-body fields or creating a database. Titles and IDs can
still be private. Follow the selected-import steps in [input scope](INPUT_SCOPE.md).

## Try the entire journey with 24 invented conversations

Run from the repository root with Python 3.10+ and SQLite FTS5. The example generator
reads no conversation files. It creates only a small synthetic ZIP (two parts) and
synthetic local JSONL in a **new** directory. It does not import or rename anything.
Use `../recap-start-demo` below or replace that path consistently. Its parent must
already exist; an existing directory is refused, even if empty. If creation fails
partway, inspect the partial files and choose another new directory. There is no
all-files atomicity or hostile-directory defense. Use an operator-controlled path.

The title commands below save directly with `--output NEW_JSON`: no shell `>` or
special shell encoding is needed. Files are UTF-8 without a BOM, with readable
Unicode. Use new filenames in an operator-controlled private directory whose
parent already exists. Existing files, directories and symlinks are refused,
not replaced. Publication uses a same-directory staging file and an atomic hard
link; filesystems without hard-link support fail rather than overwrite.
See [saved title documents](TITLE_DOCUMENT_FILES.md) for the full contract.

Check each exit status and stop on failure. For title commands with `--output`, stdout is only a
`recap.saved-title-json.v1` receipt with `status: SAVED`, the `document_kind`, byte
count and SHA-256, not the saved queue or preview. Check
`staging_cleanup_complete`: if false, the complete output already exists; inspect
the `remaining_staging_file` in the output directory rather than blindly retrying.
Saving is not approval. Open the actual saved JSON at the review points; do not
paste this whole page as an unattended script. The regression test executes these
arguments with synthetic inputs and checks the files written by the CLI.
Legacy examples elsewhere that still use shell `>` require UTF-8 redirection;
Windows PowerShell 5's default UTF-16 is not compatible, and `>` can overwrite
before validation.

### 1. Discover and explicitly prepare the web parts

```sh
python examples/make_review_demo.py ../recap-start-demo
python recap.py inspect-web-zip ../recap-start-demo/web.zip
python recap.py prepare-web-export ../recap-start-demo/web.zip --member conversations-001.json --output ../recap-start-demo/part-001.json
python recap.py prepare-web-export ../recap-start-demo/web.zip --member conversations-002.json --output ../recap-start-demo/part-002.json
```

The generated ZIP contains exactly two known parts, deliberately in reverse order.
For **your own** ZIP, do not copy these member names: inspect its inventory, choose
explicit members and preferably bind preparation with `--expected-archive-sha256`
using the returned digest. Metadata eligibility does not verify JSON, CRC or that
all parts exist. Parts are not automatically imported, merged or treated as one
atomic operation. The two-part completeness here is known only from this generator.

### 2. Inspect coverage, then import deliberately

```sh
python recap.py inspect ../recap-start-demo/part-001.json --format web
python recap.py inspect ../recap-start-demo/part-002.json --format web
python recap.py inspect ../recap-start-demo/local.jsonl --format local-codex
```

Inspect the reports before continuing. Each web part has six conversations, the
local file has twelve. The local demonstration combines session metadata records
for import; this does **not** make it a supported single-session replay input.
All web branches and raw local messages are retained by import, not just a currently
visible branch or effective model history. Nontext/media extraction is not supplied.

```sh
python recap.py --db ../recap-start-demo/archive.sqlite import ../recap-start-demo/part-001.json --format web --source demo
python recap.py --db ../recap-start-demo/archive.sqlite import ../recap-start-demo/part-002.json --format web --source demo
python recap.py --db ../recap-start-demo/archive.sqlite import ../recap-start-demo/local.jsonl --format local-codex --source demo
python recap.py --db ../recap-start-demo/archive.sqlite review-titles --source demo --limit 24 --output ../recap-start-demo/queue.json
```

Open `queue.json`: total 24, including two `UNAVAILABLE` assistant-only conversations
and deliberately repeated excerpts. A collision is a review hint, not a title error.
Review message context and title privacy before choosing. Queue JSON itself contains
conversation-derived text: keep it, the database and all previews private.

### 3. Defer one item, then return to it

```sh
python recap.py --db ../recap-start-demo/archive.sqlite show --source demo --conversation web-05
python recap.py --db ../recap-start-demo/archive.sqlite review-state --source demo --conversation web-05 --set deferred --from-queue ../recap-start-demo/queue.json
python recap.py --db ../recap-start-demo/archive.sqlite review-titles --source demo --state deferred --limit 24 --output ../recap-start-demo/deferred.json
```

Open `deferred.json`: just `web-05` remains. Deferring changed no title and scheduled
no reminder. `skipped` means an explicit skip; neither label means a successful
rename. Filters do not hide anything unless you request them.

### 4. Choose your wording, preview, then explicitly apply one local change

```sh
python recap.py --db ../recap-start-demo/archive.sqlite preview-title ../recap-start-demo/deferred.json --conversation web-05 --title "Synthetic orchard follow-up" --output ../recap-start-demo/reviewed.json
```

**Stop and open `reviewed.json`.** Verify the nested `proposal.source: demo`, `proposal.conversation: web-05` and
`proposal.title: Synthetic orchard follow-up`, plus top-level
`previous_title: New chat` and `expected_revision: 0`.
This is a fresh preview, not an automatic approval. Only after that review:

```sh
python recap.py --db ../recap-start-demo/archive.sqlite apply-title ../recap-start-demo/reviewed.json
python recap.py --db ../recap-start-demo/archive.sqlite title --source demo --conversation web-05
python recap.py --db ../recap-start-demo/archive.sqlite find "orchard follow-up" --source demo
python recap.py --db ../recap-start-demo/archive.sqlite review-titles --source demo --unrenamed-only --state open --limit 24 --output ../recap-start-demo/remaining.json
```

The chosen local title now appears in `find`: one matching conversation. The remaining
queue has 23 conversations. `--unrenamed-only` excludes any previous local title write,
including a no-op or reversal; it is not proof work is complete. The previous deferred
decision is stale after the title revision changes. Nothing was renamed remotely.

### 5. Revisit or recover without losing the original

```sh
python recap.py --db ../recap-start-demo/archive.sqlite review-state --source demo --conversation web-05
python recap.py --db ../recap-start-demo/archive.sqlite find "New chat" --source demo --include-title-history
```

State is now effectively `open`, with recorded `deferred` retained as stale. Historical
search can find the renamed conversation's old title, but also the other eleven web
conversations still titled `New chat`. It is not one exclusive match. Old title text
may contain information you had removed; historical search is explicitly opt-in.

To change the wording again, get a **fresh queue/proposal and preview** before apply.
Do not edit revision numbers to overcome a stale error. A reversal is another
reviewed local title change, not deletion of history or restoration of a remote title.
For current-node web or retained-turn local titles, use the more specific
[two-format walkthrough](TITLE_WALKTHROUGH.md) instead of the raw-content queue.

If you want to compare exact earlier labels before deciding, use the explicit
[`title-history` view](TITLE_HISTORY_VIEW.md). It shows bounded local change events,
current revision and archived original title without reading message-body columns.
Old titles can still be private. It is a read-only review aid, not an undo action.

## If you get stuck

- **Existing demo/output path:** choose a new path. Do not delete valuable files to retry.
- **Unsupported input or ZIP limits:** keep the original and inspect the coverage/error;
  do not rename a file extension or silently skip failing parts. See [ZIP limits](PREPARE_WEB_EXPORT.md).
- **Conflicting import identity:** the transaction is rejected. Earlier part imports
  may still exist. Inspect your source label and provenance; do not overwrite evidence.
- **No useful suggestion:** `UNAVAILABLE` or a weak excerpt is not a summary. Inspect
  the conversation; select a more useful [exact user message](TITLE_REVIEW_HINTS.md#choose-a-more-informative-user-message),
  provide explicit wording at preview for a valid proposal, or skip/defer. An unavailable queue item cannot be passed
  to `preview-title` as a generated proposal. See the operator proposal contract in README.
- **Stale preview or saved queue:** refresh at offset 0, re-read and decide again.
  Do not auto-apply the new snapshot. [Review-state details](TITLE_REVIEW_STATE.md).
- **Where did my remote title change go?** It did not: local display history only.
  The mock transfer contract is a simulation, not a platform connection.

No commands here collect accounts or send data externally. Protect generated outputs
when substituting your own data; exclude them from version control and shared folders.
