"""The website's Excel route gives the same numbers as building the dataset directly.

Writes the synthetic portfolio in the v0.4.2 workbook layout, reads it with the frozen v0.4.2
reader (legacy/v0_4_2/xlsx.js, as the website does), and runs both through webapp.bridge.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from synthetic import generate
from synthetic.adapters import to_dataset, to_legacy
from synthetic.workbook_v042 import write_v042_workbook
from webapp import bridge

ROOT = Path(__file__).resolve().parents[2]
READ = """
const XL=require(process.argv[1]+'/legacy/v0_4_2/xlsx.js'), RE=require(process.argv[1]+'/legacy/v0_4_2/engine.js'), fs=require('fs');
const b=fs.readFileSync(process.argv[2]); const wb=XL.open(b.buffer.slice(b.byteOffset,b.byteOffset+b.length));
const v=XL.findValuationSheets(wb).map(s=>XL.parseValuations(wb.sheet(s,800),s)); const h=XL.parseHistory(wb);
fs.writeFileSync(process.argv[3], JSON.stringify(RE.buildDataset(v,h.series)));
"""

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is needed to run the v0.4.2 reader")


def test_excel_route_matches_direct(tmp_path):
    p = generate()
    write_v042_workbook(p, tmp_path / "s.xlsx")
    subprocess.run(["node", "-e", READ, str(ROOT), str(tmp_path / "s.xlsx"), str(tmp_path / "ds.json")], check=True)
    st = json.dumps({"window": 36})
    bridge.load((tmp_path / "ds.json").read_text(), "2026-11-24")
    a = json.loads(bridge.run(st))
    bridge.load(json.dumps(to_legacy(to_dataset(p))), "2026-11-24")
    b = json.loads(bridge.run(st))
    assert a["as_of"] == b["as_of"] and a["N"] == b["N"]
    for k in ("vol", "var", "es", "hvar", "max_dd", "ytd"):
        assert a["headline"][k] == pytest.approx(b["headline"][k], abs=1e-12), k
    assert [h["rc"] for h in a["holdings"]] == pytest.approx([h["rc"] for h in b["holdings"]], abs=1e-12)
    assert [s["port"] for s in a["stress"]] == pytest.approx([s["port"] for s in b["stress"]], abs=1e-12)
