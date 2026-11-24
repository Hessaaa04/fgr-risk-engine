"""Write the synthetic workbooks to a folder (default: ./out, which git ignores).

    python scripts/make_synthetic.py [out_dir] [--seed N]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synthetic import generate  # noqa: E402
from synthetic.workbook import write_workbook  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?", default="out")
    ap.add_argument("--seed", type=int, default=None)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    p = generate(a.seed) if a.seed is not None else generate()
    write_workbook(p, out / "synthetic-portfolio.xlsx")
    errs = write_workbook(p, out / "synthetic-portfolio-with-errors.xlsx", with_errors=True)
    print(f"Wrote {out}/synthetic-portfolio.xlsx and the with-errors copy ({len(errs)} seeded errors).")


if __name__ == "__main__":
    main()
