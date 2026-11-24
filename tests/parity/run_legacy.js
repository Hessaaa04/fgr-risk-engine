// Runs the frozen v0.4.2 engine on a dataset JSON and writes its analysis as JSON.
// Usage: node run_legacy.js <dataset.json> <settings.json> <out.json>
const fs = require('fs');
const path = require('path');
const RE = require(path.join(__dirname, '..', '..', 'legacy', 'v0_4_2', 'engine.js'));
const [dsPath, stPath, outPath] = process.argv.slice(2);
const ds = JSON.parse(fs.readFileSync(dsPath, 'utf8'));
const st = Object.assign(RE.defaultSettings(), JSON.parse(fs.readFileSync(stPath, 'utf8')));
const A = RE.analyse(ds, st);
if (!A.ok) { console.error('legacy engine error:', A.error); process.exit(1); }
fs.writeFileSync(outPath, JSON.stringify(A));
