/* FGR Risk Engine v2 test build: pages, file loading and charts.
   All numbers come from riskcore (Python) via worker.js. Loaded data stays in this browser tab:
   it is never uploaded and is not saved; only settings are remembered on this device. */
(function () {
  'use strict';
  var $ = function (s, el) { return (el || document).querySelector(s); };
  var $$ = function (s, el) { return Array.prototype.slice.call((el || document).querySelectorAll(s)); };
  var KEY = 'fgr-risk-engine-v2-settings';
  var PAGES = [['overview', 'Overview'], ['data', 'Data'], ['risk', 'Risk'], ['benchmarks', 'Benchmarks'], ['stress', 'Stress & scenarios'],
    ['attribution', 'Attribution'], ['liquidity', 'Liquidity'], ['illiquid', 'Illiquid assets'], ['factors', 'Factors'], ['about', 'How it works']];
  var DEF = { window: 36, conf: 0.95, as_of: null, risk_benchmark: null, perf_benchmark: null, liquidity: {}, proxies: {}, liq_target: 0.9, reverse_loss: 0.10, propagate: true, desmooth: true, assumed_betas: {}, factor_map: {},
    liqr: { min_liquid: 0.75, horizon: 60, receivables: false, suspend: 0, terms: {} } };
  var S = {
    settings: JSON.parse(JSON.stringify(DEF)), source: null, loadMsgs: [], issues: [], meta: null, R: null, busy: false,
    cmp: { names: null, period: '36', from: null, to: null }, cmpRes: null,
    scen: { shocks: {}, propagate: true, base: '' }, scenRes: null, rev: null, revLoss: 0.10,
    attr: { from: null, to: null, policy: null }, attrRes: null, liq: { files: [], res: null, month: null }, stressSel: null, hsort: { k: 'w', d: -1 }
  };
  try { var saved = JSON.parse(localStorage.getItem(KEY) || 'null'); if (saved) Object.keys(DEF).forEach(function (k) { if (saved[k] !== undefined && k !== 'as_of') S.settings[k] = k === 'liqr' ? Object.assign({}, DEF.liqr, saved[k]) : saved[k]; }); } catch (e) { /* storage unavailable */ }
  function saveSettings() { try { localStorage.setItem(KEY, JSON.stringify(S.settings)); } catch (e) { /* ignore */ } }

  // ------------------------------------------------------------ engine
  var engine = (function () {
    var w = null, seq = 0, wait = {}, fail = null;
    try { w = new Worker('worker.js'); } catch (e) { fail = 'This browser could not start the calculation engine (' + e.message + ').'; }
    if (w) {
      w.onmessage = function (e) { var d = e.data, p = wait[d.id]; if (!p) return; delete wait[d.id]; d.ok ? p.res(d.result) : p.rej(new Error(d.error)); };
      w.onerror = function (e) { fail = 'The calculation engine failed to load (' + (e.message || 'unknown error') + ').'; Object.keys(wait).forEach(function (k) { wait[k].rej(new Error(fail)); delete wait[k]; }); status(); };
    }
    function call(fn, args) {
      if (fail) return Promise.reject(new Error(fail));
      return new Promise(function (res, rej) { var id = ++seq; wait[id] = { res: res, rej: rej }; w.postMessage({ id: id, fn: fn, args: args || [] }); });
    }
    var ready = false;
    function status() {
      var el = $('#engine');
      el.className = 'engine' + (fail ? ' fail' : ready ? ' ready' : '');
      $('span', el).textContent = fail ? 'Engine not available' : ready ? 'Engine ready · runs in this browser' : 'Starting the calculation engine…';
    }
    var t0 = Date.now();
    var started = call('ping').then(function () { ready = true; status(); }, function (e) { fail = e.message; status(); throw e; });
    return { call: function (fn, args) { return started.then(function () { return call(fn, args); }).then(JSON.parse); }, status: status, started: started, ms: function () { return Date.now() - t0; } };
  })();

  // ------------------------------------------------------------ formatting
  var MINUS = '−', MN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  function ok(x) { return x !== null && x !== undefined && isFinite(x); }
  function esc(s) { return String(s === null || s === undefined ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function fx(x, d) { return Math.abs(x).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }); }
  function pct(x, d) { if (!ok(x)) return '–'; d = d === undefined ? 1 : d; return (x < 0 && +(Math.abs(x) * 100).toFixed(d) ? MINUS : '') + fx(x * 100, d) + '%'; }
  function spct(x, d) { if (!ok(x)) return '–'; d = d === undefined ? 1 : d; var r = +(x * 100).toFixed(d); return (r < 0 ? MINUS : r > 0 ? '+' : '') + fx(x * 100, d) + '%'; }
  function num(x, d) { if (!ok(x)) return '–'; d = d === undefined ? 2 : d; return (x < 0 && +Math.abs(x).toFixed(d) ? MINUS : '') + fx(x, d); }
  function money(v) { if (!ok(v)) return '–'; var a = Math.abs(v), s = a >= 1e9 ? fx(a / 1e9, 2) + 'bn' : a >= 1e6 ? fx(a / 1e6, 1) + 'm' : a >= 1e3 ? fx(a / 1e3, 0) + 'k' : fx(a, 0); return (v < 0 ? MINUS : '') + '$' + s; }
  function ym(m) { return m ? MN[+m.slice(5, 7) - 1] + ' ' + m.slice(0, 4) : ''; }
  function cls(x) { return !ok(x) || Math.abs(x) < 1e-12 ? '' : x > 0 ? 'pos' : 'neg'; }
  function short(n) { return String(n).replace(/^Synthetic /, ''); }
  function tile(k, v, d, c) { return '<div class="tile"><span class="k">' + k + '</span><span class="v ' + (c || '') + '">' + v + '</span>' + (d ? '<span class="d">' + d + '</span>' : '') + '</div>'; }
  function seg(id, val, opts) { return '<div class="seg" role="group" data-seg="' + id + '">' + opts.map(function (o) { return '<button type="button" data-v="' + esc(o[0]) + '" aria-pressed="' + (String(o[0]) === String(val)) + '">' + esc(o[1]) + '</button>'; }).join('') + '</div>'; }
  function sel(id, val, opts, attrs) { return '<select id="' + id + '" ' + (attrs || '') + '>' + opts.map(function (o) { return '<option value="' + esc(o[0]) + '"' + (String(o[0]) === String(val === null || val === undefined ? '' : val) ? ' selected' : '') + '>' + esc(o[1]) + '</option>'; }).join('') + '</select>'; }
  function ctl(label, html) { return '<label class="ctl"><span>' + label + '</span>' + html + '</label>'; }
  function toast(msg) { var t = $('#toast'); t.textContent = msg; t.style.display = 'block'; clearTimeout(toast.t); toast.t = setTimeout(function () { t.style.display = 'none'; }, 6000); }
  var PAL = ['c1', 'c2', 'c3', 'c4', 'c5', 'c6'];

  // ------------------------------------------------------------ charts
  var charts = {};
  function lineChart(id, labels, series, fmt, opts) {
    opts = opts || {};
    charts[id] = { labels: labels, series: series, fmt: fmt, zero: opts.zero };
    var lg = '<div class="legend">' + series.map(function (s) { return '<span><i style="background:var(--' + s.c + ')' + (s.dash ? ';opacity:.6' : '') + '"></i>' + esc(s.name) + '</span>'; }).join('') + '</div>';
    return lg + '<div class="chart" data-chart="' + id + '" role="img" aria-label="' + esc(opts.label || 'Line chart') + '"></div>';
  }
  function nice(span, n) { var raw = span / n, mag = Math.pow(10, Math.floor(Math.log10(raw))), f = raw / mag; return (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * mag; }
  function drawCharts() {
    $$('[data-chart]').forEach(function (el) {
      var c = charts[el.getAttribute('data-chart')]; if (!c) return;
      var W = Math.max(280, el.clientWidth || 600), H = W < 480 ? 220 : 260, m = { l: 52, r: 14, t: 10, b: 26 }, n = c.labels.length;
      var all = []; c.series.forEach(function (s) { s.values.forEach(function (v) { if (ok(v)) all.push(v); }); });
      if (c.zero) all.push(0);
      if (all.length < 2) { el.innerHTML = '<p class="sub small">Not enough data to draw this chart.</p>'; return; }
      var lo = Math.min.apply(null, all), hi = Math.max.apply(null, all), st = nice((hi - lo) || Math.abs(hi) || 1, 4);
      lo = Math.floor(lo / st) * st; hi = Math.ceil(hi / st) * st; if (hi === lo) hi = lo + st;
      var X = function (i) { return m.l + (n > 1 ? i / (n - 1) : 0.5) * (W - m.l - m.r); }, Y = function (v) { return m.t + (1 - (v - lo) / (hi - lo)) * (H - m.t - m.b); };
      var g = '<svg viewBox="0 0 ' + W + ' ' + H + '" width="100%" height="' + H + '">';
      for (var v = lo; v <= hi + st * 1e-6; v += st) g += '<line x1="' + m.l + '" x2="' + (W - m.r) + '" y1="' + Y(v).toFixed(1) + '" y2="' + Y(v).toFixed(1) + '" stroke="var(--line)"/><text x="' + (m.l - 6) + '" y="' + (Y(v) + 4).toFixed(1) + '" text-anchor="end">' + c.fmt(v, true) + '</text>';
      var every = Math.max(1, Math.ceil(n / (W < 480 ? 3 : 7)));
      for (var i = n - 1; i >= 0; i -= every) g += '<text x="' + X(i).toFixed(1) + '" y="' + (H - 7) + '" text-anchor="' + (i === n - 1 ? 'end' : 'middle') + '">' + esc(ym(c.labels[i])) + '</text>';
      c.series.forEach(function (s) {
        var d = '', pen = false;
        s.values.forEach(function (val, k) { if (ok(val)) { d += (pen ? 'L' : 'M') + X(k).toFixed(1) + ' ' + Y(val).toFixed(1); pen = true; } else pen = false; });
        g += '<path d="' + d + '" fill="none" stroke="var(--' + s.c + ')" stroke-width="' + (s.w || 2) + '"' + (s.dash ? ' stroke-dasharray="5 4"' : '') + ' stroke-linejoin="round"/>';
      });
      g += '<line class="xh" y1="' + m.t + '" y2="' + (H - m.b) + '" stroke="var(--muted)" style="display:none"/>';
      g += '<rect class="hit" x="' + m.l + '" y="' + m.t + '" width="' + (W - m.l - m.r) + '" height="' + (H - m.t - m.b) + '" fill="transparent"/></svg>';
      el.innerHTML = g;
      var svg = $('svg', el), hit = $('.hit', el), xh = $('.xh', el);
      hit.addEventListener('pointermove', function (e) {
        var r = svg.getBoundingClientRect(), x = (e.clientX - r.left) / r.width * W, k = Math.max(0, Math.min(n - 1, Math.round((x - m.l) / (W - m.l - m.r) * (n - 1))));
        xh.setAttribute('x1', X(k)); xh.setAttribute('x2', X(k)); xh.style.display = '';
        var t = $('#tip'); t.innerHTML = '<div style="opacity:.75">' + esc(ym(c.labels[k])) + '</div>' + c.series.map(function (s) { return '<div><span class="k" style="background:var(--' + s.c + ')"></span><b>' + (ok(s.values[k]) ? c.fmt(s.values[k]) : '–') + '</b> ' + esc(s.name) + '</div>'; }).join('');
        t.style.display = 'block'; var px = e.clientX + 14, py = e.clientY + 14; if (px + t.offsetWidth > innerWidth - 8) px = e.clientX - t.offsetWidth - 14; if (py + t.offsetHeight > innerHeight - 8) py = e.clientY - t.offsetHeight - 14; t.style.left = px + 'px'; t.style.top = py + 'px';
      });
      hit.addEventListener('pointerleave', function () { xh.style.display = 'none'; $('#tip').style.display = 'none'; });
    });
  }
  window.addEventListener('resize', function () { clearTimeout(drawCharts.t); drawCharts.t = setTimeout(drawCharts, 150); });
  function pairBars(rows, a, b, la, lb) { // rows: [{name, a, b}]
    var mx = Math.max.apply(null, rows.map(function (r) { return Math.max(Math.abs(r[a] || 0), Math.abs(r[b] || 0)); }).concat([1e-9]));
    return '<div class="legend"><span><i style="background:var(--c1);height:9px"></i>' + la + '</span><span><i style="background:var(--c2);height:9px"></i>' + lb + '</span></div><div class="bars">' +
      rows.map(function (r) { return '<div class="brow"><span>' + esc(short(r.name)) + '</span><div class="btrack"><div class="bar" style="background:var(--c1);width:' + (Math.max(0, r[a]) / mx * 100).toFixed(1) + '%"></div><div class="bar" style="background:var(--c2);width:' + (Math.max(0, r[b]) / mx * 100).toFixed(1) + '%"></div><div class="blab num"><span>' + pct(r[a]) + '</span><span>' + pct(r[b]) + '</span></div></div></div>'; }).join('') + '</div>';
  }
  function dbar(v, mx) { var w = mx > 0 && ok(v) ? Math.min(50, Math.abs(v) / mx * 50) : 0; return '<div class="dbar"><i class="mid"></i><i style="' + (v < 0 ? 'right' : 'left') + ':50%;width:' + w.toFixed(1) + '%;background:var(--' + (v < 0 ? 'neg' : 'pos') + ')"></i></div>'; }

  // ------------------------------------------------------------ data in
  function today() { var d = new Date(); return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2); }
  function loadDataset(dsObj, label) {
    S.busy = true; render();
    return engine.call('load', [JSON.stringify(dsObj), today()]).then(function (meta) {
      S.meta = meta; S.source = label; S.settings.as_of = null;
      ['risk_benchmark', 'perf_benchmark'].forEach(function (k) { if (S.settings[k] && !meta.series.some(function (s) { return s.name === S.settings[k]; })) S.settings[k] = null; });
      S.cmp.names = null; S.attr = { from: null, to: null, policy: null }; S.scen.shocks = {}; S.stressSel = null;
      $('#src').textContent = label;
      return recompute();
    }).catch(function (e) { S.busy = false; S.error = e.message; render(); });
  }
  function recompute() {
    S.busy = true; S.error = null; render();
    return engine.call('run', [JSON.stringify(S.settings)]).then(function (R) {
      S.R = R; S.busy = false; S.attrRes = R.attribution; S.rev = R.reverse; S.revLoss = S.settings.reverse_loss;
      if (!S.attr.policy) S.attr.policy = R.attribution.policy;
      if (!S.cmp.names) S.cmp.names = [R.perf_benchmark, R.risk_benchmark].filter(Boolean);
      return Promise.all([runCompare(true), runScenario(true)]);
    }).then(function () { render(); }).catch(function (e) { S.busy = false; S.R = null; S.error = e.message; render(); });
  }
  function cmpRange() {
    var c = S.R.complete.filter(function (m) { return m <= S.R.as_of; }), end = c[c.length - 1], p = S.cmp.period;
    if (p === 'custom' && S.cmp.from && S.cmp.to) return [S.cmp.from, S.cmp.to];
    if (p === 'ytd') return [end.slice(0, 4) + '-01', end];
    if (p === 'all') return [c[0], end];
    return [c[Math.max(0, c.length - +p)], end];
  }
  function runCompare(quiet) {
    if (!S.R) return Promise.resolve();
    var r = cmpRange();
    return engine.call('comparison', [JSON.stringify(S.cmp.names || []), r[0], r[1]]).then(function (x) { S.cmpRes = x; if (!quiet) render(); });
  }
  function runScenario(quiet) {
    if (!S.R || !S.R.factors) { S.scenRes = null; return Promise.resolve(); }
    return engine.call('scenario', [JSON.stringify(S.scen.shocks), S.scen.propagate]).then(function (x) { S.scenRes = x; if (!quiet) renderScenario(); });
  }
  function readFiles(list) {
    var files = Array.prototype.slice.call(list || []); if (!files.length) return;
    Promise.all(files.map(function (f) { return f.arrayBuffer().then(function (b) { return { name: f.name, buf: b }; }); })).then(function (items) {
      var vals = [], hist = [], msgs = [], issues = [], liqf = [];
      items.forEach(function (it) {
        try {
          if (!/\.xlsx$|\.xlsm$/i.test(it.name)) throw new Error('only .xlsx or .xlsm Excel files can be read');
          var wb = XL.open(it.buf), did = false;
          if (wb.sheetNames.some(function (n) { return /liq/i.test(n) && /terms/i.test(n); })) {
            var sh = {}; wb.sheetNames.forEach(function (n) { sh[n] = wb.sheet(n, 400); });
            liqf.push({ name: it.name, sheets: sh }); msgs.push(it.name + ': liquidity report (see the Liquidity page).'); return;
          }
          XL.findValuationSheets(wb).forEach(function (sn) {
            var pv = XL.parseValuations(wb.sheet(sn, 800), sn); pv.file = it.name; vals.push(pv); did = true;
            var m = pv.months.filter(function (x) { return x.hasReturn; });
            msgs.push(it.name + ' › ' + sn + ': ' + pv.holdings.length + ' holdings, ' + (m.length ? ym(m[0].ym) + ' to ' + ym(m[m.length - 1].ym) : 'no months') + '.');
            pv.issues.forEach(function (i) { issues.push({ level: i.level, text: it.name + ': ' + i.text }); });
          });
          if (wb.sheetNames.some(function (n) { return /^(market\s+)?(prices?|manual)/i.test(n.trim()); })) {
            var h = XL.parseHistory(wb); did = true;
            if (h.series.length) { hist = hist.concat(h.series); msgs.push(it.name + ': ' + h.series.length + ' market series.'); }
            else msgs.push(it.name + ': the market sheets are empty (saved before Bloomberg filled them).');
            h.issues.forEach(function (i) { issues.push({ level: i.level, text: it.name + ': ' + i.text }); });
          }
          if (!did) throw new Error('no “Actual Valuations” sheet and no “Market prices” or “Market manual” sheet was found');
        } catch (e) { issues.push({ level: 'error', text: 'Could not read ' + it.name + ': ' + e.message }); }
      });
      S.loadMsgs = msgs; S.issues = issues;
      if (liqf.length) {
        var keep = S.liq.files.filter(function (f) { return !liqf.some(function (g) { return g.name === f.name; }); });
        S.liq.files = keep.concat(liqf); S.liq.month = null; runLiquidity();
        if (!vals.length) { if (page() !== 'liquidity') location.hash = 'liquidity'; else render(); return; }
      }
      if (!vals.length) { S.error = 'No valuation sheet was found in the files chosen, so nothing was loaded. See the messages below.'; render(); return; }
      var ds = RE.buildDataset(vals, hist);
      ds.issues.forEach(function (i) { if (issues.indexOf(i) < 0) issues.push(i); });
      loadDataset(ds, items.map(function (i) { return i.name; }).join(', '));
    });
  }
  function runLiquidity() {
    if (!S.liq.files.length) { S.liq.res = null; return Promise.resolve(); }
    return engine.call('liquidity', [JSON.stringify(S.liq.files), JSON.stringify(S.settings.liqr)]).then(function (x) { S.liq.res = x; render(); })
      .catch(function (e) { S.error = e.message; render(); });
  }
  function loadSample() {
    fetch('sample.json').then(function (r) { return r.json(); }).then(function (ds) { S.loadMsgs = ['Sample portfolio: 27 made-up funds, Aug 2015 to Oct 2026.']; S.issues = []; loadDataset(ds, 'sample portfolio (made-up data)'); });
  }

  // ------------------------------------------------------------ routing and render
  function page() { var h = (location.hash || '').slice(1); return PAGES.some(function (p) { return p[0] === h; }) ? h : (S.R ? 'overview' : 'data'); }
  function nav() { var p = page(); $('#nav').innerHTML = PAGES.map(function (x) { return '<a href="#' + x[0] + '"' + (x[0] === p ? ' aria-current="page"' : '') + '>' + x[1] + '</a>'; }).join(''); }
  function render() {
    nav(); charts = {};
    var p = page(), h = '';
    if (S.error) h += '<div class="banner bad"><b>Something went wrong.</b> ' + esc(S.error) + '</div>';
    if (S.busy) h += '<div class="banner">Calculating…</div>';
    if (p !== 'data' && p !== 'about' && p !== 'liquidity' && !S.R) h += empty();
    else h += PAGE[p]();
    $('#main').innerHTML = h;
    drawCharts(); wire();
  }
  function empty() {
    return '<section class="panel empty"><h1>No data loaded yet</h1><p class="sub">Load your Excel workbooks or the made-up sample portfolio on the Data page. Files are read inside this browser and are never uploaded.</p><a class="btn primary" href="#data" style="text-decoration:none;display:inline-block;padding:7px 14px;border-radius:6px;background:var(--accent);color:var(--accent-ink)">Go to Data</a></section>';
  }
  function bar() { // shared settings bar for analysis pages
    var R = S.R, asofs = R.complete.slice().reverse().slice(0, 72).map(function (m) { return [m, ym(m)]; });
    return '<div class="controls">' +
      ctl('Month-end', sel('set-asof', R.as_of, asofs, 'data-set="as_of"')) +
      ctl('History used', seg('window', S.settings.window, [[36, '3 years'], [60, '5 years'], [120, '10 years']])) +
      ctl('Confidence', seg('conf', S.settings.conf, [[0.95, '95%'], [0.99, '99%']])) + '</div>';
  }
  function head(title, sub, controls) { return '<div class="pagehead"><div><h1>' + title + '</h1>' + (sub ? '<p class="sub">' + sub + '</p>' : '') + '</div>' + (controls === false ? '' : bar()) + '</div>' + sampleNote(); }
  function sampleNote() { return /sample/.test(S.source || '') ? '<div class="banner"><b>Made-up data.</b> You are looking at the sample portfolio. Load your own workbooks on the <a href="#data">Data</a> page.</div>' : ''; }

  // ------------------------------------------------------------ pages
  var PAGE = {};
  function trust(R) {
    var q = R.quality;
    return '<section class="panel"><div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap"><h2 style="margin:0">How far to trust these numbers</h2><span class="pill ' + q.label + '">' + q.label + '</span></div>' +
      '<ul class="checks">' + q.reasons.map(function (r) { return '<li><span class="' + (r.ok ? 'y' : 'n') + '">' + (r.ok ? '✓' : '!') + '</span><span>' + esc(r.text) + '</span></li>'; }).join('') + '</ul></section>';
  }
  PAGE.overview = function () {
    var R = S.R, H = R.headline, ar = R.active_risk || {}, c = Math.round(R.conf * 100) + '%';
    var h = head('Overview', 'Month-end ' + ym(R.as_of) + ' · ' + R.N + ' holdings · risk estimated from ' + R.T + ' months (' + ym(R.months[0]) + ' to ' + ym(R.as_of) + ').');
    h += trust(R);
    h += '<section class="tiles">' +
      tile('Value', money(R.aum), 'Month-end ' + ym(R.as_of)) +
      tile('Return this year', spct(H.ytd), 'Jan to ' + ym(R.as_of).slice(0, 3) + ', flows excluded', cls(H.ytd)) +
      tile('Volatility (a year)', pct(H.vol), 'Likely range ' + pct(H.vol_range[0]) + ' to ' + pct(H.vol_range[1])) +
      tile('Value at Risk, 1 month (' + c + ')', pct(H.var), '≈ ' + money(H.var * R.aum) + ' · from history ' + pct(H.hvar)) +
      tile('Expected Shortfall (' + c + ')', pct(H.es), 'Average loss in the worst ' + Math.round(100 - R.conf * 100) + '% of months') +
      tile('Worst fall, peak to trough', pct(H.max_dd), 'Over the ' + R.T + ' months used') +
      tile('Tracking error vs ' + esc(short(R.risk_benchmark || 'reference')), pct(ar.te), 'Beta ' + num(ar.beta)) +
      tile('Can be sold within a month', pct(R.liquidity.liquid), 'Target ' + pct(R.liquidity.target, 0) + (R.liquidity.shortfall > 0 ? ' · below target' : ''), R.liquidity.shortfall > 0 ? 'neg' : '') + '</section>';
    var top = (R.stress || []).filter(function (s) { return !s.error; }).slice().sort(function (a, b) { return a.port - b.port; }).slice(0, 4);
    h += '<div class="grid2"><section class="panel"><h2>Where the money is, and where the risk is</h2>' + pairBars(R.sleeves, 'w', 'rc', 'Share of value', 'Share of risk') + '</section>' +
      '<section class="panel"><h2>Risk over time (rolling ' + R.window + ' months)</h2><p class="sub small">Volatility the engine would have reported at each month-end, and what the portfolio actually did.</p>' +
      lineChart('ov-roll', R.rolling.months, [{ name: 'Estimated volatility', values: R.rolling.vol, c: 'c1' }, { name: 'Actual volatility (trailing)', values: R.rolling.realised, c: 'c2', dash: true }], function (v) { return pct(v, 0); }, { label: 'Rolling volatility' }) + '</section></div>';
    h += '<section class="panel"><h2>Biggest stress-test losses</h2><div class="scroll"><table><tr><th>Scenario</th><th class="r">Portfolio</th><th class="r">In dollars</th></tr>' +
      top.map(function (s) { return '<tr><td>' + esc(s.name) + '</td><td class="r num ' + cls(s.port) + '">' + spct(s.port) + '</td><td class="r num">' + money(s.loss_value) + '</td></tr>'; }).join('') +
      '</table></div><p class="small"><a href="#stress">All scenarios and the scenario builder →</a></p></section>';
    return h;
  };

  PAGE.data = function () {
    var h = '<div class="pagehead"><div><h1>Data</h1><p class="sub">Load the history workbook and the 2026 positions workbook together (the same files v0.4.2 reads). Files are read inside this browser tab and are never uploaded or saved. Reloading the page clears them.</p></div></div>';
    h += '<section class="panel"><div class="drop" id="drop"><b>Drop Excel files here</b><span class="sub small">or</span><div style="display:flex;gap:10px;flex-wrap:wrap;justify-content:center"><button class="btn primary" id="pick">Choose Excel files</button><button class="btn" id="sample">Use the made-up sample portfolio</button></div><input type="file" id="file" accept=".xlsx,.xlsm" multiple hidden><span class="small mut">To test the upload, use the made-up sample workbook (sample-portfolio.xlsx) sent with this link.</span></div></section>';
    if (S.loadMsgs.length || S.issues.length) {
      h += '<section class="panel"><h2>What was read</h2><ul class="checks">' + S.loadMsgs.map(function (m) { return '<li><span class="y">✓</span><span>' + esc(m) + '</span></li>'; }).join('') +
        S.issues.map(function (i) { return '<li><span class="n">' + (i.level === 'error' ? '✕' : '!') + '</span><span>' + esc(i.text) + '</span></li>'; }).join('') + '</ul></section>';
    }
    if (!S.R) return h;
    var R = S.R, M = S.meta, st = S.settings;
    var bms = M.series.filter(function (s) { return s.type === 'benchmark' || s.type === 'index'; }).map(function (s) { return [s.name, s.name]; });
    h += '<section class="panel"><h2>Settings</h2><p class="sub small">These apply on every page and are remembered on this device (the data is not).</p><div class="controls">' +
      ctl('Risk reference (for tracking error)', sel('set-rbm', R.risk_benchmark, bms, 'data-set="risk_benchmark"')) +
      ctl('Performance benchmark', sel('set-pbm', R.perf_benchmark, bms, 'data-set="perf_benchmark"')) +
      ctl('Liquidity target', sel('set-lt', st.liq_target, [[0.8, '80%'], [0.85, '85%'], [0.9, '90%'], [0.95, '95%']], 'data-set="liq_target"')) + '</div></section>';
    h += '<section class="panel"><h2>Holdings and data quality</h2><p class="sub small">Months filled means the holding had no reported return for those months in the window, so a stand-in was used. Change a holding’s liquidity or give it a stand-in index (proxy) here.</p><div class="scroll"><table><tr><th>Holding</th><th>Sleeve</th><th class="r">Weight</th><th class="r">Own months</th><th class="r">Filled</th><th>Valued</th><th>Flags</th><th>Liquid</th><th>Stand-in index</th></tr>' +
      R.holdings.map(function (x, i) {
        var f = []; if (x.stale) f.push('<span class="chip w">stale</span>'); if (x.no_data) f.push('<span class="chip b">no data</span>'); if (x.proxied) f.push('<span class="chip">proxy</span>');
        var px = [['', 'None']].concat(M.series.filter(function (s) { return s.type !== 'signal'; }).map(function (s) { return [s.name, s.name]; }));
        return '<tr><td>' + esc(short(x.name)) + '</td><td>' + esc(x.sleeve) + '</td><td class="r num">' + pct(x.w) + '</td><td class="r num">' + x.real + '</td><td class="r num' + (x.filled ? ' neg' : '') + '">' + x.filled + '</td><td>' + x.freq + '</td><td>' + f.join('') + '</td>' +
          '<td><input type="checkbox" data-liq="' + esc(x.name) + '"' + (x.liquid ? ' checked' : '') + ' aria-label="Liquid"></td><td>' + sel('px' + i, st.proxies[x.name] || '', px, 'data-proxy="' + esc(x.name) + '"') + '</td></tr>';
      }).join('') + '</table></div></section>';
    if (R.factor_roles) {
      var RL = [['', 'Not used in scenarios'], ['globalequities', 'Global equities'], ['ustreasuries', 'US Treasuries'], ['highyieldcredit', 'High yield credit'], ['usdollar', 'US dollar'], ['oil', 'Oil']];
      h += '<section class="panel"><h2>Which factor is which</h2><p class="sub small">The stress scenarios move five market factors. Check that each of your factor series is matched to the right one. A scenario that needs an unmatched factor is not run, rather than shown as zero.</p><div class="scroll"><table><tr><th>Your factor series</th><th>Used in scenarios as</th></tr>' +
        Object.keys(R.factor_roles).map(function (n, i) { return '<tr><td>' + esc(n) + '</td><td>' + sel('role' + i, st.factor_map[n] || R.factor_roles[n] || '', RL, 'data-role="' + esc(n) + '"') + '</td></tr>'; }).join('') + '</table></div></section>';
    }
    h += '<section class="panel"><h2>Market series loaded</h2><div class="scroll"><table><tr><th>Series</th><th>Type</th><th>Ticker</th><th class="r">Months</th><th>From</th><th>To</th></tr>' +
      M.series.map(function (s) { return '<tr><td>' + esc(s.name) + '</td><td>' + esc(s.type) + '</td><td>' + esc(s.ticker) + '</td><td class="r num">' + s.n + '</td><td>' + ym(s.from) + '</td><td>' + ym(s.to) + '</td></tr>'; }).join('') + '</table></div></section>';
    return h;
  };

  PAGE.risk = function () {
    var R = S.R, H = R.headline, c = Math.round(R.conf * 100) + '%';
    var h = head('Risk', 'How much the portfolio could lose in a month, and where that risk comes from. Estimated from the last ' + R.T + ' months of returns, applied to today’s holdings.');
    h += '<section class="tiles">' +
      tile('Volatility (a year)', pct(H.vol), 'Likely range ' + pct(H.vol_range[0]) + '–' + pct(H.vol_range[1])) +
      tile('VaR ' + c + ', normal', pct(H.var), money(H.var * R.aum) + ' in a month') +
      tile('ES ' + c + ', normal', pct(H.es), money(H.es * R.aum)) +
      tile('VaR ' + c + ', from history', pct(H.hvar), ok(H.hvar_range[0]) ? 'Likely range ' + pct(H.hvar_range[0]) + '–' + pct(H.hvar_range[1]) : 'Needs 24 months') +
      tile('ES ' + c + ', from history', pct(H.hes), 'Average of the worst months; leaves out the fund-specific part added for modelled funds') +
      tile('Worst fall, peak to trough', pct(H.max_dd), 'Today’s holdings over the window') + '</section>';
    h += '<section class="panel"><h2>Rolling risk</h2><p class="sub small">Each point is what the engine would have reported at that month-end using the ' + R.window + ' months before it. The dashed line is the volatility the portfolio actually had over the same trailing months. If the solid line sits well below the dashed one, the model was understating risk. Both lines are held down by funds with smoothed valuations (see Illiquid assets).</p>' +
      lineChart('rk-roll', R.rolling.months, [{ name: 'Estimated volatility', values: R.rolling.vol, c: 'c1' }, { name: 'Actual volatility', values: R.rolling.realised, c: 'c2', dash: true }, { name: 'VaR ' + c + ' (1 month)', values: R.rolling.var, c: 'c3' }], function (v) { return pct(v, 0); }, { label: 'Rolling risk' }) + '</section>';
    h += '<section class="panel"><h2>By sleeve</h2><div class="scroll"><table><tr><th>Sleeve</th><th class="r">Weight</th><th class="r">Share of risk</th><th class="r">Volatility</th><th class="r">VaR contribution</th><th class="r">Illiquid</th></tr>' +
      R.sleeves.map(function (s) { return '<tr><td>' + esc(s.name) + '</td><td class="r num">' + pct(s.w) + '</td><td class="r num">' + pct(s.rc) + '</td><td class="r num">' + pct(s.vol_a) + '</td><td class="r num">' + pct(s.cvar, 2) + '</td><td class="r num">' + pct(s.illiquid_w) + '</td></tr>'; }).join('') + '</table></div></section>';
    var k = S.hsort.k, d = S.hsort.d, rows = R.holdings.slice().sort(function (a, b) { var x = a[k], y = b[k]; return (typeof x === 'string' ? x.localeCompare(y) : (x || 0) - (y || 0)) * d; });
    var col = function (key, label, r) { return '<th class="s' + (r ? ' r' : '') + '" data-sort="' + key + '">' + label + (k === key ? (d < 0 ? ' ↓' : ' ↑') : '') + '</th>'; };
    h += '<section class="panel"><h2>By holding</h2><p class="sub small">Share of risk adds up to 100%. Marginal VaR is how much VaR changes per extra 1% in the holding; “VaR if removed” is how much VaR falls without it. Click a heading to sort.</p><div class="scroll"><table><tr>' +
      col('name', 'Holding') + col('sleeve', 'Sleeve') + col('w', 'Weight', 1) + col('vol_a', 'Volatility', 1) + col('rc', 'Share of risk', 1) + col('mvar', 'Marginal VaR', 1) + col('ivar', 'VaR if removed', 1) + '<th>Data</th></tr>' +
      rows.map(function (x) {
        var f = []; if (x.freq !== 'monthly') f.push('<span class="chip">' + x.freq + '</span>'); if (x.stale) f.push('<span class="chip w">stale</span>'); if (x.filled) f.push('<span class="chip w">' + x.filled + ' filled</span>'); if (!x.liquid) f.push('<span class="chip">illiquid</span>');
        return '<tr><td>' + esc(short(x.name)) + '</td><td>' + esc(x.sleeve) + '</td><td class="r num">' + pct(x.w) + '</td><td class="r num">' + pct(x.vol_a) + '</td><td class="r num">' + pct(x.rc) + '</td><td class="r num">' + pct(x.mvar, 2) + '</td><td class="r num">' + pct(x.ivar, 2) + '</td><td>' + f.join('') + '</td></tr>';
      }).join('') + '</table></div></section>';
    return h;
  };

  PAGE.benchmarks = function () {
    var R = S.R, C = S.cmpRes, M = S.meta;
    var h = head('Benchmarks', 'The portfolio’s actual monthly returns (money added or taken out excluded) against any benchmark or index in your market data.', false);
    var opts = M.series.filter(function (s) { return s.type !== 'signal' && s.type !== 'holding'; });
    h += '<section class="panel"><h2>Compare with</h2><div style="display:flex;flex-wrap:wrap;gap:6px 16px">' + opts.map(function (s) {
      return '<label class="small"><input type="checkbox" data-cmp="' + esc(s.name) + '"' + (S.cmp.names.indexOf(s.name) >= 0 ? ' checked' : '') + '> ' + esc(s.name) + ' <span class="mut">(' + s.type + ')</span></label>';
    }).join('') + '</div><div class="controls">' + ctl('Period', seg('cmp', S.cmp.period, [['ytd', 'This year'], ['12', '1 year'], ['36', '3 years'], ['60', '5 years'], ['all', 'All']])) + '</div></section>';
    if (!C) return h;
    var Ms = C.months, ser = [{ name: 'Portfolio', values: C.cum_port.map(function (v) { return ok(v) ? v - 1 : null; }), c: 'c1', w: 2.5 }];
    C.rows.forEach(function (r, i) { ser.push({ name: r.name, values: C.cum[r.name].map(function (v) { return ok(v) ? v - 1 : null; }), c: PAL[(i + 1) % PAL.length] }); });
    h += '<section class="panel"><h2>Growth over ' + ym(Ms[0]) + ' to ' + ym(Ms[Ms.length - 1]) + '</h2>' + lineChart('bm-cum', Ms, ser, function (v) { return spct(v, 0); }, { label: 'Cumulative return', zero: true }) + '</section>';
    var P = C.port || {};
    h += '<section class="panel"><h2>Side by side</h2><p class="sub small">Tracking error is how far the portfolio’s monthly returns stray from the benchmark’s, as a yearly figure. Information ratio is extra return per unit of tracking error. Capture compares the portfolio’s average (geometric) monthly return with the benchmark’s, over the benchmark’s up months and over its down months. Every row covers the same months. Periods under a year are not annualised. Funds with smoothed valuations make the portfolio’s actual volatility look lower than it is.</p><div class="scroll"><table><tr><th></th><th class="r">Total return</th><th class="r">A year</th><th class="r">Volatility</th><th class="r">Worst fall</th><th class="r">Ahead by</th><th class="r">Tracking error</th><th class="r">Beta</th><th class="r">Correlation</th><th class="r">Info. ratio</th><th class="r">Months ahead</th><th class="r">Up capture</th><th class="r">Down capture</th></tr>' +
      '<tr><td><b>Portfolio</b></td><td class="r num ' + cls(P.total) + '">' + spct(P.total) + '</td><td class="r num">' + spct(P.ann_return) + '</td><td class="r num">' + pct(P.vol_a) + '</td><td class="r num">' + pct(P.max_dd) + '</td><td colspan="8"></td></tr>' +
      C.rows.map(function (r) {
        if (r.dropped) return '<tr><td>' + esc(r.name) + '</td><td colspan="12" class="mut">Left out: it has fewer than 6 months of returns in this period.</td></tr>';
        if (!r.bench) return '<tr><td>' + esc(r.name) + '</td><td colspan="12" class="mut">Only ' + r.n + ' months overlap; at least 6 are needed.</td></tr>';
        return '<tr><td>' + esc(r.name) + '</td><td class="r num ' + cls(r.bench.total) + '">' + spct(r.bench.total) + '</td><td class="r num">' + spct(r.bench.ann_return) + '</td><td class="r num">' + pct(r.bench.vol_a) + '</td><td class="r num">' + pct(r.bench.max_dd) + '</td><td class="r num ' + cls(r.excess_total) + '">' + spct(r.excess_total) + '</td><td class="r num">' + pct(r.te) + '</td><td class="r num">' + num(r.beta) + '</td><td class="r num">' + num(r.corr) + '</td><td class="r num">' + num(r.ir) + '</td><td class="r num">' + pct(r.hit_rate, 0) + '</td><td class="r num">' + pct(r.up_capture, 0) + '</td><td class="r num">' + pct(r.down_capture, 0) + '</td></tr>';
      }).join('') + '</table></div></section>';
    var A = R.active_risk || {}, B = R.active_perf || {};
    h += '<section class="panel"><h2>Expected tracking error (today’s holdings)</h2><p class="sub small">Forward-looking: today’s holdings run through the last ' + R.T + ' months, against the two benchmarks chosen on the Data page.</p><div class="kv"><span>' + esc(R.risk_benchmark || '–') + '</span><span class="num">' + pct(A.te) + ' tracking error · beta ' + num(A.beta) + '</span><span>' + esc(R.perf_benchmark || '–') + '</span><span class="num">' + pct(B.te) + ' tracking error · beta ' + num(B.beta) + ' · information ratio ' + num(B.ir) + '</span></div></section>';
    return h;
  };

  PAGE.stress = function () {
    var R = S.R, h = head('Stress tests and scenarios', 'What today’s portfolio would lose if markets moved like this. Each holding’s loss is its sensitivity to five market factors times the factor moves.');
    if (!R.factors) return h + '<div class="banner warn">No market factor history is loaded, so stress tests cannot run. Load the positions workbook with its market sheets filled.</div>';
    var sel_ = S.stressSel;
    h += '<section class="panel"><h2>Scenario library</h2><p class="sub small">Historical scenarios replay what the factors did in that period (from your market data when it covers it, otherwise approximate preset moves). Click a row to see it by sleeve, or load it into the builder below.</p><div class="scroll"><table><tr><th>Scenario</th><th>Source</th><th class="r">Portfolio</th><th class="r">In dollars</th><th class="r">' + esc(short(R.risk_benchmark || 'Reference')) + '</th><th class="r">What actually happened</th><th></th></tr>' +
      R.stress.map(function (s) {
        if (s.error) return '<tr><td>' + esc(s.name) + '</td><td colspan="6" class="neg small">Not run. ' + esc(s.error) + ' Match your factors on the <a href="#data">Data</a> page.</td></tr>';
        return '<tr class="click' + (sel_ === s.id ? ' sel' : '') + '" data-stress="' + s.id + '"><td>' + esc(s.name) + (s.from ? ' <span class="mut small">' + ym(s.from) + '–' + ym(s.to) + '</span>' : '') + '</td><td><span class="chip">' + (s.src === 'data' ? 'your data' : s.src === 'preset' ? 'preset' : 'hypothetical') + '</span></td><td class="r num ' + cls(s.port) + '">' + spct(s.port) + '</td><td class="r num">' + money(s.loss_value) + '</td><td class="r num">' + spct(s.bench) + '</td><td class="r num">' + (ok(s.actual) ? spct(s.actual) : '–') + '</td><td><button class="btn" data-use="' + s.id + '" style="padding:2px 8px;font-size:.8rem">Use in builder</button></td></tr>';
      }).join('') + '</table></div>';
    if (sel_) { var s = R.stress.filter(function (x) { return x.id === sel_; })[0]; if (s) { var mx = Math.max.apply(null, s.by_sleeve.map(function (x) { return Math.abs(x.impact); }).concat([1e-9])); h += '<h3>' + esc(s.name) + ': by sleeve (contribution to the portfolio’s result)</h3><div class="bars">' + s.by_sleeve.map(function (x) { return '<div class="brow"><span>' + esc(x.name) + '</span><div>' + dbar(x.impact, mx) + '<div class="blab num"><span>' + spct(x.impact, 2) + '</span></div></div></div>'; }).join('') + '</div><p class="small mut">Factor moves: ' + R.factors.names.map(function (n, i) { return esc(n) + ' ' + spct(s.shocks[i], 1); }).join(' · ') + '</p>'; } }
    h += '</section>';
    h += '<section class="panel" id="builder"></section>';
    h += '<section class="panel" id="reverse"></section>';
    return h;
  };
  function renderScenario() {
    var el = $('#builder'); if (!el || !S.R || !S.R.factors) return;
    var F = S.R.factors, X = S.scenRes, sh = S.scen.shocks;
    var h = '<h2>Build your own scenario</h2><p class="sub small">Move any factor. Factors you leave at “not set” move the way they usually have alongside the ones you set (from their history), unless you switch that off. Results update as you move the sliders.</p>';
    h += '<div style="display:flex;gap:16px;flex-wrap:wrap;align-items:center"><label class="small"><input type="checkbox" id="prop"' + (S.scen.propagate ? ' checked' : '') + '> Let unset factors move with the ones I set</label><button class="btn" id="sc-reset">Reset all to not set</button></div><div style="display:grid;gap:8px">';
    F.names.forEach(function (n, i) {
      var set = sh[n] !== undefined && sh[n] !== null, v = set ? sh[n] : (X && X.shocks ? X.shocks[i] : 0);
      h += '<div class="slider' + (set ? '' : ' implied') + '"><label for="sl' + i + '">' + esc(n) + (set ? '' : ' <span class="mut small">(not set)</span>') + '</label><input type="range" id="sl' + i + '" min="-60" max="60" step="1" value="' + Math.round(v * 100) + '" data-fac="' + esc(n) + '"><span class="val">' + spct(v, 1) + '</span></div>';
    });
    h += '</div>';
    if (X && !X.error) {
      var mx = Math.max.apply(null, X.by_sleeve.map(function (x) { return Math.abs(x.impact); }).concat([1e-9]));
      var hs = X.holdings.slice().sort(function (a, b) { return a.impact - b.impact; }).slice(0, 8);
      h += '<div class="tiles">' + tile('Portfolio', spct(X.port), money(X.loss_value), cls(X.port)) + tile(esc(short(S.R.risk_benchmark || 'Reference')), spct(X.bench), 'Same moves') +
        tile('How unusual, as a one-month move', ok(X.sigma) ? num(X.sigma, 1) + ' σ' : '–', (X.sigma > 4 ? 'Very extreme for a single month' : X.sigma > 2.5 ? 'Severe but has happened' : 'Within normal experience') + '. Multi-month crises score high here.') + '</div>';
      h += '<div class="grid2"><div><h3>By sleeve</h3><div class="bars">' + X.by_sleeve.map(function (x) { return '<div class="brow"><span>' + esc(x.name) + '</span><div>' + dbar(x.impact, mx) + '<div class="blab num"><span>' + spct(x.impact, 2) + '</span></div></div></div>'; }).join('') + '</div></div>' +
        '<div><h3>Holdings hit hardest</h3><table><tr><th>Holding</th><th class="r">Its move</th><th class="r">Effect on portfolio</th></tr>' + hs.map(function (x) { return '<tr><td>' + esc(short(x.name)) + '</td><td class="r num ' + cls(x.shock) + '">' + spct(x.shock) + '</td><td class="r num ' + cls(x.impact) + '">' + spct(x.impact, 2) + '</td></tr>'; }).join('') + '</table></div></div>';
    }
    el.innerHTML = h;
    $$('input[data-fac]', el).forEach(function (inp) {
      inp.addEventListener('input', function () { inp.nextElementSibling.textContent = spct(inp.value / 100, 1); });
      inp.addEventListener('change', function () { S.scen.shocks[inp.getAttribute('data-fac')] = inp.value / 100; runScenario(); });
    });
    $('#prop', el).addEventListener('change', function (e) { S.scen.propagate = e.target.checked; runScenario(); });
    $('#sc-reset', el).addEventListener('click', function () { S.scen.shocks = {}; runScenario(); });
    renderReverse();
  }
  function renderReverse() {
    var el = $('#reverse'); if (!el) return;
    var V = S.rev, F = S.R.factors;
    var h = '<h2>Reverse stress test</h2><p class="sub small">Instead of asking “what if”, this asks: what is the most likely combination of factor moves that causes a given loss?</p><div class="slider"><label for="rl">Loss to explain</label><input type="range" id="rl" min="2" max="40" step="1" value="' + Math.round(S.revLoss * 100) + '"><span class="val">' + pct(S.revLoss, 0) + '</span></div>';
    if (V) h += '<p>The most likely way to lose ' + pct(S.revLoss, 0) + ' (' + money(S.revLoss * S.R.aum) + ') in a month is roughly: ' + F.names.map(function (n, i) { return '<b>' + esc(n) + ' ' + spct(V.shocks[i], 0) + '</b>'; }).join(', ') + '. That is a ' + num(V.sigma_m, 1) + '-standard-deviation month; ' + (V.sigma_m > 4 ? 'very unlikely, but not impossible.' : V.sigma_m > 2.5 ? 'rare, roughly a few times a century or less.' : 'something that happens from time to time.') + '</p>';
    el.innerHTML = h;
    var r = $('#rl', el);
    r.addEventListener('input', function () { r.nextElementSibling.textContent = pct(r.value / 100, 0); });
    r.addEventListener('change', function () { S.revLoss = r.value / 100; engine.call('reverse', [S.revLoss]).then(function (x) { S.rev = x; renderReverse(); }); });
  }

  PAGE.attribution = function () {
    var R = S.R, A = S.attrRes, M = S.meta;
    var h = head('Attribution', 'Why the portfolio did better or worse than its benchmark: the asset mix (allocation) or the funds chosen within each sleeve (selection). Brinson-Fachler, linked across months.', false);
    var av = (A.available || []).map(function (m) { return [m, ym(m)]; });
    var idx = [['', 'None']].concat(M.series.filter(function (s) { return s.type !== 'signal'; }).map(function (s) { return [s.name, s.name]; }));
    h += '<section class="panel"><div class="controls">' + ctl('From', sel('at-from', A.from, av)) + ctl('To', sel('at-to', A.to, av)) + '</div>' +
      '<h3>Benchmark mix</h3>' + (A.is_default ? '<p class="small"><span class="chip w">placeholder</span> 35% equities and 65% bonds until you enter your performance benchmark’s real mix.</p>' : '') +
      '<div class="scroll"><table><tr><th>Sleeve</th><th>Weight %</th><th>Index used for the sleeve</th></tr>' + A.policy.map(function (p, i) { return '<tr><td>' + esc(p.sleeve) + '</td><td><input type="number" min="0" max="100" step="1" value="' + (+p.weight || 0) + '" data-pw="' + i + '" style="width:80px"></td><td>' + sel('ps' + i, p.series, idx, 'data-ps="' + i + '"') + '</td></tr>'; }).join('') + '</table></div><div><button class="btn primary" id="at-run">Recalculate</button></div></section>';
    if (!A.ok) h += '<div class="banner warn">' + esc(A.reason || 'Attribution is not available.') + '</div>';
    else {
      if (A.own_return_classes && A.own_return_classes.length) h += '<div class="banner warn"><b>No index chosen for ' + esc(A.own_return_classes.join(', ')) + '.</b> For those sleeves the benchmark uses the portfolio’s own return, so they show no selection effect and the benchmark total is partly the portfolio’s own result.</div>';
      h += '<section class="tiles">' + tile('Portfolio', spct(A.Rp), ym(A.from) + ' to ' + ym(A.to), cls(A.Rp)) + tile('Benchmark', spct(A.Rb), 'Weighted index returns', cls(A.Rb)) + tile('Difference', spct(A.excess, 2), 'Allocation ' + spct(A.alloc_total, 2) + ' · selection ' + spct(A.sel_total, 2), cls(A.excess)) + '</section>';
      var mx = Math.max.apply(null, A.sleeves.map(function (s) { return Math.max(Math.abs(s.alloc), Math.abs(s.sel)); }).concat([1e-9]));
      h += '<section class="panel"><h2>By sleeve</h2><div class="scroll"><table><tr><th>Sleeve</th><th class="r">Benchmark weight</th><th class="r">Allocation</th><th style="min-width:120px"></th><th class="r">Selection</th><th style="min-width:120px"></th><th class="r">Total</th></tr>' +
        A.sleeves.map(function (s) { return '<tr><td>' + esc(s.name) + '</td><td class="r num">' + pct(s.wb, 0) + '</td><td class="r num ' + cls(s.alloc) + '">' + spct(s.alloc, 2) + '</td><td>' + dbar(s.alloc, mx) + '</td><td class="r num ' + cls(s.sel) + '">' + spct(s.sel, 2) + '</td><td>' + dbar(s.sel, mx) + '</td><td class="r num ' + cls(s.total) + '">' + spct(s.total, 2) + '</td></tr>'; }).join('') + '</table></div></section>';
    }
    if (A.contrib) {
      var top = A.contrib.slice(0, 6), bot = A.contrib.slice(-6).reverse().filter(function (x) { return x.c < 0; });
      var t = function (rows) { return '<table>' + rows.map(function (x) { return '<tr><td>' + esc(short(x.name)) + '</td><td class="mut">' + esc(x.sleeve) + '</td><td class="r num ' + cls(x.c) + '">' + spct(x.c, 2) + '</td></tr>'; }).join('') + '</table>'; };
      h += '<div class="grid2"><section class="panel"><h2>Added the most</h2>' + t(top) + '</section><section class="panel"><h2>Cost the most</h2>' + (bot.length ? t(bot) : '<p class="sub small">No holding lost money in this period.</p>') + '</section></div>';
    }
    return h;
  };

  PAGE.liquidity = function () {
    var st = S.settings.liqr, L = S.liq.res;
    var h = '<div class="pagehead"><div><h1>Liquidity</h1><p class="sub">How much of the portfolio can be turned into cash, and how fast. Load the monthly liquidity report (the “Liquidity Profile” workbook); load several months to see the trend. Files are read in this browser and never uploaded.</p></div></div>';
    h += '<section class="panel"><div class="drop" id="drop"><b>Drop liquidity reports here</b><span class="sub small">or</span><div style="display:flex;gap:10px;flex-wrap:wrap;justify-content:center"><button class="btn primary" id="pick">Choose Excel files</button><button class="btn" id="liq-sample">Use a made-up report</button>' + (S.liq.files.length ? '<button class="btn" id="liq-clear">Clear</button>' : '') + '</div><input type="file" id="file" accept=".xlsx,.xlsm" multiple hidden>' +
      (S.liq.files.length ? '<span class="small mut">Loaded: ' + esc(S.liq.files.map(function (f) { return f.name; }).join(', ')) + '</span>' : '<span class="small mut">Your file’s layout must match the monthly report: a “Portfolio Liq. Terms &amp; NAV” sheet with Name and Max Days columns.</span>') + '</div></section>';
    if (!L) return h;
    (L.issues || []).forEach(function (i) { h += '<div class="banner ' + (i.level === 'error' ? 'bad' : 'warn') + '">' + esc(i.text) + '</div>'; });
    if (!L.profiles.length) return h;
    var n = L.profiles.length, k = S.liq.month === null ? n - 1 : Math.min(S.liq.month, n - 1), A = L.profiles[k], lim = A.limit;
    var months = L.profiles.map(function (a, i) { return [i, (a.as_of || a.file) + (a.file ? ' · ' + a.file : '')]; });
    h += '<div class="controls">' + (n > 1 ? ctl('Report', sel('liq-month', k, months)) : '') +
      ctl('Receivables', seg('liq-rec', st.receivables ? 1 : 0, [[0, 'Left out'], [1, 'Included']])) +
      ctl('Limit: at least', '<span><input type="number" id="liq-min" min="0" max="100" step="1" value="' + Math.round(st.min_liquid * 100) + '" style="width:64px"> % in cash within</span>') +
      ctl('Days', sel('liq-h', st.horizon, [[5, '5 days'], [15, '15 days'], [40, '40 days'], [60, '60 days'], [90, '90 days'], [180, '180 days'], [365, '1 year']])) +
      ctl('Stress: quarterly funds suspend', '<span><input type="range" id="liq-sus" min="0" max="100" step="5" value="' + Math.round(st.suspend * 100) + '" style="width:120px"> <b class="num">' + Math.round(st.suspend * 100) + '%</b></span>') + '</div>';
    var okc = lim.ok ? 'pos' : 'neg';
    h += '<div class="tiles">' +
      tile('Assets (' + esc(A.as_of || '') + ')', money(A.aum), st.receivables ? 'Including receivables' : 'Excluding receivables') +
      tile('Cash and deposits', pct(A.cash), 'Principal only') +
      tile('Liquid (up to 60 days)', pct(A.liquid), 'Plus cash: ' + pct(A.liquid_incl_cash)) +
      tile('Illiquid', pct(A.illiquid_for_limits), A.unknown ? 'Includes ' + pct(A.unknown) + ' with terms missing' : 'Over 60 days or no redemption right') +
      tile('In cash within ' + lim.horizon + ' days', pct(lim.available), (lim.ok ? 'Meets' : 'Below') + ' the ' + pct(lim.min_liquid, 0) + ' limit (' + spct(lim.headroom) + ')', okc) +
      tile('Same, under stress', pct(lim.stressed), st.suspend ? Math.round(st.suspend * 100) + '% of quarterly funds suspended' : 'Move the stress slider', lim.stressed_ok ? 'pos' : 'neg') + '</div>';

    var KC = { cash: 'c3', liquid: 'c1', illiquid: 'c2', unknown: 'c6' }, op = [1, 0.85, 0.65, 0.45, 0.3];
    var cnt = { cash: 0, liquid: 0, illiquid: 0, unknown: 0 };
    var B = A.buckets.map(function (b) { b.c = KC[b.kind]; b.o = op[cnt[b.kind]++] || 0.3; return b; });
    var rep = {}; (A.reconciliation || []).forEach(function (r) { if (r.bucket) rep[r.bucket] = r; });
    h += '<section class="panel"><h2>By how fast it can be sold</h2><div style="display:flex;height:26px;border-radius:6px;overflow:hidden;margin:6px 0 12px" role="img" aria-label="Share of assets in each liquidity bucket">' +
      B.filter(function (b) { return b.share > 0; }).map(function (b) { return '<div title="' + esc(b.name) + ': ' + pct(b.share) + '" style="width:' + (b.share * 100).toFixed(2) + '%;background:var(--' + b.c + ');opacity:' + b.o + '"></div>'; }).join('') + '</div>' +
      '<div class="scroll"><table><tr><th>Bucket</th><th>Counts as</th><th class="r">Value</th><th class="r">Share</th>' + (Object.keys(rep).length ? '<th class="r">Report’s own figure</th><th class="r">Difference</th>' : '') + '</tr>' +
      B.map(function (b) {
        var r = rep[b.key];
        return '<tr><td><span class="k" style="display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;background:var(--' + b.c + ');opacity:' + b.o + '"></span>' + esc(b.name) + '</td><td>' + b.kind + '</td><td class="r num">' + money(b.value) + '</td><td class="r num">' + pct(b.share) + '</td>' +
          (Object.keys(rep).length ? '<td class="r num">' + (r ? money(r.report) : '–') + '</td><td class="r num' + (r && Math.abs(r.diff_share) >= 0.0005 ? ' neg' : '') + '">' + (r ? (Math.abs(r.diff_share) >= 0.0005 ? money(r.diff) + ' (' + spct(r.diff_share, 2) + ')' : 'ties') : '–') + '</td>' : '') + '</tr>';
      }).join('') + '</table></div><p class="small mut">Each holding is placed from its own terms: its timeline and its maximum days to cash, taken as the worst case from the decision to sell until cash arrives (notice, dealing date and settlement). Nothing is added to it. Liquid means 60 days or fewer, as in the report.</p></section>';

    var mx = 1;
    h += '<section class="panel"><h2>Days to cash</h2><p class="sub small">Share of assets that could be in cash within each number of days. “With your terms” applies the gates, lock-ups and fees entered below; “under stress” also suspends the chosen share of quarterly and less frequent funds.</p><div class="scroll"><table><tr><th>Within</th><th class="r">Contractual</th><th class="r">With your terms</th><th class="r">Under stress</th><th style="width:40%"></th></tr>' +
      A.ladder.map(function (x) {
        var w = function (v, c, o) { return '<div style="height:6px;border-radius:3px;margin:2px 0;width:' + (Math.max(0, v || 0) / mx * 100).toFixed(1) + '%;background:var(--' + c + ');opacity:' + o + '"></div>'; };
        return '<tr' + (x.days === lim.horizon ? ' style="font-weight:600"' : '') + '><td>' + x.days + (x.days === 1 ? ' day' : ' days') + '</td><td class="r num">' + pct(x.share) + '</td><td class="r num">' + pct(x.with_terms_share) + '</td><td class="r num ' + (x.days === lim.horizon ? (x.stressed_share >= lim.min_liquid ? 'pos' : 'neg') : '') + '">' + pct(x.stressed_share) + '</td><td>' + w(x.share, 'c1', 0.35) + w(x.with_terms_share, 'c1', 0.7) + w(x.stressed_share, 'c2', 1) + '</td></tr>';
      }).join('') + '</table></div>' + A.not_captured.map(function (t) { return '<p class="small"><span class="chip w">not captured</span> ' + esc(t) + '</p>'; }).join('') + '</section>';

    if (A.checks.length) h += '<section class="panel"><h2>Checks on this report</h2><ul class="checks">' + A.checks.map(function (c) { return '<li><span class="n">' + (c.level === 'error' ? '✕' : c.level === 'warn' ? '!' : 'i') + '</span><span><b>' + esc(c.name) + '</b> ' + esc(c.text) + '</span></li>'; }).join('') + '</ul></section>';

    var BN = {}; L.buckets.forEach(function (b) { BN[b.key] = b.name; });
    h += '<section class="panel"><h2>Holdings and terms</h2><p class="sub small">Gates, lock-ups and fees are only in the report’s comments, so the engine does not read them from the text. Enter them here to apply them; they are remembered on this device.</p><div class="scroll"><table><tr><th>Holding</th><th>Class</th><th class="r">Value</th><th class="r">Share</th><th>Bucket</th><th class="r">Max days</th><th>Timeline</th><th>Proceeds</th><th>Report label</th><th>Gate % per dealing date</th><th>Lock-up ends</th><th>Fee %</th><th>Comments</th></tr>' +
      A.rows.map(function (r) {
        var t = st.terms[r.name] || {}, can = ['maturity', 'permanent', 'cash', 'unknown'].indexOf(r.bucket) < 0;
        var inp = function (key, type, v, w) { return can ? '<input type="' + type + '" data-lt="' + esc(r.name) + '" data-k="' + key + '" value="' + (v === undefined || v === null ? '' : v) + '" style="width:' + w + '"' + (type === 'number' ? ' min="0" max="100" step="1"' : '') + '>' : ''; };
        var mism = r.label && r.kind !== r.label && (r.kind === 'liquid' || r.kind === 'illiquid');
        return '<tr><td>' + esc(r.name) + '</td><td>' + esc(r.asset_class) + '</td><td class="r num">' + money(r.value) + '</td><td class="r num">' + pct(r.w) + '</td><td>' + (r.bucket === 'unknown' ? '<span class="chip b">terms missing</span>' : esc(BN[r.bucket])) + '</td><td class="r num">' + (r.no_redemption ? 'none' : r.max_days === null ? '–' : r.max_days) + '</td><td>' + esc(r.timeline) + '</td><td>' + esc(r.payment) + '</td><td>' + esc(r.label) + (mism ? ' <span class="chip w">differs</span>' : '') + '</td>' +
          '<td>' + inp('gate', 'number', t.gate === undefined || t.gate === null ? '' : Math.round(t.gate * 100), '64px') + '</td><td>' + inp('lockup_end', 'date', t.lockup_end, '130px') + '</td><td>' + inp('fee', 'number', t.fee === undefined || t.fee === null ? '' : +(t.fee * 100).toFixed(2), '56px') + '</td><td class="small">' + esc(r.comments) + '</td></tr>';
      }).join('') + '</table></div></section>';

    if (n > 1) {
      h += '<section class="panel"><h2>Month by month</h2><div class="scroll"><table><tr><th></th>' + L.profiles.map(function (a) { return '<th class="r">' + esc(a.as_of || a.file) + '</th>'; }).join('') + '</tr>' +
        '<tr><td>Assets</td>' + L.profiles.map(function (a) { return '<td class="r num">' + money(a.aum) + '</td>'; }).join('') + '</tr>' +
        L.buckets.filter(function (b) { return L.profiles.some(function (a) { return a.buckets.some(function (x) { return x.key === b.key && x.share; }); }); }).map(function (b) {
          return '<tr><td>' + esc(b.name) + '</td>' + L.profiles.map(function (a) { var x = a.buckets.filter(function (y) { return y.key === b.key; })[0]; return '<td class="r num">' + pct(x ? x.share : null) + '</td>'; }).join('') + '</tr>';
        }).join('') +
        '<tr><td><b>In cash within ' + st.horizon + ' days</b></td>' + L.profiles.map(function (a) { return '<td class="r num ' + (a.limit.ok ? 'pos' : 'neg') + '"><b>' + pct(a.limit.available) + '</b></td>'; }).join('') + '</tr></table></div>';
      var ch = (L.change || []).filter(function (c) { return c.moved || c.new || c.gone; });
      if (ch.length) h += '<h3>What changed since the previous report</h3><ul class="checks">' + ch.map(function (c) { return '<li><span class="n">!</span><span><b>' + esc(c.name) + '</b> ' + (c.new ? 'is new.' : c.gone ? 'is no longer in the report.' : 'moved from “' + esc(BN[c.bucket_before]) + '” to “' + esc(BN[c.bucket_after]) + '”.') + '</span></li>'; }).join('') + '</ul>';
      h += '</section>';
    }
    return h;
  };

  PAGE.illiquid = function () {
    var R = S.R, st = S.settings, h = head('Illiquid assets', 'Funds valued by appraisal or by the manager (property, private equity, strategic holdings, many hedge funds) report smoothed or infrequent returns. Left alone, they look steadier and less linked to markets than they are, and the portfolio’s risk is understated.', false);
    h += '<section class="panel"><div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap"><h2 style="margin:0">Correction for smoothed returns</h2>' + seg('desm', st.desmooth ? 1 : 0, [[1, 'On'], [0, 'Off (as v0.4.2)']]) + '</div>' +
      '<p class="sub small">When on, every risk figure in the app uses the corrected returns below. Switch it off to see how much difference it makes.</p>';
    var A = R.adjustments || [];
    if (!st.desmooth) h += '<p class="small"><span class="chip w">off</span> Risk is calculated from the returns as reported.</p>';
    else if (!A.length) h += '<p class="small mut">No holding needed a correction.</p>';
    else h += '<div class="scroll"><table><tr><th>Holding</th><th>Valued</th><th>What was done</th><th class="r">Smoothing (φ)</th><th class="r">Equity beta used</th><th class="r">Based on</th><th class="r">Fund-specific volatility added</th></tr>' +
      A.map(function (x) {
        var m = x.method === 'desmoothed' ? 'Desmoothed' + (x.phi_capped ? ' <span class="chip w">φ capped at 0.7</span>' : '') : x.method === 'factor model' ? 'Modelled from equities (this quarter and last)' + (x.phi_floored ? ' <span class="chip w">smoothing assumed 0.5</span>' : '') : x.method === 'assumed beta' ? '<span class="chip w">your assumption</span> Modelled from equities' : '<span class="chip b">needs your input</span>';
        return '<tr><td>' + esc(short(x.name)) + '</td><td>' + x.freq + '</td><td>' + m + '</td><td class="r num">' + num(x.phi) + '</td><td class="r num">' + num(x.beta) + '</td><td class="r num">' + (x.method === 'desmoothed' ? x.n + ' months' : x.method === 'factor model' ? x.n + ' quarters' : '–') + '</td><td class="r num">' + pct(x.resid_vol_a) + '</td></tr>';
      }).join('') + '</table></div>';
    var yearly = A.filter(function (x) { return x.freq === 'annual'; });
    if (st.desmooth && yearly.length) {
      h += '<h3>Funds valued once a year</h3><p class="sub small">About ten yearly values cannot support an estimate, so these need your judgement: how much does each tend to move when global equities move 1%? (For example 0.5 for core property, 1.0 or more for a private company.) Leave blank to keep the reported returns, which understate risk.</p><div class="scroll"><table><tr><th>Holding</th><th>Assumed equity beta</th></tr>' +
        yearly.map(function (x, i) { var v = st.assumed_betas[x.name]; return '<tr><td>' + esc(short(x.name)) + '</td><td><input type="number" step="0.1" min="-1" max="3" id="ab' + i + '" data-ab="' + esc(x.name) + '" value="' + (v === undefined ? '' : v) + '" style="width:90px"></td></tr>'; }).join('') +
        '</table></div>';
    }
    h += '</section>';
    h += '<section class="panel"><h2>How smoothed each fund looks</h2><div class="scroll"><table><tr><th>Holding</th><th>Sleeve</th><th class="r">Weight</th><th>Valued</th><th class="r">Months</th><th class="r">Volatility reported</th><th class="r">After desmoothing</th><th class="r">Smoothing (φ)</th><th class="r">Link to equities, reported</th><th class="r">After desmoothing</th></tr>' +
      R.illiquid.map(function (x) {
        return '<tr><td>' + esc(short(x.name)) + '</td><td>' + esc(x.sleeve) + '</td><td class="r num">' + pct(x.w) + '</td><td>' + x.freq + '</td><td class="r num">' + x.n + '</td><td class="r num">' + pct(x.obs_vol) + '</td><td class="r num">' + pct(x.desm_vol) + '</td><td class="r num">' + num(x.phi) + '</td><td class="r num">' + num(x.eq_obs) + '</td><td class="r num">' + num(x.eq_desm) + '</td></tr>';
      }).join('') + '</table></div><p class="small mut">Desmoothing (Geltner) applies to monthly returns with at least 36 unbroken months. Quarterly funds are modelled from equity returns in the same and the previous quarter (Dimson), because appraisals react late.</p></section>';
    return h;
  };

  PAGE.factors = function () {
    var R = S.R, F = R.factors, h = head('Factors', 'How sensitive the portfolio is to five broad market drivers, estimated by regression on the months used.');
    if (!F) return h + '<div class="banner warn">No market factor history is loaded.</div>';
    h += '<section class="tiles">' + F.names.map(function (n, i) { return tile(esc(n), num(F.port[i]), 'Benchmark ' + (F.bench ? num(F.bench[i]) : '–')); }).join('') + tile('Explained by factors', pct(F.port_r2, 0), 'R² of the portfolio') + '</section>';
    h += '<section class="panel"><h2>By holding</h2><p class="sub small">A beta of 0.8 to Global equities means the holding tends to move 0.8% when equities move 1%. Low R² means the factors explain little of the holding, so its stress results are less reliable.</p><div class="scroll"><table><tr><th>Holding</th><th class="r">Weight</th>' + F.names.map(function (n) { return '<th class="r">' + esc(n) + '</th>'; }).join('') + '<th class="r">R²</th></tr>' +
      F.holdings.map(function (x) { return '<tr><td>' + esc(short(x.name)) + '</td><td class="r num">' + pct(x.w) + '</td>' + x.beta.map(function (b) { return '<td class="r num ' + cls(b) + '">' + num(b) + '</td>'; }).join('') + '<td class="r num' + (x.r2 < 0.3 ? ' neg' : '') + '">' + pct(x.r2, 0) + '</td></tr>'; }).join('') + '</table></div></section>';
    if (F.corr) h += '<section class="panel"><h2>How the factors move together</h2><div class="scroll"><table class="heat"><tr><th></th>' + F.names.map(function (n) { return '<th>' + esc(n) + '</th>'; }).join('') + '</tr>' +
      F.corr.map(function (row, i) { return '<tr><th style="text-align:left">' + esc(F.names[i]) + '</th>' + row.map(function (v) { var a = Math.min(1, Math.abs(v)) * 60; return '<td style="background:color-mix(in srgb,var(--' + (v < 0 ? 'neg' : 'pos') + ') ' + a.toFixed(0) + '%,var(--panel))">' + num(v) + '</td>'; }).join('') + '</tr>'; }).join('') + '</table></div></section>';
    if (F.pca) h += '<section class="panel"><h2>Hidden common drivers (principal components)</h2><p class="sub small">Statistical patterns in the holdings’ returns. If one component explains most of the portfolio’s risk, the holdings are less diversified than they look.</p><div class="scroll"><table><tr><th>Component</th><th class="r">Share of all holdings’ variation</th><th class="r">Share of portfolio risk</th><th>Holdings that load most</th></tr>' +
      F.pca.map(function (c, i) { return '<tr><td>' + (i + 1) + '</td><td class="r num">' + pct(c.share, 0) + '</td><td class="r num">' + pct(c.port_share, 0) + '</td><td class="wrap small">' + c.top.map(function (t) { return esc(short(t.name)); }).join(', ') + '</td></tr>'; }).join('') + '</table></div></section>';
    return h;
  };

  PAGE.about = function () {
    return '<div class="pagehead"><div><h1>How it works</h1></div></div><section class="panel"><div class="kv">' +
      '<b>Your data</b><span>Excel files are read inside this browser tab. Nothing is uploaded, sent or saved; reloading the page clears it. Only settings (such as the window and confidence level) are remembered on this device.</span>' +
      '<b>The engine</b><span>The calculations are riskcore, a Python library, running in the browser. On the same data it reproduces v0.4.2 to within 0.00000001.</span>' +
      '<b>Risk window</b><span>By default the last 36 months (a rolling 3-year window), applied to today’s holdings. Switch to 5 or 10 years at the top of each page.</span>' +
      '<b>VaR and ES</b><span>Losses over one month, shown as positive numbers. “Normal” assumes a bell curve; “from history” uses the actual worst months. Ranges come from resampling the history (a block bootstrap, fixed seed so results repeat).</span>' +
      '<b>Trust label</b><span>High, Medium or Low, from how many months are used, how much of the history is the funds’ own reported data, and how much of the portfolio has stale prices.</span>' +
      '<b>Illiquid funds</b><span>Smoothed monthly funds are desmoothed; quarterly funds are modelled from equity returns; yearly-valued funds use your assumed beta. See the Illiquid assets page, where the correction can be switched off.</span>' +
      '<b>Liquidity</b><span>Read from the monthly liquidity report. Each holding is placed in a bucket from its own terms, and the totals are checked against the report’s own dashboard. Gates, lock-ups and fees apply only when you enter them.</span>' +
      '<b>Status</b><span>Test build. An independent check of the maths passed the arithmetic; its five main findings have been fixed and are awaiting re-review.</span>' +
      '</div></section>';
  };

  // ------------------------------------------------------------ events
  function wire() {
    $$('[data-seg]').forEach(function (g) {
      $$('button', g).forEach(function (b) {
        b.addEventListener('click', function () {
          var id = g.getAttribute('data-seg'), v = b.getAttribute('data-v');
          if (id === 'window') { S.settings.window = +v; saveSettings(); recompute(); }
          else if (id === 'conf') { S.settings.conf = +v; saveSettings(); recompute(); }
          else if (id === 'cmp') { S.cmp.period = v; runCompare(); }
          else if (id === 'liq-rec') { S.settings.liqr.receivables = v === '1'; saveSettings(); runLiquidity(); }
          else if (id === 'desm') { S.settings.desmooth = v === '1'; saveSettings(); recompute(); }
        });
      });
    });
    $$('select[data-set]').forEach(function (s) { s.addEventListener('change', function () { var k = s.getAttribute('data-set'); S.settings[k] = k === 'liq_target' ? +s.value : s.value || null; if (k !== 'as_of') saveSettings(); recompute(); }); });
    $$('input[data-liq]').forEach(function (c) { c.addEventListener('change', function () { S.settings.liquidity[c.getAttribute('data-liq')] = c.checked; saveSettings(); recompute(); }); });
    $$('select[data-proxy]').forEach(function (s) { s.addEventListener('change', function () { var n = s.getAttribute('data-proxy'); if (s.value) S.settings.proxies[n] = s.value; else delete S.settings.proxies[n]; saveSettings(); recompute(); }); });
    $$('input[data-ab]').forEach(function (c) { c.addEventListener('change', function () { var n = c.getAttribute('data-ab'), o = {}; Object.keys(S.settings.assumed_betas).forEach(function (k) { if (k !== n) o[k] = S.settings.assumed_betas[k]; }); if (c.value !== '' && isFinite(+c.value)) o[n] = +c.value; S.settings.assumed_betas = o; saveSettings(); recompute(); }); });
    $$('select[data-role]').forEach(function (c) { c.addEventListener('change', function () { var n = c.getAttribute('data-role'), o = {}; Object.keys(S.settings.factor_map).forEach(function (k) { if (k !== n) o[k] = S.settings.factor_map[k]; }); if (c.value) o[n] = c.value; S.settings.factor_map = o; saveSettings(); recompute(); }); });
    $$('input[data-cmp]').forEach(function (c) { c.addEventListener('change', function () { var n = c.getAttribute('data-cmp'); S.cmp.names = S.cmp.names.filter(function (x) { return x !== n; }); if (c.checked) S.cmp.names.push(n); runCompare(); }); });
    $$('th[data-sort]').forEach(function (t) { t.addEventListener('click', function () { var k = t.getAttribute('data-sort'); S.hsort = { k: k, d: S.hsort.k === k ? -S.hsort.d : (k === 'name' || k === 'sleeve' ? 1 : -1) }; render(); }); });
    $$('tr[data-stress]').forEach(function (r) { r.addEventListener('click', function (e) { if (e.target.closest('button')) return; var id = r.getAttribute('data-stress'); S.stressSel = S.stressSel === id ? null : id; render(); }); });
    $$('button[data-use]').forEach(function (b) { b.addEventListener('click', function () {
      var s = S.R.stress.filter(function (x) { return x.id === b.getAttribute('data-use'); })[0]; S.scen.shocks = {}; S.R.factors.names.forEach(function (n, i) { S.scen.shocks[n] = Math.round(s.shocks[i] * 1000) / 1000; });
      runScenario().then(function () { $('#builder').scrollIntoView({ behavior: 'smooth' }); toast('Loaded “' + s.name + '” into the builder. Move any slider to change it.'); });
    }); });
    var at = $('#at-run'); if (at) at.addEventListener('click', function () {
      var pol = S.attrRes.policy.map(function (p, i) { return { sleeve: p.sleeve, weight: +$('[data-pw="' + i + '"]').value || 0, series: $('[data-ps="' + i + '"]').value }; });
      S.attr.policy = pol; engine.call('attribution', [$('#at-from').value, $('#at-to').value, JSON.stringify(pol)]).then(function (x) { S.attrRes = x; render(); });
    });
    ['at-from', 'at-to'].forEach(function (id) { var e = $('#' + id); if (e) e.addEventListener('change', function () { engine.call('attribution', [$('#at-from').value, $('#at-to').value, JSON.stringify(S.attrRes.policy)]).then(function (x) { S.attrRes = x; render(); }); }); });
    var lm = $('#liq-month'); if (lm) lm.addEventListener('change', function () { S.liq.month = +lm.value; render(); });
    var lh = $('#liq-h'); if (lh) lh.addEventListener('change', function () { S.settings.liqr.horizon = +lh.value; saveSettings(); runLiquidity(); });
    var lmin = $('#liq-min'); if (lmin) lmin.addEventListener('change', function () { var v = +lmin.value; if (isFinite(v) && v >= 0 && v <= 100) { S.settings.liqr.min_liquid = v / 100; saveSettings(); runLiquidity(); } });
    var ls = $('#liq-sus'); if (ls) { ls.addEventListener('input', function () { ls.nextElementSibling.textContent = ls.value + '%'; }); ls.addEventListener('change', function () { S.settings.liqr.suspend = +ls.value / 100; saveSettings(); runLiquidity(); }); }
    var lsm = $('#liq-sample'); if (lsm) lsm.addEventListener('click', function () { fetch('sample-liquidity.json').then(function (r) { return r.json(); }).then(function (f) { S.liq.files = f; S.liq.month = null; runLiquidity(); }); });
    var lc = $('#liq-clear'); if (lc) lc.addEventListener('click', function () { S.liq = { files: [], res: null, month: null }; render(); });
    $$('input[data-lt]').forEach(function (c) { c.addEventListener('change', function () {
      var n = c.getAttribute('data-lt'), k = c.getAttribute('data-k'), T = S.settings.liqr.terms, t = Object.assign({}, T[n] || {});
      if (c.value === '') t[k] = null; else if (k === 'lockup_end') t[k] = c.value; else if (isFinite(+c.value)) t[k] = +c.value / 100;
      var o = {}; Object.keys(T).forEach(function (x) { if (x !== n) o[x] = T[x]; });
      if (t.gate || t.fee || t.lockup_end) o[n] = t;
      S.settings.liqr.terms = o; saveSettings(); runLiquidity();
    }); });
    var pick = $('#pick'), file = $('#file'), drop = $('#drop');
    if (pick) pick.addEventListener('click', function () { file.click(); });
    if (file) file.addEventListener('change', function () { readFiles(file.files); file.value = ''; });
    if ($('#sample')) $('#sample').addEventListener('click', loadSample);
    if (drop) {
      ['dragenter', 'dragover'].forEach(function (t) { drop.addEventListener(t, function (e) { e.preventDefault(); drop.classList.add('over'); }); });
      ['dragleave', 'drop'].forEach(function (t) { drop.addEventListener(t, function (e) { e.preventDefault(); drop.classList.remove('over'); }); });
      drop.addEventListener('drop', function (e) { readFiles(e.dataTransfer.files); });
    }
    if (page() === 'stress') renderScenario();
  }
  window.addEventListener('hashchange', function () { render(); window.scrollTo(0, 0); });
  engine.status();
  render();
  engine.started.catch(function () { render(); });
})();
