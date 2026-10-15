"""Project entry point. Use THCC bundled Python via lab.ps1."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from typhoon_lab.cli import main
raise SystemExit(main())
