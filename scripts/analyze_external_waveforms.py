"""Compatibility script; explicit intake required. Prefer lab.ps1 analyze-waveforms."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from typhoon_lab.cli import main
if __name__=="__main__":
    raise SystemExit(main(["analyze-waveforms",*sys.argv[1:]]))
