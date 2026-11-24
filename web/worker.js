/* Runs the Python calculation engine (riskcore) in the browser with Pyodide.
   Nothing here makes a network request except loading the engine's own files from this site.
   Archives are published with a .wasm suffix because some static hosts will not serve .zip or .whl files. */
importScripts('pyodide/pyodide.js');
const ready = (async () => {
  const base = new URL('pyodide/', self.location.href).href;
  const py = await loadPyodide({ indexURL: base, stdLibURL: base + 'python_stdlib.zip.wasm' });
  const whl = await (await fetch(base + 'numpy.whl.wasm')).arrayBuffer();
  py.unpackArchive(new Uint8Array(whl), 'wheel', { extractDir: '/lib/python3.12/site-packages' });
  const src = await (await fetch('engine.json')).json();
  for (const [path, text] of Object.entries(src)) {
    const dir = '/home/pyodide/' + path.split('/').slice(0, -1).join('/');
    py.FS.mkdirTree(dir);
    py.FS.writeFile('/home/pyodide/' + path, text);
  }
  py.runPython('import numpy, webapp.bridge');
  return py.pyimport('webapp.bridge');
})();
self.onmessage = async (e) => {
  const { id, fn, args } = e.data;
  try {
    const b = await ready;
    if (fn === 'ping') { self.postMessage({ id, ok: true, result: 'ready' }); return; }
    self.postMessage({ id, ok: true, result: b[fn](...args) });
  } catch (err) {
    self.postMessage({ id, ok: false, error: String(err && err.message || err).split('\n').filter(Boolean).slice(-1)[0] });
  }
};
