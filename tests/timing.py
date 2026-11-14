"""Opt-in synthetic-suite observations; no receipt files or runtime promises."""
import contextlib
import io
import json
import math
from pathlib import Path
import subprocess
import sys
import time
import unittest
from recaplib.strict_json import loads

ROOT=Path(__file__).resolve().parents[1]
SCHEMA='recap.test-timing.v1'
BOUNDARY=('Synthetic suite timing on one machine; not a performance claim. '
    'Modules run sequentially in one fresh worker process using unittest, without changing test bodies or CLI helpers. '
    'Module seconds include loading and fixtures; total includes module orchestration within the worker (not process startup). '
    'No hard duration or memory guarantee. Failure diagnostics are withheld. '
    'No receipt file is created; tests retain their existing temporary-file behavior. '
    'Receipts are local observations and must not be committed.')
COUNTS=('tests','failures','errors','skipped','expected_failures','unexpected_successes')


def module_names():
    return sorted('tests.'+path.stem for path in (ROOT/'tests').glob('test_*.py') if path.is_file() and not path.is_symlink())


def select_modules(arguments):
    allowed=module_names()
    if not arguments:return allowed
    if len(set(arguments))!=len(arguments) or any(value not in allowed for value in arguments):
        raise ValueError('select distinct published tests.test_* module names only')
    return list(arguments)


def observe(modules,loader=None,clock=time.perf_counter):
    """One worker, sequential module suites; no global subprocess monkeypatch."""
    loader=loader or unittest.TestLoader()
    started=clock();rows=[]
    for name in modules:
        begin=clock();result=unittest.TestResult()
        # Python-level output is discarded here; the parent captures fd writes
        # and inherited child-process output as well, never forwarding it.
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            suite=loader.loadTestsFromName(name)
            suite.run(result)
        row=dict(module=name,tests=result.testsRun,seconds=clock()-begin,
                 failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
                 expected_failures=len(result.expectedFailures),unexpected_successes=len(result.unexpectedSuccesses))
        rows.append(row)
    totals={key:sum(row[key] for row in rows) for key in COUNTS}
    success=not any(totals[key] for key in ('failures','errors','unexpected_successes'))
    return dict(schema=SCHEMA,interpreter=f'{sys.version_info.major}.{sys.version_info.minor}',modules=rows,
                total=dict(totals,seconds=clock()-started),success=success,boundary=BOUNDARY)


def _fixed_error():
    return dict(schema=SCHEMA,success=False,error='Timing observation could not be completed',boundary=BOUNDARY)


def _worker_main(modules):
    receipt=observe(select_modules(modules))
    # Start a fresh line even if a test wrote directly to fd 1 without a newline.
    print('\n'+json.dumps(receipt,ensure_ascii=True,allow_nan=False))
    return 0 if receipt['success'] else 1


def _valid_receipt(receipt,modules,returncode):
    if (not isinstance(receipt,dict) or set(receipt)!={'schema','interpreter','modules','total','success','boundary'} or
            receipt['schema']!=SCHEMA or receipt['boundary']!=BOUNDARY or
            receipt['interpreter']!=f'{sys.version_info.major}.{sys.version_info.minor}' or
            type(receipt['success']) is not bool or not isinstance(receipt['modules'],list) or
            len(receipt['modules'])!=len(modules)):
        return False
    for row,name in zip(receipt['modules'],modules):
        if not isinstance(row,dict) or set(row)!=set(COUNTS)|{'module','seconds'} or row['module']!=name:return False
    total=receipt['total']
    if not isinstance(total,dict) or set(total)!=set(COUNTS)|{'seconds'}:return False
    for row in [*receipt['modules'],total]:
        if any(type(row[key]) is not int or row[key]<0 for key in COUNTS):return False
        seconds=row['seconds']
        if type(seconds) not in (int,float) or not math.isfinite(seconds) or seconds<0:return False
    if any(total[key]!=sum(row[key] for row in receipt['modules']) for key in COUNTS):return False
    success=not any(total[key] for key in ('failures','errors','unexpected_successes'))
    return receipt['success']==success and returncode==(0 if success else 1)


def main(argv=None):
    args=list(sys.argv[1:] if argv is None else argv)
    try:
        modules=select_modules(args)
        # One worker for the entire selected suite. No public bypass flag, result
        # file or environment-variable transport; incidental fd output is private.
        code='import sys; from tests.timing import _worker_main; sys.exit(_worker_main(sys.argv[1:]))'
        process=subprocess.run([sys.executable,'-c',code,*modules],cwd=ROOT,capture_output=True)
        receipt=loads(process.stdout.splitlines()[-1].decode('utf-8'))
        if not _valid_receipt(receipt,modules,process.returncode):raise ValueError()
    except (OSError,ValueError,IndexError,KeyError,TypeError,RecursionError):
        receipt=_fixed_error()
    print(json.dumps(receipt,ensure_ascii=True,allow_nan=False))
    return 0 if receipt['success'] else 1


if __name__=='__main__':raise SystemExit(main())
