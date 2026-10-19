"""Version 1 command responses and isolation of Python/native progress output."""
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
import json
import os
import sys

COMMANDS = ('doctor', 'prepare-models', 'smoke', 'inspect', 'run', 'sweep', 'report', 'verify',
            'compare-rectifier', 'list-cases', 'validate-case', 'run-case')


def command_name(argv):
    return next((a for a in argv if a in COMMANDS), None)


def response(command, result=None, *, status=None, run_dir=None,
             experiment_status=None, record_status=None, artifacts=None, error=None):
    result = result if result is not None else {}
    state = status or result.get('status', 'passed')
    if state == 'generated':
        state = 'passed'
    return {'schema_version': 1, 'command': command, 'status': state,
            'run_dir': str(run_dir) if run_dir is not None else None,
            'record_status': record_status, 'experiment_status': experiment_status,
            'artifacts': artifacts or {}, 'result': result, 'error': error}


def emit(value, output=None):
    text = json.dumps(value, ensure_ascii=False, allow_nan=False)
    print(text, file=output or sys.stdout, flush=True)


@contextmanager
def progress_to_stderr():
    """Preserve the original response stream, including Windows native writers."""
    original = sys.stdout
    saved_fd = None
    old_handle = None
    kernel = None
    try:
        original.flush()
        sys.stderr.flush()
        try:
            # In-process tests can provide streams without file descriptors.
            original.fileno()
            sys.stderr.fileno()
        except (AttributeError, OSError, ValueError):
            pass
        else:
            saved_fd = os.dup(1)
            os.dup2(2, 1)
            if os.name == 'nt':
                import ctypes
                import msvcrt
                kernel = ctypes.WinDLL('kernel32', use_last_error=True)
                kernel.GetStdHandle.restype = ctypes.c_void_p
                kernel.SetStdHandle.argtypes = (ctypes.c_ulong, ctypes.c_void_p)
                old_handle = kernel.GetStdHandle(-11)
                kernel.SetStdHandle(-11, msvcrt.get_osfhandle(2))
        with redirect_stdout(sys.stderr):
            yield original
    finally:
        sys.stderr.flush()
        if saved_fd is not None:
            os.dup2(saved_fd, 1)
            os.close(saved_fd)
        if old_handle is not None:
            kernel.SetStdHandle(-11, old_handle)


def decorate(command, result, argv, project, failure=None):
    """Read result metadata; never verify implicitly or mutate a saved record."""
    run_dir = result.get('run_dir')
    if run_dir is None and command in ('verify', 'report') and '--run-dir' in argv:
        i = argv.index('--run-dir')
        if i + 1 < len(argv):
            p = Path(argv[i + 1])
            run_dir = str((p if p.is_absolute() else project / p).resolve())
    manifest = {}
    if run_dir:
        try:
            manifest = json.loads((Path(run_dir) / 'manifest.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
    artifacts = {k: str(Path(run_dir) / k) for k in manifest.get('artifacts', {})} if run_dir else {}
    for p in result.get('files', []):
        artifacts[Path(p).name] = str(p)
    error = failure
    if error is None and command in ('run', 'smoke', 'sweep', 'run-case') and manifest.get('status') == 'error':
        error = {'code': 'execution_error', 'stage': 'execution',
                 'message': manifest.get('error') or manifest.get('report_error') or str(manifest.get('cleanup_issues'))}
    return response(command, result, run_dir=run_dir,
                    record_status=result.get('record_status') if command in ('verify', 'run-case') else None,
                    experiment_status=result.get('experiment_status') if command in ('verify', 'run-case') else manifest.get('experiment_status', manifest.get('status')),
                    artifacts=artifacts, error=error)
