"""Direct CLI calls for semantic tests; real processes still own interpreter tests.

Not thread-safe: argv, cwd and standard streams are process-global. Callers must
pass the entrypoint function explicitly; no script discovery or import resolver.
"""
import io
import os
from pathlib import Path
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]


def run_cli(main, argv, cwd=ROOT):
    """Call main with argv excluding argv[0], capturing an ASCII console result."""
    saved = sys.argv, os.getcwd(), sys.stdout, sys.stderr
    out_bytes, err_bytes = io.BytesIO(), io.BytesIO()
    stdout = io.TextIOWrapper(out_bytes, encoding='ascii', errors='strict', newline='\n', write_through=True)
    stderr = io.TextIOWrapper(err_bytes, encoding='ascii', errors='backslashreplace', newline='\n', write_through=True)
    arguments = [str(value) for value in argv]
    returncode = 0
    try:
        sys.argv = [main.__module__, *arguments]
        sys.stdout, sys.stderr = stdout, stderr
        try:
            os.chdir(cwd)
            returned = main()
            if isinstance(returned, int):
                returncode = returned
        except SystemExit as error:
            if error.code is None:
                returncode = 0
            elif isinstance(error.code, int):
                returncode = error.code
            else:
                print(error.code, file=stderr)
                returncode = 1
        except BaseException:
            traceback.print_exc(file=stderr)
            returncode = 1
        stdout.flush()
        stderr.flush()
    finally:
        sys.argv, original_cwd, sys.stdout, sys.stderr = saved
        os.chdir(original_cwd)
    output = out_bytes.getvalue().decode('ascii')
    errors = err_bytes.getvalue().decode('ascii')
    stdout.close()
    stderr.close()
    return subprocess.CompletedProcess(arguments, returncode, output, errors)
