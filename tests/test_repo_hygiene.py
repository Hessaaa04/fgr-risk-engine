"""Guards the rule that real portfolio data never enters the repository (spec Section 2.5).

No spreadsheet, CSV or data file may be committed. Synthetic files are generated
at test time into temporary folders and are git-ignored.
"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLOCKED = {".xlsx", ".xlsm", ".xls", ".csv", ".parquet", ".pdf", ".db", ".sqlite"}
ALLOWED_JSON = {"package.json", "package-lock.json"}
MAX_BYTES = 300_000


def tracked() -> list[Path]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [ROOT / f for f in out.splitlines() if f]


def test_no_data_files_tracked():
    bad = [p for p in tracked() if p.suffix.lower() in BLOCKED or (p.suffix == ".json" and p.name not in ALLOWED_JSON)]
    assert not bad, f"Data files must not be committed: {bad}"


def test_no_large_files_tracked():
    big = [p for p in tracked() if p.exists() and p.stat().st_size > MAX_BYTES]
    assert not big, f"Unexpectedly large files: {big}"
