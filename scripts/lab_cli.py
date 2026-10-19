"""Project entry point. Use THCC bundled Python via lab.ps1."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
if '--json' in sys.argv[1:]:
    from typhoon_lab.protocol import command_name, emit, response, progress_to_stderr
    failure = None
    with progress_to_stderr() as output:
        try:
            from typhoon_lab.cli import main
        except Exception as exc:
            failure = response(command_name(sys.argv[1:]), status='error', error={
                'code':type(exc).__name__, 'stage':'entry_import', 'message':str(exc)})
    if failure is not None:
        emit(failure, output)
        raise SystemExit(2)
else:
    from typhoon_lab.cli import main
raise SystemExit(main())
