"""Reviewed command effects plus live argparse metadata, not authorization."""
import argparse
from pathlib import Path

from recaplib.strict_json import loads

SCHEMA = 'recap.command-catalog.v1'
BOUNDARY = ('Static effects with representative synthetic tests, not an exhaustive read-only execution audit. '
            'SQLite can create journal or sidecar files; logical read-only effects are not a filesystem sandbox. '
            'Descriptive local CLI metadata, not permission, approval, schema validation or a privacy guarantee. '
            'Options describe parser syntax; runtime cross-option validation still applies. '
            'Release is unverified text from the local publication manifest, or null. '
            'Read operations can reveal private contents on stdout. Writes may partially succeed before errors; '
            'no rollback guarantee is implied. No existing command execution, database access or network call occurs while describing.')
COMMANDS = (
    'ingest','search','stats','describe-schema','inspect','list-export','inspect-web-zip','prepare-web-export',
    'replay-local','web-branch','suggest-branch-title','suggest-replay-title','suggest-attributed-title',
    'preview-title','apply-title','review-state','render-queue','review-titles','title-adapter-dry-run',
    'title-adapter-simulate','export-title-plan','check-title-plan','import','check-import','export-normalized',
    'export-provenance','check-provenance','declare-review-checkpoint','declare-checkpoint','changed-since',
    'declare-recovery','rehearse-recovery','rebuild-archive','list','find','show','render','suggest-title','title','title-history','describe')
IGNORED_DB = frozenset(('inspect','list-export','web-branch','replay-local','prepare-web-export','inspect-web-zip','describe'))
REJECTED_DB = frozenset(('rehearse-recovery','rebuild-archive','render-queue'))
INPUT_COMMANDS = frozenset(('ingest','import','inspect','list-export','web-branch','replay-local','prepare-web-export','inspect-web-zip',
    'suggest-branch-title','suggest-replay-title','suggest-attributed-title','preview-title','apply-title',
    'render-queue','title-adapter-dry-run','title-adapter-simulate','export-title-plan','check-title-plan',
    'check-import','check-provenance','rehearse-recovery','rebuild-archive'))
TITLE_OUTPUT = frozenset(('suggest-title','suggest-branch-title','suggest-replay-title','suggest-attributed-title','preview-title','review-titles'))
DEFAULT_FILES = frozenset(('prepare-web-export','render','render-queue','export-normalized','export-provenance',
                          'declare-review-checkpoint','declare-checkpoint','declare-recovery','rehearse-recovery','rebuild-archive'))
SCHEMAS = {
    'describe':SCHEMA, 'describe-schema':'recap.archive-describe.v1',
    'inspect-web-zip':'recap.web-zip-candidates.v1','prepare-web-export':'recap.prepared-web-export.v1',
    'render':'recap.saved-view.v1','render-queue':'recap.saved-view.v1','review-titles':'recap.title-review-queue.v1',
    'export-title-plan':'recap.manual-title-plan.v2','check-title-plan':'recap.manual-title-plan.v2',
    'title-adapter-dry-run':'recap.title-transfer-request.v1','title-adapter-simulate':'recap.title-transfer-simulation.v1',
    'export-normalized':'recap.normalized-export-receipt.v1','export-provenance':'recap.message-provenance-export.v1',
    'check-provenance':'recap.message-provenance-check.v1','declare-review-checkpoint':'recap.review-checkpoint-declaration.v1',
    'declare-checkpoint':'recap.import-checkpoint-declaration.v1','changed-since':'recap.import-changes.v1',
    'declare-recovery':'recap.recovery-declaration.v1','rehearse-recovery':'recap.recovery-receipt.v1','rebuild-archive':'recap.rebuild-receipt.v1'}
RESULT_FAILURES = {'replay-local':'supported is false','check-import':'conflicts_found is true',
                  'check-provenance':'status is not PASS','changed-since':'status is not CUTOFF_VERIFIED',
                  'rebuild-archive':'status is not REBUILD_REHEARSAL_PASSED',
                  'rehearse-recovery':'status is not RECOVERY_REHEARSAL_PASSED'}


def needs_db(command):
    if command not in COMMANDS:
        raise ValueError('unknown catalog command')
    return 'ignored' if command in IGNORED_DB else 'rejected' if command in REJECTED_DB else 'required'


def _open(resource, mode='read', when='always'):
    return dict(resource=resource,mode=mode,when=when)


def _effects(name):
    writes=[];conditional=[];opens=[];notes=[];schemas=[]
    policy=needs_db(name)
    if policy=='required':
        if name in ('ingest','import','apply-title'):
            opens.append(_open('--db','write'))
            writes.append('--db')
        elif name in ('title','review-state'):
            opens.extend((_open('--db','read','without --set'),_open('--db','write','with --set')))
            conditional.append(dict(flag='--set',writes=['--db']))
        else:
            opens.append(_open('--db'))
    if name in INPUT_COMMANDS:
        opens.append(_open('input'))
    if name in DEFAULT_FILES:
        writes.append('--output')
        opens.append(_open('--output','exclusive-create'))
    if name in TITLE_OUTPUT or name=='show':
        conditional.append(dict(flag='--output',writes=['--output']))
        opens.append(_open('--output','exclusive-create','with --output'))
        schemas.append(dict(when='with --output',schema='recap.saved-document.v1' if name=='show' else 'recap.saved-title-json.v1'))
    if name=='check-import':
        conditional.append(dict(flag='--delta-output',writes=['--delta-output']))
        opens.append(_open('--delta-output','exclusive-create','with --delta-output'))
    if name=='review-titles':
        opens.extend((_open('--proposal','read','with --proposal (repeatable)'),_open('--since-checkpoint','read','with --since-checkpoint')))
    if name=='review-state':
        opens.append(_open('--from-queue','read','with --from-queue and --set'))
        notes.append('--from-queue alone is invalid: it requires --set and excludes explicit expected-value flags.')
    if name=='changed-since':
        opens.append(_open('--checkpoint'))
    if name in ('check-title-plan','title-adapter-dry-run'):
        opens.append(_open('plan'))
    if name in ('title-adapter-dry-run','title-adapter-simulate'):
        opens.append(_open('target'))
        notes.append('Mock-only transfer; simulation changes an in-memory mock, not a remote service.')
    if name=='title-adapter-simulate':
        opens.extend((_open('request'),_open('approval')))
    if name=='declare-recovery':
        schemas.append(dict(when='with --manifest-version 2',schema='recap.recovery-declaration.v2'))
    if name=='rehearse-recovery':
        schemas.append(dict(when='input manifest schema is recap.recovery-manifest.v2',schema='recap.recovery-receipt.v2'))
        opens.extend((_open('--restored-db'),_open('--objects','read','with --objects')))
    if name=='rebuild-archive':
        notes.append('Accepts v1 recovery manifests only; v2 is restored-copy rehearsal only and is rejected before rebuilding.')
        opens.extend((_open('--plan'),_open('--objects'),_open('--new-db','exclusive-create')))
        writes.append('--new-db')
        notes.append('Uses staging databases/files. A verified new DB can remain published if receipt publication fails; inspect it before retrying.')
    if name in ('ingest','import'):
        notes.append('Can create the archive/schema; schema initialization precedes the data transaction. Invalid input and failures do not imply universal rollback.')
    if name=='stats':
        schemas.append(dict(when='with --by-source',schema=None))
        notes.append('--by-source changes the JSON shape to include source/time coverage; neither form declares a schema identifier.')
    if name=='describe':
        opens.append(_open('local PUBLICATION_MANIFEST.json','read','best-effort release label only'))
    if writes or conditional:
        notes.append('Writes may create temporary/journal files; failure cleanup and partial outcomes follow each operation contract.')
    return dict(needs_db=policy,opens=opens,network='none',writes=dict(default=writes,conditional=conditional),
                output_schema=SCHEMAS.get(name),output_schema_conditional=schemas,notes=notes,
                exits={'0':'normal result; not necessarily semantic approval or completeness',
                       '1':dict(caught_error=name!='describe',result_failure=RESULT_FAILURES.get(name)),
                       '2':'argument parsing or CLI policy error'},guide='docs/COMMANDS.md')


def _options(parser):
    # argparse has no public action iterator. Restrict inspection to established
    # Action attributes; never format version-dependent usage/help strings.
    output=[]
    for action in parser._actions:
        if isinstance(action,argparse._SubParsersAction):
            continue
        output.append(dict(name=action.dest,flags=list(action.option_strings),required=bool(action.required),
            nargs=action.nargs,default=None if action.default is argparse.SUPPRESS else action.default,
            choices=list(action.choices) if action.choices is not None else None,
            type='boolean' if isinstance(action,argparse._StoreTrueAction) else 'int' if action.type is int else 'float' if action.type is float else 'text',
            action='help' if isinstance(action,argparse._HelpAction) else
                   'store_true' if isinstance(action,argparse._StoreTrueAction) else
                   'append' if isinstance(action,argparse._AppendAction) else 'store'))
    return output


def _release():
    path=Path(__file__).resolve().parents[1]/'PUBLICATION_MANIFEST.json'
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size>4*1024*1024:
            return None
        with path.open('rb') as stream:
            raw=stream.read(4*1024*1024+1)
        if len(raw)>4*1024*1024:
            return None
        value=loads(raw.decode('utf-8'))
        release=value.get('release') if isinstance(value,dict) else None
        return release if isinstance(release,str) and release else None
    except (OSError,ValueError,TypeError,RecursionError):
        return None


def _standalone():
    boundary='Reviewed effects only; standalone argument syntax remains in that module --help. Other standalone commands are outside this catalog section.'
    common=dict(needs_db='required',archive_mutation=False,guide='docs/ADAPTER_GUIDE.md',scope=boundary)
    return [dict(common,command='recaplib.title_adapter prepare',opens=['--db','--input when selected evidence scope requires it'],
                 writes=dict(default=[],conditional=[dict(flag='--output',writes=['--output'])]),
                 network='none',output_schema=None,output_schema_conditional=[dict(when='with --output',schema='recap.saved-title-json.v1')],
                 exits={'0':'result','1':'AdapterError bare code or PROVIDER_FAILED','2':'argument parsing error'}),
            dict(common,command='recaplib.title_adapter generate',opens=['--db','--input when selected evidence scope requires it','--response when supplied','--consent when supplied'],
                 writes=dict(default=[],conditional=[]),network='none in this build; external kind checks consent then raises EXTERNAL_NOT_CONFIGURED; no transport is installed',output_schema=None,
                 exits={'0':'result','1':'AdapterError bare code or PROVIDER_FAILED','2':'argument parsing error'}),
            dict(common,command='recaplib.title_adapter complete-response',opens=['--db','prepared','response','--input when selected evidence scope requires it'],
                 writes=dict(default=[],conditional=[dict(flag='--output',writes=['--output'])]),network='none; offline completion requires external-kind configuration',output_schema=None,
                 output_schema_conditional=[dict(when='with --output',schema='recap.saved-title-json.v1')],exits={'0':'result','1':'AdapterError bare code or PROVIDER_FAILED','2':'argument parsing error'}),
            dict(command='recaplib.title_proposal snapshot',needs_db='required',opens=['--db'],writes=dict(default=[],conditional=[]),
                 archive_mutation=False,network='none',output_schema=None,guide='docs/COMMANDS.md',scope=boundary,
                 exits={'0':'private raw message snapshot','1':'caught error','2':'argument parsing error'})]


def describe(parser, command=None):
    actions=[a for a in parser._actions if isinstance(a,argparse._SubParsersAction)]
    if len(actions)!=1 or set(actions[0].choices)!=set(COMMANDS):
        raise ValueError('command catalog and parser command sets differ')
    if command is not None and command not in COMMANDS:
        raise ValueError('unknown catalog command')
    selected=[command] if command is not None else sorted(COMMANDS)
    entries=[dict(command=name,options=_options(actions[0].choices[name]),**_effects(name)) for name in selected]
    for entry in entries:
        if any('--text' in option['flags'] for option in entry['options']):
            entry['notes'].append('--text selects an ASCII summary instead of JSON; output_schema describes the JSON form only.')
    return dict(schema=SCHEMA,release=_release(),global_options=_options(parser),commands=entries,
                standalone=_standalone(),boundary=BOUNDARY)
