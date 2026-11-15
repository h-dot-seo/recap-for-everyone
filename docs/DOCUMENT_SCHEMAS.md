# Documentation shapes for existing exchange documents

These JSON Schema files describe necessary structural conditions, not Recap
admission, authenticity, consent, permission, currentness, integrity or successful
recovery. Existing consuming commands and their Python checks remain authoritative
and can reject a document that satisfies its schema. Nothing loads these schemas
at runtime. There is no new validation CLI, source selection, remote reference
fetch or automatic write.

## Current scope

| Existing label | File | Who supplies it | Consumer and stronger checks |
| --- | --- | --- | --- |
| `recap.rebuild-plan.v1` | [rebuild plan schema](../schemas/recap.rebuild-plan.v1.schema.json) | Operator writes explicit replay steps | `rebuild-archive`: exact bounded plan reading, manifest membership, object hashes, explicit parsing/selection choices, replay and declared comparisons |

Only this already-labelled hand-authored input is covered. General stdout views,
receipts, proposals and previews do not gain labels or stability promises. This
is not an inventory of all Recap shapes. A label is not always one shape: for
example, `recap.manual-title-plan.v2` labels both a saved plan and its check result;
those forms are intentionally not included here.

The file uses the JSON Schema 2020-12 dialect URI as an identifier. It does not
require downloading the URI. It has no remote `$id` or `$ref`. Schema artifacts
are checkout documentation, not installed package files or a public validation
service. [RIGHTS.md](../RIGHTS.md) still applies; a schema is not a redistribution
license or a new permission grant.

## Rebuild plan: what is described

The top-level object has exactly `schema` and `steps`. Each step has exactly
`source`, `kind`, `object_sha256`, `label`, `conversation`, and `newline`.
The schema records the existing kind and newline enums, lowercase SHA-256
spelling, nullable/nonempty string shapes, and maximum 10,000 steps. Empty steps
are allowed by the current plan reader; they do not establish that a manifest
can be rebuilt with no objects. The schema does not manufacture a minimum of one.

These stronger constraints still belong to the unchanged consumer:

- Source identity validation, including whitespace and Unicode restrictions.
- Valid UTF-8, duplicate-key and unpaired-surrogate rejection, BOM decoding and
  the 64 MiB plan byte limit. A parsed JSON value does not preserve duplicate-key
  history or its original byte length.
- Local/local-codex replay requires a non-null original parsing label. Normalized
  replay requires null label and conversation. The first schema intentionally
  describes nullable fields without implementing these cross-field conditions.
- Declared object membership, format and selection consistency, object-byte
  hashes, import ordering, replay results and ledger comparison. Strings that
  look like hashes are not verified object contents.
- Title/review exclusions, partial publication and every version-specific rebuild
  boundary in [REBUILD_V3.md](REBUILD_V3.md) and the recovery guides.

Consequently a structurally plausible plan may fail before or during replay.
Do not change a plan just to make a structural checker accept it, infer a missing
label/order/selection, or read schema success as permission to execute it.

## Testing and numeric boundaries

Offline tests directly compare the schema's property sets, required fields,
types, enums and bounds with runtime constants and explicit expected metadata.
They exercise the unchanged consumer on valid and invalid synthetic plans.
They do not implement a general JSON Schema validator. The local development
cross-check with an already-installed standard validator is an observation, not
a new runtime/CI dependency. CI still uses the standard library only.

This first plan has no numeric-valued fields. In broader documents, JSON Schema
`integer` includes integral numbers such as `1.0`, whereas some Recap consumers
require exact Python integers and reject `1.0`; booleans are not schema integers.
Do not weaken runtime validation to make the two agree. Numeric wire extensions
such as NaN/Infinity, per-reader decoding and semantic restrictions require their
actual consumer checks; this work adds no universal input-normalization policy.

Sources: [JSON Schema numeric types](https://json-schema.org/understanding-json-schema/reference/numeric)
and [python-jsonschema validation](https://python-jsonschema.readthedocs.io/en/stable/validate/).
The schemas are deliberately incomplete structural descriptions; consumer tests
remain necessary even when an external standard validator reports no errors.

Explicit plan.v2 permits normalized selection but has no documentation schema
artifact here yet. The v1 schema is unchanged and must not be used to label v2.
See [selected normalized replay](SELECTED_NORMALIZED.md).
