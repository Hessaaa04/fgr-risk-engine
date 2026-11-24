/* Combine valuation files from different sources before the dataset is built.
   FGR has two sources for the same month: management accounts ("actuals", more accurate) and the monthly
   estimates (revised by later files). For each month exactly one file is used:
     1. a file that reports the month's return beats one that only has its value (a file's opening month);
     2. then an actuals file beats any estimates file;
     3. among files of the same kind, the one that runs to the latest month wins (it carries the revisions);
     4. a remaining tie goes to the file loaded last.
   Every other file's figures for that month are set aside and listed, so revisions are visible, never silent.
   Only the sheets that supply a month pass on their own warnings, so superseded sheets stay quiet.
   Works on the parsed sheets from the v0.4.2 reader (XL.parseValuations); the frozen reader is not changed. */
(function (root) {
  'use strict';
  var SRC = {};
  function lastYm(pv) { return pv.months.length ? pv.months[pv.months.length - 1].ym : ''; }
  function total(pv, ym) {
    var t = 0, n = 0, err = 0;
    pv.holdings.forEach(function (h) { var d = h.data[ym]; if (!d) return; if (d.val !== null && d.val !== undefined) { t += d.val; n++; } if (d.err) err++; });
    return n ? { total: t, n: n, errors: err } : null;
  }
  SRC.kindFromName = function (name) { return /actual|management/i.test(name || '') ? 'actual' : 'estimate'; };
  SRC.ymAdd = function (ym, k) { var y = +ym.slice(0, 4), m = +ym.slice(5, 7) - 1 + k; y += Math.floor(m / 12); m = ((m % 12) + 12) % 12; return y + '-' + ('0' + (m + 1)).slice(-2); };

  /* Within one file, several sheets can hold the same months (e.g. one "A+R" sheet per month, each cumulative).
     Keep, for each month, only the sheet that runs latest. */
  SRC.dedupeSheets = function (pvs) {
    var order = pvs.slice().sort(function (a, b) { return lastYm(b) < lastYm(a) ? -1 : lastYm(b) > lastYm(a) ? 1 : 0; });
    var seen = {}, out = [];
    order.forEach(function (pv) {
      var keep = pv.months.filter(function (m) { return !seen[m.ym]; }).map(function (m) { return m.ym; });
      if (!keep.length) return;
      keep.forEach(function (ym) { seen[ym] = 1; });
      out.push(SRC.only(pv, keep));
    });
    return out;
  };

  /* A copy of pv holding only the listed months. */
  SRC.only = function (pv, yms) {
    var k = {}; yms.forEach(function (y) { k[y] = 1; });
    function cut(data) { var o = {}; Object.keys(data).forEach(function (y) { if (k[y]) o[y] = data[y]; }); return o; }
    return {
      sheet: pv.sheet, file: pv.file, kind: pv.kind, layout: pv.layout, benchmarkNote: pv.benchmarkNote, issues: pv.issues || [],
      months: pv.months.filter(function (m) { return k[m.ym]; }),
      holdings: pv.holdings.map(function (h) { var c = {}; Object.keys(h).forEach(function (x) { c[x] = h[x]; }); c.data = cut(h.data); return c; }),
      sleeves: (pv.sleeves || []).map(function (s) { var c = {}; Object.keys(s).forEach(function (x) { c[x] = s[x]; }); c.data = cut(s.data); return c; }),
      total: pv.total ? { data: cut(pv.total.data) } : null
    };
  };

  /* files: [{name, kind: 'actual'|'estimate', order, pvs: [parsed sheets]}].
     Returns {vals: parsed sheets to pass to RE.buildDataset, months: {ym: {file, kind, sheet, total, n, errors, others: [...]}}, gaps: [[from, to]], issues}. */
  SRC.combine = function (files) {
    var cands = {}, issues = [];
    files.forEach(function (f, fi) {
      var withRet = f.pvs.filter(function (pv) { return pv.months.some(function (m) { return m.hasReturn; }); });
      var vo = f.pvs.filter(function (pv) { return withRet.indexOf(pv) < 0; }).map(function (pv) { return String(pv.sheet).trim(); });
      if (vo.length) issues.push({ level: 'info', text: f.name + ': ' + (vo.length === 1 ? 'sheet “' + vo[0] + '” has' : vo.length + ' sheets (' + vo.slice(0, 3).join(', ') + (vo.length > 3 ? ', …' : '') + ') have') + ' values but no monthly returns, so ' + (vo.length === 1 ? 'it is' : 'they are') + ' not used.' });
      SRC.dedupeSheets(withRet).forEach(function (pv) {
        pv.months.forEach(function (m) {
          var t = total(pv, m.ym); if (!t) return;
          (cands[m.ym] = cands[m.ym] || []).push({ file: f.name, kind: f.kind, order: fi, last: lastYm(pv), pv: pv, sheet: pv.sheet, hasReturn: m.hasReturn, total: t.total, n: t.n, errors: t.errors });
        });
      });
    });
    var rank = function (a, b) {
      if (a.hasReturn !== b.hasReturn) return a.hasReturn ? -1 : 1;  // a file's opening month carries no return; risk needs one
      if (a.kind !== b.kind) return a.kind === 'actual' ? -1 : 1;
      if (a.last !== b.last) return a.last > b.last ? -1 : 1;
      return b.order - a.order;
    };
    var months = {}, keepBy = new Map();
    Object.keys(cands).sort().forEach(function (ym) {
      var c = cands[ym].slice().sort(rank), w = c[0];
      months[ym] = {
        file: w.file, kind: w.kind, sheet: w.sheet, total: w.total, n: w.n, errors: w.errors, hasReturn: w.hasReturn,
        others: c.slice(1).map(function (o) { return { file: o.file, kind: o.kind, total: o.total, diff: w.total ? o.total / w.total - 1 : null, errors: o.errors }; })
      };
      if (!keepBy.has(w.pv)) keepBy.set(w.pv, []);
      keepBy.get(w.pv).push(ym);
      if (w.errors) issues.push({ level: 'warn', text: ym + ': ' + w.errors + ' holdings show an Excel error in ' + w.file + ', the file used for that month.' });
    });
    var vals = [];
    keepBy.forEach(function (yms, pv) { vals.push(SRC.only(pv, yms)); });
    var all = Object.keys(months).sort(), gaps = [];
    for (var i = 1; i < all.length; i++) {
      var exp = SRC.ymAdd(all[i - 1], 1);
      if (exp !== all[i]) gaps.push([exp, SRC.ymAdd(all[i], -1)]);
    }
    return { vals: vals, months: months, gaps: gaps, issues: issues };
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = SRC; else root.SRC = SRC;
})(this);
