"""Assemble the website into a folder of static files (code and made-up sample data only).

    python scripts/build_web.py dist/            # needs Pyodide; downloads it once into .cache/
    python scripts/build_web.py dist/ --csp      # add a strict Content-Security-Policy (for the static host)
    python scripts/build_web.py dist/ --artifact # page body only, for a private Claude page used for testing

The site runs riskcore in the browser with Pyodide (Python compiled to WebAssembly), served
from the same site: no third-party scripts, and the page makes no other network requests.
Every downloaded file is checked against a pinned SHA-256 hash.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PYODIDE_VERSION = "0.27.7"
RELEASE = f"https://github.com/pyodide/pyodide/releases/download/{PYODIDE_VERSION}/"
PINNED = {  # file -> sha256
    "pyodide.js": "b4cb23a53aba19c221659b9fb40a2f18281d685691dc06647fb0afd0681baf98",
    "pyodide.asm.js": "6b4c90de5b7172873f04f21884d0e9d2274e305fe32116558fe3e4fbe3618d51",
    "pyodide.asm.wasm": "a50dd1843f805a0b7c45b61037ee0d7b26dfe85efe0e18ef95a34ad24e401f5f",
    "python_stdlib.zip": "16611534726e5d8ac2bd8f926410b2dcb8d6f49aa24913463533b457a2115c16",
    "pyodide-lock.json": "9c45b916001a750f4102fc287494f3eab215909c7535c626a20db80fd6333e2c",
    "numpy-2.0.2-cp312-cp312-pyodide_2024_0_wasm32.whl": "ebb61241d962b98b21597d7ce43b67668a6d5bab3acec4fbe958657320d7cd08",
}
CSP = ("default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; connect-src 'self'; "
       "style-src 'self' 'unsafe-inline'; img-src 'self' data:; base-uri 'none'; form-action 'none'")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def fetch_pyodide(cache: Path) -> Path:
    d = cache / f"pyodide-{PYODIDE_VERSION}"
    if all((d / f).exists() and sha(d / f) == h for f, h in PINNED.items()):
        return d
    d.mkdir(parents=True, exist_ok=True)
    print("Downloading Pyodide (one-off, about 390 MB)...")
    with urllib.request.urlopen(RELEASE + f"pyodide-{PYODIDE_VERSION}.tar.bz2") as r:
        data = r.read()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:bz2") as t:
        for f in PINNED:
            m = t.getmember(f"pyodide/{f}")
            (d / f).write_bytes(t.extractfile(m).read())
    for f, h in PINNED.items():
        if sha(d / f) != h:
            raise SystemExit(f"Checksum mismatch for {f}: refusing to build.")
    return d


def build(out: Path, csp: bool, artifact: bool = False) -> None:
    from synthetic import generate
    from synthetic.adapters import to_dataset, to_legacy
    from synthetic.workbook_v042 import write_v042_workbook

    if out.exists():
        shutil.rmtree(out)
    (out / "vendor").mkdir(parents=True)
    (out / "pyodide").mkdir()
    web = ROOT / "web"
    for f in ("app.js", "app.css", "worker.js"):
        shutil.copy(web / f, out / f)
    html = (web / "index.html").read_text()
    html = html.replace("<!--CSP-->", f'<meta http-equiv="Content-Security-Policy" content="{CSP}">' if csp else "")
    if artifact:  # the host adds the document wrapper and blocks page-started downloads
        html = html.split("<html lang=\"en\">", 1)[1].replace("<head>", "").replace("</head>", "").replace("<body>", "")
        html = html.replace("</body>", "").replace("</html>", "").replace('<meta charset="utf-8">', "")
        html = html.replace('<meta name="viewport" content="width=device-width, initial-scale=1">', "")
    (out / "index.html").write_text(html)
    shutil.copy(ROOT / "legacy/v0_4_2/xlsx.js", out / "vendor/xlsx.js")
    shutil.copy(ROOT / "legacy/v0_4_2/engine.js", out / "vendor/engine-v042.js")
    src = {f"{pkg}/{p.name}": p.read_text() for pkg in ("riskcore", "webapp") for p in sorted((ROOT / pkg).glob("*.py"))}
    (out / "engine.json").write_text(json.dumps(src))
    p = generate()
    (out / "sample.json").write_text(json.dumps(to_legacy(to_dataset(p)), separators=(",", ":")))
    if not artifact:
        write_v042_workbook(p, out / "sample-portfolio.xlsx")
    cache = fetch_pyodide(ROOT / ".cache")
    for f in PINNED:  # archives get a .wasm suffix: some hosts refuse .zip and .whl (the bytes are unchanged)
        dest = {"python_stdlib.zip": "python_stdlib.zip.wasm", "numpy-2.0.2-cp312-cp312-pyodide_2024_0_wasm32.whl": "numpy.whl.wasm"}.get(f, f)
        shutil.copy(cache / f, out / "pyodide" / dest)
    print(f"Built {out} ({sum(f.stat().st_size for f in out.rglob('*') if f.is_file()) / 1e6:.1f} MB)")


if __name__ == "__main__":
    build(Path(sys.argv[1] if len(sys.argv) > 1 else "dist"), "--csp" in sys.argv, "--artifact" in sys.argv)
