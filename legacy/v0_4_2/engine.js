/* Risk engine: all calculations. Pure functions, no DOM. Returns are decimals per month. */
(function (root) {
  'use strict';
  var RE = {};

  // ================= basic maths =================
  function zeros(n, m) { var a = new Array(n); for (var i = 0; i < n; i++) a[i] = new Array(m).fill(0); return a; }
  function dot(a, b) { var s = 0; for (var i = 0; i < a.length; i++) s += a[i] * b[i]; return s; }
  function matVec(A, v) { return A.map(function (r) { return dot(r, v); }); }
  function sum(a) { var s = 0; for (var i = 0; i < a.length; i++) s += a[i]; return s; }
  function mean(a) { return a.length ? sum(a) / a.length : 0; }
  function variance(a) { if (a.length < 2) return 0; var m = mean(a), s = 0; for (var i = 0; i < a.length; i++) s += (a[i] - m) * (a[i] - m); return s / (a.length - 1); }
  function stdev(a) { return Math.sqrt(variance(a)); }
  function covar(a, b) { if (a.length < 2) return 0; var ma = mean(a), mb = mean(b), s = 0; for (var i = 0; i < a.length; i++) s += (a[i] - ma) * (b[i] - mb); return s / (a.length - 1); }
  function correl(a, b) { var d = stdev(a) * stdev(b); return d > 0 ? covar(a, b) / d : 0; }
  function compound(a) { var p = 1; for (var i = 0; i < a.length; i++) p *= 1 + a[i]; return p - 1; }
  function covMatrix(X) {
    var T = X.length, N = T ? X[0].length : 0, mu = new Array(N).fill(0), i, j, t;
    for (t = 0; t < T; t++) for (j = 0; j < N; j++) mu[j] += X[t][j] / T;
    var C = zeros(N, N), d = Math.max(T - 1, 1);
    for (t = 0; t < T; t++) for (i = 0; i < N; i++) { var di = X[t][i] - mu[i]; if (di === 0) continue; for (j = i; j < N; j++) C[i][j] += di * (X[t][j] - mu[j]); }
    for (i = 0; i < N; i++) for (j = i; j < N; j++) { C[i][j] /= d; C[j][i] = C[i][j]; }
    return C;
  }
  function corrFromCov(C) {
    var n = C.length, R = zeros(n, n);
    for (var i = 0; i < n; i++) for (var j = 0; j < n; j++) { var d = Math.sqrt(C[i][i] * C[j][j]); R[i][j] = d > 0 ? C[i][j] / d : (i === j ? 1 : 0); }
    return R;
  }
  function solve(A, b) {
    var n = A.length, M = A.map(function (r, i) { return r.concat([b[i]]); }), i, j, k;
    for (i = 0; i < n; i++) {
      var p = i;
      for (k = i + 1; k < n; k++) if (Math.abs(M[k][i]) > Math.abs(M[p][i])) p = k;
      if (Math.abs(M[p][i]) < 1e-300) throw new Error('singular matrix');
      var tmp = M[i]; M[i] = M[p]; M[p] = tmp;
      for (k = i + 1; k < n; k++) { var f = M[k][i] / M[i][i]; if (f === 0) continue; for (j = i; j <= n; j++) M[k][j] -= f * M[i][j]; }
    }
    var x = new Array(n);
    for (i = n - 1; i >= 0; i--) { var s = M[i][n]; for (j = i + 1; j < n; j++) s -= M[i][j] * x[j]; x[i] = s / M[i][i]; }
    return x;
  }
  function inv(A) {
    var n = A.length, R = zeros(n, n);
    for (var j = 0; j < n; j++) { var e = new Array(n).fill(0); e[j] = 1; var c = solve(A, e); for (var i = 0; i < n; i++) R[i][j] = c[i]; }
    return R;
  }
  /* Jacobi eigen-decomposition of a symmetric matrix. Returns values (desc) and vectors[k] = k-th eigenvector. */
  function eigSym(A) {
    var n = A.length, a = A.map(function (r) { return r.slice(); }), V = zeros(n, n), i, j, k, p, q;
    for (i = 0; i < n; i++) V[i][i] = 1;
    var scale = 0; for (i = 0; i < n; i++) for (j = 0; j < n; j++) scale += a[i][j] * a[i][j];
    for (var sweep = 0; sweep < 200; sweep++) {
      var off = 0; for (i = 0; i < n; i++) for (j = i + 1; j < n; j++) off += a[i][j] * a[i][j];
      if (off <= 1e-26 * scale) break;
      for (p = 0; p < n - 1; p++) for (q = p + 1; q < n; q++) {
        if (a[p][q] === 0) continue;
        var theta = (a[q][q] - a[p][p]) / (2 * a[p][q]);
        var t = (theta >= 0 ? 1 : -1) / (Math.abs(theta) + Math.sqrt(theta * theta + 1));
        var c = 1 / Math.sqrt(t * t + 1), s = t * c;
        for (k = 0; k < n; k++) { var akp = a[k][p], akq = a[k][q]; a[k][p] = c * akp - s * akq; a[k][q] = s * akp + c * akq; }
        for (k = 0; k < n; k++) { var apk = a[p][k], aqk = a[q][k]; a[p][k] = c * apk - s * aqk; a[q][k] = s * apk + c * aqk; }
        for (k = 0; k < n; k++) { var vkp = V[k][p], vkq = V[k][q]; V[k][p] = c * vkp - s * vkq; V[k][q] = s * vkp + c * vkq; }
      }
    }
    var idx = []; for (i = 0; i < n; i++) idx.push(i);
    idx.sort(function (x, y) { return a[y][y] - a[x][x]; });
    return {
      values: idx.map(function (m) { return a[m][m]; }),
      vectors: idx.map(function (m) { var v = V.map(function (r) { return r[m]; }); if (sum(v) < 0) v = v.map(function (x) { return -x; }); return v; })
    };
  }
  function normPdf(z) { return Math.exp(-0.5 * z * z) / Math.sqrt(2 * Math.PI); }
  function normInv(p) {
    var a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00],
      b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01, -1.328068155288572e+01],
      c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00],
      d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00], q, r;
    if (p < 0.02425) { q = Math.sqrt(-2 * Math.log(p)); return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1); }
    if (p <= 1 - 0.02425) { q = p - 0.5; r = q * q; return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1); }
    q = Math.sqrt(-2 * Math.log(1 - p)); return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
  }
  function quantile(a, p) { // linear interpolation, same as numpy default
    var s = a.slice().sort(function (x, y) { return x - y; }), h = (s.length - 1) * p, lo = Math.floor(h), hi = Math.ceil(h);
    return s[lo] + (s[hi] - s[lo]) * (h - lo);
  }
  /* OLS with intercept. y: T, F: T x k. */
  function ols(y, F) {
    var T = y.length, k = T ? F[0].length : 0, n = k + 1, XtX = zeros(n, n), Xty = new Array(n).fill(0), t, i, j;
    for (t = 0; t < T; t++) {
      var row = [1].concat(F[t]);
      for (i = 0; i < n; i++) { Xty[i] += row[i] * y[t]; for (j = 0; j < n; j++) XtX[i][j] += row[i] * row[j]; }
    }
    var tr = 0; for (i = 1; i < n; i++) tr += XtX[i][i];
    for (i = 1; i < n; i++) XtX[i][i] += 1e-12 * (tr / Math.max(k, 1) + 1e-30);
    var b; try { b = solve(XtX, Xty); } catch (e) { b = new Array(n).fill(0); b[0] = mean(y); }
    var my = mean(y), ssr = 0, sst = 0;
    for (t = 0; t < T; t++) { var fit = b[0]; for (i = 0; i < k; i++) fit += b[i + 1] * F[t][i]; ssr += (y[t] - fit) * (y[t] - fit); sst += (y[t] - my) * (y[t] - my); }
    return { alpha: b[0], beta: b.slice(1), r2: sst > 1e-30 ? Math.max(0, 1 - ssr / sst) : 0 };
  }
  /* Convex QP by Hildreth's dual method: min 0.5 x'Hx + f'x  s.t.  A x <= b,  E x = e. */
  function qp(H, f, A, b, E, e) {
    var n = f.length, Hi = inv(H), x0 = matVec(Hi, f).map(function (v) { return -v; });
    var rows = A.concat(E || []), rhs = b.concat(e || []), m = rows.length, nIneq = A.length, i, j;
    if (!m) return x0;
    var G = rows.map(function (r) { return matVec(Hi, r); });
    var P = zeros(m, m), d = new Array(m);
    for (i = 0; i < m; i++) { d[i] = rhs[i] - dot(rows[i], x0); for (j = 0; j < m; j++) P[i][j] = dot(rows[i], G[j]); }
    var lam = new Array(m).fill(0);
    for (var it = 0; it < 200000; it++) {
      var maxCh = 0;
      for (i = 0; i < m; i++) {
        if (P[i][i] <= 0) continue;
        var s = d[i]; for (j = 0; j < m; j++) if (j !== i) s += P[i][j] * lam[j];
        var nv = -s / P[i][i];
        if (i < nIneq && nv < 0) nv = 0;
        var ch = Math.abs(nv - lam[i]) * Math.sqrt(P[i][i]); if (ch > maxCh) maxCh = ch;
        lam[i] = nv;
      }
      if (maxCh < 1e-13) break;
    }
    var x = x0.slice();
    for (j = 0; j < m; j++) if (lam[j] !== 0) for (i = 0; i < n; i++) x[i] -= lam[j] * G[j][i];
    return x;
  }
  /* Convex QP by a primal active-set method, started from a feasible point x0.
     min 0.5 x'Hx + f'x  s.t.  Aeq x = beq,  Ain x >= bin.  Returns null if it cannot finish. */
  function qpActiveSet(H, f, Aeq, Ain, bin, x0) {
    var n = f.length, x = x0.slice(), me = Aeq.length, mi = Ain.length, work = [], i, j, r, k;
    for (var it = 0; it < 60 * (n + mi + 5); it++) {
      var g = matVec(H, x), rows = Aeq.concat(work.map(function (q) { return Ain[q]; })), m = rows.length;
      var K = zeros(n + m, n + m), rhs = new Array(n + m).fill(0);
      for (i = 0; i < n; i++) { g[i] += f[i]; rhs[i] = -g[i]; for (j = 0; j < n; j++) K[i][j] = H[i][j]; }
      for (r = 0; r < m; r++) for (i = 0; i < n; i++) { K[i][n + r] = -rows[r][i]; K[n + r][i] = rows[r][i]; }
      var sol; try { sol = solve(K, rhs); } catch (e) { return null; }
      var p = sol.slice(0, n), pn = Math.sqrt(dot(p, p));
      if (pn < 1e-11) {
        var worst = -1, wv = -1e-9;
        for (r = me; r < m; r++) if (sol[n + r] < wv) { wv = sol[n + r]; worst = r - me; }
        if (worst < 0) return x;
        work.splice(worst, 1);
      } else {
        var alpha = 1, block = -1;
        for (k = 0; k < mi; k++) {
          if (work.indexOf(k) >= 0) continue;
          var ap = dot(Ain[k], p);
          if (ap < -1e-13) { var a = (bin[k] - dot(Ain[k], x)) / ap; if (a < alpha) { alpha = Math.max(0, a); block = k; } }
        }
        for (i = 0; i < n; i++) x[i] += alpha * p[i];
        if (block >= 0) work.push(block);
      }
    }
    return null;
  }
  RE.math = { zeros: zeros, dot: dot, matVec: matVec, sum: sum, mean: mean, variance: variance, stdev: stdev, covar: covar, correl: correl, compound: compound, covMatrix: covMatrix, corrFromCov: corrFromCov, solve: solve, inv: inv, eigSym: eigSym, normInv: normInv, normPdf: normPdf, quantile: quantile, ols: ols, qp: qp, qpActiveSet: qpActiveSet };

  // ================= month helpers =================
  function ymAdd(ym, k) { var y = +ym.slice(0, 4), m = +ym.slice(5, 7) - 1 + k; y += Math.floor(m / 12); m = ((m % 12) + 12) % 12; return y + '-' + ('0' + (m + 1)).slice(-2); }
  function ymRange(a, b) { var out = []; for (var m = a; m <= b; m = ymAdd(m, 1)) out.push(m); return out; }
  function norm(s) { return String(s || '').toLowerCase().replace(/[^a-z0-9]+/g, ''); }
  RE.ymAdd = ymAdd; RE.ymRange = ymRange; RE.norm = norm;

  // ================= dataset =================
  /* valuations: array of XL.parseValuations() results; history: array of series {name,type,ticker,kind,obs}. */
  RE.buildDataset = function (valuations, history) {
    var ds = { demo: false, months: [], monthInfo: {}, holdings: [], sleeves: [], total: { data: {} }, series: {}, issues: [], benchmarkNote: '' };
    var hmap = {}, smap = {};
    var vals = (valuations || []).slice().sort(function (a, b) { var la = a.months[a.months.length - 1].ym, lb = b.months[b.months.length - 1].ym; return la < lb ? -1 : la > lb ? 1 : a.months.length - b.months.length; });
    function merge(target, d) {
      var o = target;
      if (!o) return { val: d.val, ret: d.ret, w: d.w, err: d.err };
      return { val: d.val !== null ? d.val : o.val, ret: d.ret !== null ? d.ret : o.ret, w: d.w !== null ? d.w : o.w, err: d.err || (d.val === null && d.ret === null ? o.err : null) };
    }
    vals.forEach(function (pv) {
      pv.months.forEach(function (m) { var mi = ds.monthInfo[m.ym]; if (!mi) ds.monthInfo[m.ym] = { hasReturn: m.hasReturn, date: m.date }; else if (m.hasReturn) mi.hasReturn = true; });
      pv.holdings.forEach(function (h) {
        var k = norm(h.name), t = hmap[k];
        if (!t) { t = hmap[k] = { name: h.name, sleeve: h.sleeve, liquid: h.liquid, data: {} }; ds.holdings.push(t); }
        t.sleeve = h.sleeve; if (h.liquid !== null && h.liquid !== undefined) t.liquid = h.liquid; else if (t.liquid === undefined || t.liquid === null) t.liquid = !/strategic|alternative/i.test(h.sleeve); t.name = h.name;
        Object.keys(h.data).forEach(function (ym) { t.data[ym] = merge(t.data[ym], h.data[ym]); });
      });
      pv.sleeves.forEach(function (s) {
        var k = norm(s.name), t = smap[k];
        if (!t) { t = smap[k] = { name: s.name, data: {} }; ds.sleeves.push(t); }
        Object.keys(s.data).forEach(function (ym) { t.data[ym] = merge(t.data[ym], s.data[ym]); });
      });
      if (pv.total) Object.keys(pv.total.data).forEach(function (ym) { ds.total.data[ym] = merge(ds.total.data[ym], pv.total.data[ym]); });
      (pv.issues || []).forEach(function (i) { ds.issues.push(i); });
      if (pv.benchmarkNote) ds.benchmarkNote = pv.benchmarkNote;
    });
    ds.months = Object.keys(ds.monthInfo).sort();
    // keep only sleeves that still have holdings
    var used = {}; ds.holdings.forEach(function (h) { used[norm(h.sleeve)] = 1; });
    ds.sleeves = ds.sleeves.filter(function (s) { return used[norm(s.name)]; });
    (history || []).forEach(function (s) { RE.addSeries(ds, s); });
    return ds;
  };
  RE.addSeries = function (ds, s) {
    var o = { name: s.name, type: s.type || 'holding', ticker: s.ticker || '', ret: {}, lvl: {} };
    var yms = Object.keys(s.obs).sort();
    if (s.kind === 'level') {
      yms.forEach(function (ym) { o.lvl[ym] = s.obs[ym]; var p = s.obs[ymAdd(ym, -1)]; if (o.type !== 'signal' && p !== undefined && p !== 0) o.ret[ym] = s.obs[ym] / p - 1; });
    } else yms.forEach(function (ym) { o.ret[ym] = s.obs[ym]; });
    ds.series[norm(s.name)] = o;
  };
  RE.findSeries = function (ds, name) { return name ? ds.series[norm(name)] || null : null; };
  RE.seriesList = function (ds, types) {
    return Object.keys(ds.series).map(function (k) { return ds.series[k]; }).filter(function (s) { return !types || types.indexOf(s.type) >= 0; });
  };
  /* Months in which the workbook is usable: a total exists and almost all previously held positions have a return. */
  RE.today = function () { var d = new Date(); return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2); };
  RE.monthEnd = function (ym) { var y = +ym.slice(0, 4), m = +ym.slice(5, 7); return ym + '-' + ('0' + new Date(Date.UTC(y, m, 0)).getUTCDate()).slice(-2); };
  RE.monthOpen = function (ym, today) { return RE.monthEnd(ym) >= (today || RE.today()); };   // a month counts as over from the day after its last day
  RE.completeMonths = function (ds, today) {
    return ds.months.filter(function (ym, i) {
      if (!ds.monthInfo[ym].hasReturn || RE.monthOpen(ym, today)) return false;
      var prev = ds.months[i - 1], tot = 0, miss = 0;
      ds.holdings.forEach(function (h) {
        var p = prev && h.data[prev] ? h.data[prev].val : null, c = h.data[ym];
        if (p > 0) { tot += p; if (!c || c.val === null || c.ret === null) miss += p; }
      });
      return tot > 0 && miss / tot <= 0.02;
    });
  };

  RE.portReturn = function (ds, ym) {
    var prev = ymAdd(ym, -1), tv = 0, c = 0, miss = 0;
    ds.holdings.forEach(function (h) { var p = h.data[prev]; if (p && p.val > 0) tv += p.val; });
    if (!(tv > 0)) return null;
    ds.holdings.forEach(function (h) { var p = h.data[prev], d = h.data[ym]; if (p && p.val > 0) { if (d && d.ret !== null) c += p.val / tv * d.ret; else miss += p.val; } });
    return miss / tv > 0.02 ? null : c;
  };
  RE.defaultSettings = function () {
    return {
      asOf: null, window: 60, minCoverage: 0.4, conf: 0.95, liq: {}, proxy: {}, riskBenchmark: '', perfBenchmark: '',
      policy: null, liqTarget: 0.90, reverseLoss: 0.10, propagate: true, custom: {},
      opt: { goal: 'minrisk_same_return', maxChange: 0.05, lockIlliquid: true, maxTE: null, mu: {} },
      attrFrom: null, attrTo: null
    };
  };

  // ================= scenario library =================
  /* Approximate factor moves, used only when the loaded history does not cover the period. */
  RE.SCENARIOS = [
    { id: 'gfc', name: '2008 financial crisis', kind: 'historical', from: '2007-11', to: '2009-02', preset: { globalequities: -0.54, ustreasuries: 0.14, highyieldcredit: -0.26, usdollar: 0.15, oil: -0.49 } },
    { id: 'euro', name: '2011 euro crisis', kind: 'historical', from: '2011-05', to: '2011-09', preset: { globalequities: -0.195, ustreasuries: 0.078, highyieldcredit: -0.065, usdollar: 0.076, oil: -0.18 } },
    { id: 'q418', name: 'Q4 2018 sell-off', kind: 'historical', from: '2018-10', to: '2018-12', preset: { globalequities: -0.134, ustreasuries: 0.026, highyieldcredit: -0.045, usdollar: 0.011, oil: -0.35 } },
    { id: 'covid', name: '2020 Covid sell-off', kind: 'historical', from: '2020-02', to: '2020-03', preset: { globalequities: -0.205, ustreasuries: 0.056, highyieldcredit: -0.127, usdollar: 0.017, oil: -0.61 } },
    { id: 'y2022', name: '2022 inflation and rates shock', kind: 'historical', from: '2022-01', to: '2022-09', preset: { globalequities: -0.254, ustreasuries: -0.131, highyieldcredit: -0.147, usdollar: 0.172, oil: 0.13 } },
    { id: 'eq20', name: 'Equities fall 20%', kind: 'hypothetical', shocks: { globalequities: -0.20 } },
    { id: 'rates', name: 'Rates rise 100 bp (Treasuries −6%)', kind: 'hypothetical', shocks: { ustreasuries: -0.06 } },
    { id: 'credit', name: 'Credit spreads widen (high yield −10%)', kind: 'hypothetical', shocks: { highyieldcredit: -0.10 } },
    { id: 'usd', name: 'Dollar rises 10%', kind: 'hypothetical', shocks: { usdollar: 0.10 } },
    { id: 'oil', name: 'Oil falls 30%', kind: 'hypothetical', shocks: { oil: -0.30 } },
    { id: 'stag', name: 'Stagflation mix', kind: 'hypothetical', shocks: { globalequities: -0.15, ustreasuries: -0.08, highyieldcredit: -0.08, usdollar: 0.05, oil: 0.30 } }
  ];

  // ================= main analysis =================
  RE.analyse = function (ds, st) {
    var A = { ok: false, notes: [], issues: ds.issues.slice(), demo: !!ds.demo };
    var today = st.today || RE.today(), complete = RE.completeMonths(ds, today);
    if (!complete.length) { A.error = 'No complete month was found. Check that the workbook has values and returns for at least one month.'; return A; }
    var asOf = st.asOf && complete.indexOf(st.asOf) >= 0 ? st.asOf : complete[complete.length - 1];
    A.asOf = asOf; A.completeMonths = complete; A.latestMonth = ds.months[ds.months.length - 1];
    A.incompleteAfter = ds.months.filter(function (m) { return m > asOf && complete.indexOf(m) < 0 && ds.monthInfo[m].hasReturn && ds.holdings.some(function (h) { var d = h.data[m]; return d && (d.val !== null || d.ret !== null); }); });
    A.openMonths = A.incompleteAfter.filter(function (m) { return RE.monthOpen(m, today); });

    // ---- positions
    var pos = ds.holdings.filter(function (h) { return h.data[asOf] && h.data[asOf].val > 0; });
    var aum = sum(pos.map(function (h) { return h.data[asOf].val; }));
    var N = pos.length, w = pos.map(function (h) { return h.data[asOf].val / aum; });
    var liquid = pos.map(function (h) { return st.liq && st.liq[h.name] !== undefined ? !!st.liq[h.name] : h.liquid; });
    var sleeveNames = ds.sleeves.map(function (s) { return s.name; }).filter(function (sn) { return pos.some(function (h) { return norm(h.sleeve) === norm(sn); }); });
    var sIdx = pos.map(function (h) { for (var i = 0; i < sleeveNames.length; i++) if (norm(sleeveNames[i]) === norm(h.sleeve)) return i; return -1; });
    A.aum = aum; A.N = N; A.sleeveNames = sleeveNames;
    var totRow = ds.total.data[asOf];
    if (totRow && totRow.val && Math.abs(totRow.val / aum - 1) > 0.001) A.issues.push({ level: 'warn', text: 'The holdings add up to ' + (aum / 1e6).toFixed(1) + 'm but the total row shows ' + (totRow.val / 1e6).toFixed(1) + 'm for ' + asOf + '.' });

    // ---- return history per holding
    var hist = pos.map(function (h) {
      var m = {}, s = RE.findSeries(ds, h.name), ym;
      if (s) for (ym in s.ret) if (ym <= asOf) m[ym] = s.ret[ym];
      ds.months.forEach(function (mm, i) {
        if (mm > asOf || !ds.monthInfo[mm].hasReturn) return;
        var d = h.data[mm], p = i > 0 && h.data[ds.months[i - 1]] ? h.data[ds.months[i - 1]].val : null;
        if (d && d.ret !== null && ((d.val || 0) > 0 || (p || 0) > 0)) m[mm] = d.ret;
      });
      return m;
    });
    var proxy = pos.map(function (h) { var p = st.proxy && st.proxy[h.name] ? RE.findSeries(ds, st.proxy[h.name]) : null; return p ? p.ret : null; });
    function ownAt(i, ym) { if (proxy[i] && proxy[i][ym] !== undefined) return proxy[i][ym]; return hist[i][ym]; }

    // ---- estimation window
    var W = Math.max(3, Math.min(240, st.window || 60)), cand = ymRange(ymAdd(asOf, -(W - 1)), asOf), months = [], coverage = {};
    for (var ci = cand.length - 1; ci >= 0; ci--) {
      var cov = 0; for (var i0 = 0; i0 < N; i0++) if (ownAt(i0, cand[ci]) !== undefined) cov += w[i0];
      coverage[cand[ci]] = cov;
      if (cov < (st.minCoverage || 0.4)) break;
      months.unshift(cand[ci]);
    }
    var T = months.length;
    A.months = months; A.T = T; A.coverage = coverage;
    if (T < 3) { A.error = 'Fewer than three months of usable returns are available up to ' + asOf + '.'; return A; }
    var X = zeros(T, N), real = new Array(N).fill(0), filled = new Array(N).fill(0), zerosCnt = new Array(N).fill(0), fromPast = new Array(N).fill(0);
    var sleeveKey = sleeveNames.map(norm);
    function pastSleeve(s, ym) {   // what all of FGR's holdings in this asset class returned that month
      var prev = ymAdd(ym, -1), a = 0, b = 0;
      ds.holdings.forEach(function (h) { if (norm(h.sleeve) !== sleeveKey[s]) return; var p = h.data[prev], d = h.data[ym]; if (p && p.val > 0 && d && d.ret !== null) { a += p.val * d.ret; b += p.val; } });
      return b > 0 ? a / b : null;
    }
    months.forEach(function (ym, t) {
      var sSum = new Array(sleeveNames.length).fill(0), sW = new Array(sleeveNames.length).fill(0), past = {}, i, v;
      for (i = 0; i < N; i++) { v = ownAt(i, ym); if (v !== undefined) { X[t][i] = v; real[i]++; if (v === 0) zerosCnt[i]++; sSum[sIdx[i]] += w[i] * v; sW[sIdx[i]] += w[i]; } }
      for (i = 0; i < N; i++) if (ownAt(i, ym) === undefined) {
        var s = sIdx[i];
        if (sW[s] > 0) X[t][i] = sSum[s] / sW[s];
        else { if (!(s in past)) past[s] = pastSleeve(s, ym); X[t][i] = past[s] === null ? 0 : past[s]; if (past[s] !== null) fromPast[i]++; }
        filled[i]++;
      }
    });
    var C = covMatrix(X), Cw = matVec(C, w), varP = dot(w, Cw), sdP = Math.sqrt(Math.max(varP, 0));
    var rp = X.map(function (r) { return dot(r, w); });
    var z = normInv(st.conf || 0.95), conf = st.conf || 0.95;
    A.X = X; A.C = C; A.w = w; A.rp = rp;
    A.confidence = T < 12 ? 'low' : T < 36 ? 'medium' : 'good';

    // ---- risk
    var VaR = z * sdP, CVaR = sdP * normPdf(z) / (1 - conf);
    A.risk = { volM: sdP, volA: sdP * Math.sqrt(12), VaR: VaR, CVaR: CVaR, conf: conf, z: z, meanM: mean(rp), best: Math.max.apply(null, rp), worst: Math.min.apply(null, rp) };
    if (T >= 24) { var qv = quantile(rp, 1 - conf); A.risk.histVaR = -qv; var tail = rp.filter(function (x) { return x <= qv; }); A.risk.histCVaR = -mean(tail); }
    var peak = 1, lvl = 1, mdd = 0; rp.forEach(function (r) { lvl *= 1 + r; if (lvl > peak) peak = lvl; mdd = Math.min(mdd, lvl / peak - 1); }); A.risk.maxDD = mdd;
    A.holdings = pos.map(function (h, i) {
      var w2 = w.slice(); w2[i] = 0;
      var sdi = Math.sqrt(Math.max(C[i][i], 0));
      return {
        name: h.name, sleeve: sleeveNames[sIdx[i]], liquid: liquid[i], value: h.data[asOf].val, w: w[i],
        volA: sdi * Math.sqrt(12), rc: varP > 0 ? w[i] * Cw[i] / varP : 0,
        mvar: sdP > 0 ? z * Cw[i] / sdP : 0, cvar: sdP > 0 ? w[i] * z * Cw[i] / sdP : 0,
        ivar: VaR - z * Math.sqrt(Math.max(dot(w2, matVec(C, w2)), 0)),
        real: real[i], filled: filled[i], fromPast: fromPast[i], proxied: !!proxy[i], stale: real[i] > 0 && zerosCnt[i] / real[i] >= 0.7 && !proxy[i], noData: real[i] === 0,
        corrP: sdi > 0 && sdP > 0 ? Cw[i] / (sdi * sdP) : 0
      };
    });
    // ---- sleeves
    var S = sleeveNames.length, sw = new Array(S).fill(0);
    for (var i1 = 0; i1 < N; i1++) sw[sIdx[i1]] += w[i1];
    var XS = X.map(function (r) { var o = new Array(S).fill(0); for (var i = 0; i < N; i++) if (sw[sIdx[i]] > 0) o[sIdx[i]] += r[i] * w[i] / sw[sIdx[i]]; return o; });
    var CS = covMatrix(XS);
    A.sleeves = sleeveNames.map(function (sn, s) {
      var hs = A.holdings.filter(function (h) { return h.sleeve === sn; });
      return {
        name: sn, w: sw[s], value: sw[s] * aum, rc: sum(hs.map(function (h) { return h.rc; })), cvar: sum(hs.map(function (h) { return h.cvar; })),
        volA: Math.sqrt(Math.max(CS[s][s], 0) * 12), illiquidW: sum(hs.filter(function (h) { return !h.liquid; }).map(function (h) { return h.w; })), n: hs.length
      };
    });
    A.XS = XS; A.CS = CS; A.sw = sw; A.corrS = corrFromCov(CS); A.corr = corrFromCov(C);

    // ---- liquidity
    var liqW = sum(A.holdings.filter(function (h) { return h.liquid; }).map(function (h) { return h.w; })), tgt = st.liqTarget || 0.9;
    A.liquidity = { liquid: liqW, target: tgt, illiquidValue: (1 - liqW) * aum, exitNeeded: Math.max(0, (1 - liqW) * aum - (1 - tgt) * aum), inflowNeeded: Math.max(0, (1 - liqW) * aum / (1 - tgt) - aum) };

    // ---- data quality
    var noDataW = sum(A.holdings.filter(function (h) { return h.noData; }).map(function (h) { return h.w; }));
    var staleW = sum(A.holdings.filter(function (h) { return h.stale; }).map(function (h) { return h.w; }));
    A.quality = { noDataW: noDataW, staleW: staleW, avgCoverage: mean(months.map(function (m) { return coverage[m]; })) };

    // ---- benchmarks
    function pick(name, re, nth) {
      var s = RE.findSeries(ds, name); if (s) return s;
      var bs = RE.seriesList(ds, ['benchmark']), hit = bs.filter(function (b) { return re.test(b.name) || re.test(b.ticker); })[0];
      return hit || bs[nth] || null;
    }
    var riskBm = pick(st.riskBenchmark, /50\s*\/?\s*50|bmadm55/i, 0), perfBm = pick(st.perfBenchmark, /russell|multi-?asset\s*35/i, 1) ;
    if (perfBm === riskBm && !st.perfBenchmark) perfBm = RE.seriesList(ds, ['benchmark']).filter(function (b) { return b !== riskBm; })[0] || null;
    A.riskBm = riskBm ? riskBm.name : null; A.perfBm = perfBm ? perfBm.name : null;
    function active(bm) {
      if (!bm) return null;
      var a = [], p = [], b = [];
      months.forEach(function (ym, t) { if (bm.ret[ym] !== undefined) { p.push(rp[t]); b.push(bm.ret[ym]); a.push(rp[t] - bm.ret[ym]); } });
      if (a.length < 6) return { n: a.length };
      var vb = variance(b);
      return { n: a.length, te: stdev(a) * Math.sqrt(12), beta: vb > 0 ? covar(p, b) / vb : 0, corr: correl(p, b), bmVolA: Math.sqrt(vb * 12), pVolA: stdev(p) * Math.sqrt(12), activeMeanA: mean(a) * 12, ir: stdev(a) > 0 ? mean(a) * 12 / (stdev(a) * Math.sqrt(12)) : 0, relVaR: z * stdev(a), bmVaR: z * Math.sqrt(vb) };
    }
    A.activeRisk = active(riskBm); A.activePerf = active(perfBm);

    // ---- realised performance from the workbook
    var yr = asOf.slice(0, 4), q0 = yr + '-' + ('0' + (Math.floor((+asOf.slice(5, 7) - 1) / 3) * 3 + 1)).slice(-2);
    function realised(from) {
      var ms = complete.filter(function (m) { return m >= from && m <= asOf; }), rs = ms.map(function (m) { var r = RE.portReturn(ds, m); return r !== null ? r : ds.total.data[m] ? ds.total.data[m].ret : null; });
      if (!ms.length || rs.some(function (r) { return r === null; })) return null;
      function bmRet(bm) { if (!bm) return null; var b = ms.map(function (m) { return bm.ret[m]; }); return b.some(function (x) { return x === undefined; }) ? null : compound(b); }
      return { months: ms, port: compound(rs), series: rs, risk: bmRet(riskBm), perf: bmRet(perfBm) };
    }
    A.perf = { ytd: realised(yr + '-01'), qtd: realised(q0), month: realised(asOf) };

    // ---- factors
    var fs = RE.seriesList(ds, ['factor']);
    A.factors = null;
    if (fs.length) {
      var fIdx = []; months.forEach(function (ym, t) { if (fs.every(function (f) { return f.ret[ym] !== undefined; })) fIdx.push(t); });
      if (fIdx.length >= Math.max(8, fs.length + 3)) {
        var F = fIdx.map(function (t) { return fs.map(function (f) { return f.ret[months[t]]; }); }), K = fs.length;
        var B = [], r2 = [];
        for (var i2 = 0; i2 < N; i2++) { var o = ols(fIdx.map(function (t) { return X[t][i2]; }), F); B.push(o.beta); r2.push(o.r2); }
        var bp = new Array(K).fill(0); for (var i3 = 0; i3 < N; i3++) for (var k0 = 0; k0 < K; k0++) bp[k0] += w[i3] * B[i3][k0];
        var op = ols(fIdx.map(function (t) { return rp[t]; }), F), SF = covMatrix(F);
        var bb = null;
        if (riskBm) { var bi = fIdx.filter(function (t) { return riskBm.ret[months[t]] !== undefined; }); if (bi.length >= Math.max(8, K + 3)) bb = ols(bi.map(function (t) { return riskBm.ret[months[t]]; }), bi.map(function (t) { return fs.map(function (f) { return f.ret[months[t]]; }); })); }
        var bs = sleeveNames.map(function (sn, s) { var v = new Array(K).fill(0); for (var i = 0; i < N; i++) if (sIdx[i] === s && sw[s] > 0) for (var k = 0; k < K; k++) v[k] += w[i] / sw[s] * B[i][k]; return v; });
        A.factors = { names: fs.map(function (f) { return f.name; }), n: fIdx.length, B: B, r2: r2, port: bp, portR2: op.r2, alphaM: op.alpha, bench: bb ? bb.beta : null, benchR2: bb ? bb.r2 : null, SF: SF, sleeve: bs, volA: fs.map(function (f, k) { return Math.sqrt(SF[k][k] * 12); }) };
      } else A.notes.push('Factor analysis needs at least ' + Math.max(8, fs.length + 3) + ' months in which every factor has data; only ' + fIdx.length + ' are available.');
    }

    // ---- PCA
    var act = []; for (var i4 = 0; i4 < N; i4++) if (C[i4][i4] > 1e-14) act.push(i4);
    if (act.length >= 2) {
      var Csub = act.map(function (i) { return act.map(function (j) { return C[i][j]; }); }), eg = eigSym(Csub), tot = sum(eg.values.map(function (v) { return Math.max(v, 0); })), wsub = act.map(function (i) { return w[i]; });
      var comps = [];
      for (var k1 = 0; k1 < Math.min(5, act.length); k1++) {
        var v = eg.vectors[k1], lam = Math.max(eg.values[k1], 0), proj = dot(v, wsub);
        var score = X.map(function (r) { var s = 0; for (var a = 0; a < act.length; a++) s += r[act[a]] * v[a]; return s; });
        var best = null;
        fs.concat(riskBm ? [riskBm] : []).forEach(function (f) {
          var a = [], b = []; months.forEach(function (ym, t) { if (f.ret[ym] !== undefined) { a.push(score[t]); b.push(f.ret[ym]); } });
          if (a.length >= 6) { var c = correl(a, b); if (!best || Math.abs(c) > Math.abs(best.corr)) best = { name: f.name, corr: c }; }
        });
        var load = act.map(function (i, a) { return { name: pos[i].name, v: v[a] }; }).sort(function (x, y) { return Math.abs(y.v) - Math.abs(x.v); }).slice(0, 5);
        comps.push({ share: tot > 0 ? lam / tot : 0, portShare: varP > 0 ? lam * proj * proj / varP : 0, top: load, like: best });
      }
      A.pca = { comps: comps, n: act.length };
    }

    // ---- stress tests
    A.stress = null; A.reverse = null;
    if (A.factors) {
      var FA = A.factors, keys = FA.names.map(norm), SFm = FA.SF;
      var resolve = function (sc) {
        var s = new Array(keys.length).fill(null), src = 'preset';
        if (sc.kind === 'historical') {
          var ms = ymRange(sc.from, sc.to), all = fs.every(function (f) { return ms.every(function (m) { return f.ret[m] !== undefined; }); });
          if (all) { src = 'data'; fs.forEach(function (f, k) { s[k] = compound(ms.map(function (m) { return f.ret[m]; })); }); }
          else keys.forEach(function (k, i) { if (sc.preset[k] !== undefined) s[i] = sc.preset[k]; });
        } else { src = sc.kind; keys.forEach(function (k, i) { if (sc.shocks && sc.shocks[k] !== undefined && sc.shocks[k] !== null) s[i] = sc.shocks[k]; }); }
        var Kn = [], Un = []; s.forEach(function (v, i) { (v === null ? Un : Kn).push(i); });
        if (Un.length && Kn.length && st.propagate !== false && sc.kind !== 'historical') {
          try {
            var SKK = Kn.map(function (i) { return Kn.map(function (j) { return SFm[i][j]; }); }), y = solve(SKK, Kn.map(function (i) { return s[i]; }));
            Un.forEach(function (u) { s[u] = dot(Kn.map(function (kk) { return SFm[u][kk]; }), y); });
          } catch (e) { Un.forEach(function (u) { s[u] = 0; }); }
        } else Un.forEach(function (u) { s[u] = 0; });
        return { shocks: s, src: src, specified: Kn };
      };
      var apply = function (s) {
        var hI = FA.B.map(function (b) { return dot(b, s); }), port = 0, bySleeve = new Array(S).fill(0);
        for (var i = 0; i < N; i++) { port += w[i] * hI[i]; bySleeve[sIdx[i]] += w[i] * hI[i]; }
        return { port: port, bench: FA.bench ? dot(FA.bench, s) : null, bySleeve: bySleeve, holding: hI };
      };
      var list = RE.SCENARIOS.slice();
      if (st.custom && Object.keys(st.custom).some(function (k) { return st.custom[k] !== null && st.custom[k] !== undefined && st.custom[k] !== ''; })) list.push({ id: 'custom', name: 'Your custom scenario', kind: 'custom', shocks: st.custom });
      var actualOver = function (sc) {
        if (sc.kind !== 'historical') return null;
        var ms = ymRange(sc.from, sc.to), rs = ms.map(function (m) { return complete.indexOf(m) >= 0 ? RE.portReturn(ds, m) : null; });
        return rs.some(function (x) { return x === null; }) ? null : compound(rs);
      };
      A.stress = list.map(function (sc) { var r = resolve(sc), a = apply(r.shocks); return { id: sc.id, name: sc.name, kind: sc.kind, from: sc.from, to: sc.to, src: r.src, shocks: r.shocks, specified: r.specified, port: a.port, bench: a.bench, bySleeve: a.bySleeve, holding: a.holding, actual: actualOver(sc) }; });
      // reverse stress: most likely factor move producing the target loss
      var L = st.reverseLoss || 0.10, Sb = matVec(SFm, FA.port), q = dot(FA.port, Sb);
      if (q > 1e-16) {
        var sStar = Sb.map(function (v) { return -L * v / q; }), ap = apply(sStar);
        A.reverse = { loss: L, shocks: sStar, sigmaM: L / Math.sqrt(q), sigmaA: L / Math.sqrt(q * 12), bySleeve: ap.bySleeve, bench: ap.bench,
          top: A.holdings.map(function (h, i) { return { name: h.name, sleeve: h.sleeve, impact: w[i] * ap.holding[i] }; }).sort(function (a, b) { return a.impact - b.impact; }).slice(0, 6) };
      }
    }

    A.episodes = RE.SCENARIOS.filter(function (sc) { return sc.kind === 'historical'; }).map(function (sc) {
      var ms = ymRange(sc.from, sc.to), rs = ms.map(function (m) { return complete.indexOf(m) >= 0 ? RE.portReturn(ds, m) : null; });
      var ok = !rs.some(function (x) { return x === null; });
      return { id: sc.id, name: sc.name, from: sc.from, to: sc.to, actual: ok ? compound(rs) : null, worst: ok ? Math.min.apply(null, rs) : null };
    });
    A.attribution = RE.attribution(ds, st, asOf, complete);
    A.optimizer = RE.optimise(A, st, riskBm);
    A.signals = RE.signals(ds, asOf);
    A.ok = true;
    return A;
  };

  // ================= attribution (Brinson-Fachler, Carino linking) =================
  RE.defaultPolicy = function (ds) {
    var eq = null, fi = null;
    RE.seriesList(ds, ['factor', 'index']).forEach(function (s) {
      if (!eq && (/equit/i.test(s.name) || /dmtr|acwi|nddu/i.test(s.ticker))) eq = s.name;
      if (!fi && (/bond|aggregate/i.test(s.name) || /legatruu/i.test(s.ticker))) fi = s.name;
    });
    return ds.sleeves.map(function (s) {
      if (/equit/i.test(s.name) && eq) return { sleeve: s.name, weight: 35, series: eq };
      if (/fixed|bond/i.test(s.name) && fi) return { sleeve: s.name, weight: 65, series: fi };
      return { sleeve: s.name, weight: 0, series: '' };
    });
  };
  RE.attribution = function (ds, st, asOf, complete) {
    var R = { ok: false, isDefault: !st.policy };
    var policy = st.policy || RE.defaultPolicy(ds);
    R.policy = policy;
    var wsum = sum(policy.map(function (p) { return +p.weight || 0; }));
    if (wsum <= 0) { R.reason = 'Set the performance benchmark weights in Data & settings to run the attribution.'; }
    var yr = asOf.slice(0, 4), from = st.attrFrom && st.attrFrom <= asOf ? st.attrFrom : yr + '-01', to = st.attrTo && st.attrTo <= asOf && st.attrTo >= from ? st.attrTo : asOf;
    var ms = complete.filter(function (m) { return m >= from && m <= to && ds.months.indexOf(ymAdd(m, -1)) >= 0; });
    R.from = from; R.to = to; R.months = ms; R.available = complete.filter(function (m) { return ds.months.indexOf(ymAdd(m, -1)) >= 0; });
    if (!ms.length) { R.reason = 'No complete months in the selected period.'; return R; }
    var SL = ds.sleeves, nS = SL.length;
    var pol = SL.map(function (s) { var p = policy.filter(function (x) { return norm(x.sleeve) === norm(s.name); })[0]; return { w: p && wsum > 0 ? (+p.weight || 0) / wsum : 0, series: p ? RE.findSeries(ds, p.series) : null }; });
    // holding contributions
    var cum = 1, contrib = {}, rpAll = [], reported = [];
    var perMonth = ms.map(function (m) {
      var prev = ymAdd(m, -1), tv = 0, c = 0;
      ds.holdings.forEach(function (h) { var p = h.data[prev]; if (p && p.val > 0) tv += p.val; });
      ds.holdings.forEach(function (h) {
        var p = h.data[prev], d = h.data[m];
        if (p && p.val > 0 && d && d.ret !== null) { var x = p.val / tv * d.ret; c += x; contrib[h.name] = (contrib[h.name] || 0) + x * cum; }
      });
      var wp = SL.map(function (s) { var hv = 0; ds.holdings.forEach(function (h) { if (norm(h.sleeve) === norm(s.name) && h.data[prev] && h.data[prev].val > 0) hv += h.data[prev].val; }); return tv > 0 ? hv / tv : 0; });
      var rps = SL.map(function (s) {
        var d = s.data[m]; if (d && d.ret !== null) return d.ret;
        var a = 0, b = 0; ds.holdings.forEach(function (h) { var p = h.data[prev], x = h.data[m]; if (norm(h.sleeve) === norm(s.name) && p && p.val > 0 && x && x.ret !== null) { a += p.val * x.ret; b += p.val; } });
        return b > 0 ? a / b : 0;
      });
      cum *= 1 + c; rpAll.push(c);
      reported.push(ds.total.data[m] ? ds.total.data[m].ret : null);
      return { m: m, wp: wp, rps: rps, holdRet: c };
    });
    R.holdRet = compound(rpAll); R.reported = reported.some(function (x) { return x === null; }) ? null : compound(reported);
    var cl = Object.keys(contrib).map(function (k) { var h = ds.holdings.filter(function (x) { return x.name === k; })[0]; return { name: k, sleeve: h ? h.sleeve : '', c: contrib[k] }; }).sort(function (a, b) { return b.c - a.c; });
    R.contributors = cl.filter(function (x) { return x.c > 0; }).slice(0, 5); R.detractors = cl.filter(function (x) { return x.c < 0; }).reverse().slice(0, 5); R.contribAll = cl;
    if (R.reason) return R;
    // benchmark availability
    var missing = [];
    pol.forEach(function (p, s) { if (p.w > 0) { if (!p.series) missing.push(SL[s].name + ': no benchmark series chosen'); else ms.forEach(function (m) { if (p.series.ret[m] === undefined) missing.push(p.series.name + ' has no return for ' + m); }); } });
    if (missing.length) { R.reason = 'The benchmark needs more data: ' + missing.slice(0, 3).join('; ') + (missing.length > 3 ? ' (and ' + (missing.length - 3) + ' more)' : '') + '.'; return R; }
    var eff = SL.map(function () { return { alloc: 0, sel: 0 }; }), RpT = [], RbT = [], rows = [];
    perMonth.forEach(function (pm) {
      var rbs = pol.map(function (p, s) { if (p.series && p.series.ret[pm.m] !== undefined) return p.series.ret[pm.m]; return null; });
      var Rb = 0; pol.forEach(function (p, s) { if (p.w > 0) Rb += p.w * rbs[s]; });
      var Rp = dot(pm.wp, pm.rps), e = SL.map(function (sl, s) {
        var rb = rbs[s] === null ? pm.rps[s] : rbs[s];
        return { alloc: (pm.wp[s] - pol[s].w) * (rb - Rb), sel: pol[s].w * (pm.rps[s] - rb) + (pm.wp[s] - pol[s].w) * (pm.rps[s] - rb) };
      });
      RpT.push(Rp); RbT.push(Rb); rows.push(e);
    });
    var Rp = compound(RpT), Rb = compound(RbT);
    var kf = function (a, b) { return Math.abs(a - b) < 1e-12 ? 1 / (1 + a) : (Math.log(1 + a) - Math.log(1 + b)) / (a - b); }, k = kf(Rp, Rb);
    rows.forEach(function (e, t) { var kt = kf(RpT[t], RbT[t]) / k; e.forEach(function (x, s) { eff[s].alloc += x.alloc * kt; eff[s].sel += x.sel * kt; }); });
    R.sleeves = SL.map(function (s, i) {
      var wpAvg = mean(perMonth.map(function (pm) { return pm.wp[i]; }));
      return { name: s.name, wp: wpAvg, wb: pol[i].w, rp: compound(perMonth.map(function (pm) { return pm.rps[i]; })), rb: pol[i].series ? compound(ms.map(function (m) { return pol[i].series.ret[m] === undefined ? 0 : pol[i].series.ret[m]; })) : null, alloc: eff[i].alloc, sel: eff[i].sel, total: eff[i].alloc + eff[i].sel, series: pol[i].series ? pol[i].series.name : '' };
    });
    R.Rp = Rp; R.Rb = Rb; R.excess = Rp - Rb; R.alloc = sum(eff.map(function (e) { return e.alloc; })); R.sel = sum(eff.map(function (e) { return e.sel; }));
    R.ok = true;
    return R;
  };

  // ================= optimizer (asset-class level) =================
  /* P: {C (monthly cov), W (current), mu (annual), lb, ub, cB (cov with reference) or null, vB, goal, maxTE} */
  RE.optimiseCore = function (P) {
    var C = P.C, W = P.W, mu = P.mu, lb = P.lb, ub = P.ub, cB = P.cB || null, vB = P.vB || 0, S = W.length, notes = [], i;
    var free = [], fixed = [];
    for (i = 0; i < S; i++) (ub[i] - lb[i] > 1e-9 ? free : fixed).push(i);
    var varOf = function (x) { return dot(x, matVec(C, x)); };
    var teOf = function (x) { return cB ? Math.sqrt(Math.max(varOf(x) - 2 * dot(x, cB) + vB, 0) * 12) : null; };
    if (free.length < 2) return { x: W.slice(), notes: ['Nothing can move under the current limits.'] };
    var nf = free.length, fixSum = sum(fixed.map(function (k) { return W[k]; })), fixRet = sum(fixed.map(function (k) { return mu[k] * W[k]; }));
    var avgVar = mean(free.map(function (k) { return C[k][k]; })) || 1e-8, sc = 1 / (2 * avgVar), x0 = free.map(function (k) { return W[k]; });
    var ones = [new Array(nf).fill(1)], Ab = [], bb = [];
    free.forEach(function (k, a) { var r1 = new Array(nf).fill(0); r1[a] = 1; Ab.push(r1); bb.push(lb[k]); var r2 = new Array(nf).fill(0); r2[a] = -1; Ab.push(r2); bb.push(-ub[k]); });
    var muF = free.map(function (k) { return mu[k]; });
    /* minimise  cVar*var + cTE*TE^2 - cRet*mu'x  (scaled by 1/(2 avgVar)) over the linear limits */
    var solveFor = function (cVar, cTE, cRet, retTarget) {
      var H = zeros(nf, nf), f = new Array(nf).fill(0), a, b2, q = cVar + cTE, ridge = 1e-4 * Math.max(q, 1e-6);
      for (a = 0; a < nf; a++) {
        for (b2 = 0; b2 < nf; b2++) H[a][b2] = q * C[free[a]][free[b2]] / avgVar;
        H[a][a] += ridge;
        var cx = 0; fixed.forEach(function (k) { cx += C[free[a]][k] * W[k]; });
        f[a] = (q * cx - (cTE && cB ? cTE * cB[free[a]] : 0)) / avgVar - cRet * muF[a];
      }
      var Ain = Ab, bin = bb;
      if (retTarget !== null) { Ain = Ab.concat([muF]); bin = bb.concat([retTarget - fixRet - 1e-13]); }
      var xf = qpActiveSet(H, f, ones, Ain, bin, x0);
      if (!xf) xf = qp(H, f, Ain.map(function (r) { return r.map(function (v) { return -v; }); }), bin.map(function (v) { return -v; }), ones, [1 - fixSum]);
      var x = W.slice();
      free.forEach(function (k, a2) { x[k] = Math.min(ub[k], Math.max(lb[k], xf[a2])); });
      var gap = 1 - sum(x);
      for (a = 0; a < nf && Math.abs(gap) > 1e-13; a++) { var k = free[a], room = gap > 0 ? ub[k] - x[k] : lb[k] - x[k], mv = gap > 0 ? Math.min(gap, room) : Math.max(gap, room); x[k] += mv; gap -= mv; }
      return x;
    };
    /* smallest multiplier c >= 0 for which ok(fn(c)) holds; ok must become true as c grows. Returns the feasible end. */
    var search = function (fn, ok, iters) {
      var x = fn(0);
      if (ok(x)) return { x: x, met: true };
      var lo = 1e-6, hi = 1e-6, xh = fn(hi), n = 0;
      while (!ok(xh) && n++ < 18) { lo = hi; hi *= 8; xh = fn(hi); }
      if (!ok(xh)) return { x: xh, met: false };
      if (hi === lo) return { x: xh, met: true };
      for (n = 0; n < iters; n++) { var mid = Math.sqrt(lo * hi), xm = fn(mid); if (ok(xm)) { hi = mid; xh = xm; } else lo = mid; }
      return { x: xh, met: true };
    };
    var goal = P.goal, x, curRet = dot(W, mu), curVar = varOf(W), teLim = P.maxTE && cB ? P.maxTE : null;
    var teOk = function (xx) { return !teLim || teOf(xx) <= teLim + 1e-9; };
    var teNote = function (r) { if (!r.met) notes.push('The tracking-error limit cannot be met within the other limits; the closest result is shown.'); return r.x; };
    if (goal === 'min_te' && cB) x = solveFor(0, 1, 0, null);
    else if (goal === 'minrisk') x = teNote(search(function (g) { return solveFor(1, g, 0, null); }, teOk, 40));
    else if (goal === 'maxret_same_risk') {
      var varOk = function (xx) { return varOf(xx) <= curVar * (1 + 1e-9); };
      var inner = function (bTE) { return search(function (aVar) { return solveFor(aVar, bTE, 1, null); }, varOk, 45).x; };
      x = teNote(search(inner, teOk, 30));
      if (!teLim && dot(x, mu) < curRet - 1e-12) x = W.slice();
    } else {
      if (goal === 'min_te') notes.push('No risk reference series is loaded, so the lowest-risk goal was used instead.');
      x = teNote(search(function (g) { return solveFor(1, g, 0, curRet); }, teOk, 40));
    }
    for (i = 0; i < S; i++) if (Math.abs(x[i] - W[i]) < 5e-6) x[i] = W[i];
    var gap2 = 1 - sum(x);
    if (Math.abs(gap2) > 1e-12) for (i = 0; i < nf; i++) { var kk = free[i]; if (x[kk] + gap2 >= lb[kk] && x[kk] + gap2 <= ub[kk]) { x[kk] += gap2; break; } }
    return { x: x, notes: notes };
  };
  RE.optimise = function (A, st, riskBm) {
    var o = st.opt || {}, S = A.sleeves.length, C = A.CS, W = A.sw.slice(), i;
    var muHist = A.sleeves.map(function (s, k) { return mean(A.XS.map(function (r) { return r[k]; })) * 12; });
    var mu = A.sleeves.map(function (s, k) { var v = o.mu ? o.mu[s.name] : undefined; return v !== undefined && v !== null && v !== '' && isFinite(+v) ? +v : muHist[k]; });
    var maxCh = o.maxChange === null || o.maxChange === undefined || o.maxChange === '' ? 1 : Math.max(0, +o.maxChange), lock = o.lockIlliquid !== false;
    var lb = A.sleeves.map(function (s, k) { return Math.max(0, W[k] - maxCh, lock ? s.illiquidW : 0); });
    var ub = A.sleeves.map(function (s, k) { return lock && s.illiquidW >= W[k] - 1e-12 ? W[k] : Math.min(1, W[k] + maxCh); });
    for (i = 0; i < S; i++) { if (lb[i] > W[i]) lb[i] = W[i]; if (ub[i] < lb[i]) ub[i] = lb[i]; }
    var cB = null, vB = 0;
    if (riskBm) {
      var idx = []; A.months.forEach(function (ym, t) { if (riskBm.ret[ym] !== undefined) idx.push(t); });
      if (idx.length >= 6) { var b = idx.map(function (t) { return riskBm.ret[A.months[t]]; }); cB = A.sleeves.map(function (s, k) { return covar(idx.map(function (t) { return A.XS[t][k]; }), b); }); vB = variance(b); }
    }
    var stats = function (x) { var v = dot(x, matVec(C, x)); return { volA: Math.sqrt(Math.max(v, 0) * 12), ret: dot(x, mu), te: cB ? Math.sqrt(Math.max(v - 2 * dot(x, cB) + vB, 0) * 12) : null }; };
    var goal = o.goal || 'minrisk_same_return';
    var r = RE.optimiseCore({ C: C, W: W, mu: mu, lb: lb, ub: ub, cB: cB, vB: vB, goal: goal, maxTE: o.maxTE ? +o.maxTE : null });
    return { sleeves: A.sleeves.map(function (s) { return s.name; }), current: W, mu: mu, muHist: muHist, lb: lb, ub: ub, goal: goal, notes: r.notes, weights: r.x, before: stats(W), after: stats(r.x), hasRef: !!cB, changed: r.x.some(function (v, k) { return Math.abs(v - W[k]) > 5e-5; }) };
  };

  // ================= signals =================
  RE.signals = function (ds, asOf) {
    var list = RE.seriesList(ds, ['signal']).map(function (s) {
      var yms = Object.keys(s.lvl).sort(), last = yms[yms.length - 1];
      if (!last) return null;
      var v = s.lvl[last], all = yms.map(function (y) { return s.lvl[y]; }), below = all.filter(function (x) { return x <= v; }).length;
      var ch = function (k) { var p = s.lvl[ymAdd(last, -k)]; return p === undefined ? null : v - p; };
      var sd = stdev(all);
      return { name: s.name, ticker: s.ticker, asOf: last, value: v, ch1: ch(1), ch3: ch(3), ch12: ch(12), pct: all.length > 1 ? (below - 1) / (all.length - 1) : null, z: sd > 0 ? (v - mean(all)) / sd : null, n: all.length, from: yms[0], hist: yms.slice(-60).map(function (y) { return { ym: y, v: s.lvl[y] }; }) };
    }).filter(Boolean);
    var erp = list.filter(function (s) { return /erp|equity risk premium/i.test(s.name); })[0], ten = list.filter(function (s) { return /10\s*-?\s*y|usgg10/i.test(s.name + ' ' + s.ticker); })[0];
    var gauge = null;
    if (erp) gauge = { erp: erp.value, ten: ten ? ten.value : null, pct: erp.pct, n: erp.n, from: erp.from, asOf: erp.asOf, view: erp.pct === null ? 'none' : erp.pct < 0.25 ? 'bonds' : erp.pct > 0.75 ? 'equities' : 'neutral' };
    return { list: list, gauge: gauge };
  };

  // ================= demo data =================
  RE.demoDataset = function () {
    var seed = 20261110;
    function rnd() { seed |= 0; seed = seed + 0x6D2B79F5 | 0; var t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }
    function gauss() { var u = 0, v = 0; while (u === 0) u = rnd(); v = rnd(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); }
    var months = ymRange('2019-01', '2026-09'), T = months.length;
    var fn = ['Global equities', 'US Treasuries', 'High yield credit', 'US dollar', 'Oil'], vol = [0.044, 0.014, 0.023, 0.019, 0.09], mu = [0.007, 0.0025, 0.0045, 0.0005, 0.003];
    var corr = [[1, -0.15, 0.75, -0.35, 0.35], [-0.15, 1, 0.05, -0.1, -0.2], [0.75, 0.05, 1, -0.3, 0.4], [-0.35, -0.1, -0.3, 1, -0.25], [0.35, -0.2, 0.4, -0.25, 1]];
    var L = zeros(5, 5), i, j, k;
    for (i = 0; i < 5; i++) for (j = 0; j <= i; j++) { var s = corr[i][j]; for (k = 0; k < j; k++) s -= L[i][k] * L[j][k]; L[i][j] = i === j ? Math.sqrt(s) : s / L[j][j]; }
    var F = months.map(function () { var zz = [gauss(), gauss(), gauss(), gauss(), gauss()]; return fn.map(function (n, a) { var x = 0; for (var b = 0; b <= a; b++) x += L[a][b] * zz[b]; return mu[a] + vol[a] * x; }); });
    RE.SCENARIOS.forEach(function (sc) {
      if (sc.kind !== 'historical' || months.indexOf(sc.from) < 0 || months.indexOf(sc.to) < 0) return;
      var ms = ymRange(sc.from, sc.to), key = ['globalequities', 'ustreasuries', 'highyieldcredit', 'usdollar', 'oil'];
      ms.forEach(function (m) { var t = months.indexOf(m); key.forEach(function (kk, a) { F[t][a] = Math.pow(1 + sc.preset[kk], 1 / ms.length) - 1; }); });
    });
    var H = [
      ['US Equity Fund A', 'Equities', 1, 80, [1.0, 0, 0, 0, 0], 0.010], ['Global Equity Index', 'Equities', 1, 60, [1.0, 0, 0, 0, 0], 0.002], ['Technology Fund', 'Equities', 1, 40, [1.35, 0, 0, 0, 0], 0.035], ['Europe Equity Fund', 'Equities', 1, 50, [0.95, 0, 0, -0.5, 0], 0.018], ['Japan Equity Fund', 'Equities', 1, 20, [0.7, 0, 0, -0.4, 0], 0.025], ['Quant Equity Fund', 'Equities', 1, 60, [0.9, 0, 0, 0, 0.02], 0.015],
      ['Core Bond Fund', 'Fixed Income', 1, 90, [0.02, 0.9, 0.1, 0, 0], 0.004], ['Global Bond Fund', 'Fixed Income', 1, 70, [0.03, 0.8, 0.1, -0.25, 0], 0.005], ['Credit Income Fund', 'Fixed Income', 1, 60, [0.05, 0.3, 0.55, 0, 0], 0.006], ['Tactical Credit Fund', 'Fixed Income', 0, 50, [0.05, 0.1, 0.5, 0, 0], 0.009], ['Regional Bond Fund', 'Fixed Income', 1, 40, [0.05, 0.6, 0.2, 0, 0.01], 0.006],
      ['Macro Fund', 'Alternatives', 1, 45, [0.15, 0.2, 0, 0.1, 0.02], 0.02], ['Trend Fund', 'Alternatives', 1, 30, [-0.05, 0.15, 0, 0.15, 0.03], 0.025], ['Relative Value Fund', 'Alternatives', 1, 20, [0.02, 0.05, 0.05, 0, 0], 0.008], ['Property Fund', 'Alternatives', 0, 35, [0.12, 0.1, 0.1, 0, 0], 0.012], ['Infrastructure Fund', 'Alternatives', 0, 15, [0.08, 0.1, 0.05, 0, 0], 0.006], ['Distressed Debt Fund', 'Alternatives', 0, 15, [0.1, 0, 0.3, 0, 0], 0.012],
      ['Multi-Asset Fund', 'Multi-Asset', 1, 35, [0.65, 0.25, 0.05, 0, 0], 0.006],
      ['Head Office Building', 'Strategic', 0, 70, [0, 0, 0, 0, 0], 0], ['Land Bank', 'Strategic', 0, 25, [0, 0, 0, 0, 0], 0],
      ['Bank Deposits', 'Cash', 1, 60, [0, 0, 0, 0, 0], 0.0002], ['Money Market Fund', 'Cash', 1, 40, [0, 0, 0, 0, 0], 0.0002]
    ];
    var ds = { demo: true, months: ymRange('2025-12', '2026-09'), monthInfo: {}, holdings: [], sleeves: [], total: { data: {} }, series: {}, issues: [], benchmarkNote: '' };
    ds.months.forEach(function (m, a) { ds.monthInfo[m] = { hasReturn: a > 0 }; });
    var sl = {};
    H.forEach(function (h) {
      var rets = F.map(function (f) { var x = (h[1] === 'Cash' ? 0.0035 : h[1] === 'Strategic' ? 0 : 0.001) + h[5] * gauss(); for (var a = 0; a < 5; a++) x += h[4][a] * f[a]; return h[1] === 'Strategic' ? 0 : x; });
      var obs = {}, data = {}, v = h[3] * 1e6;
      months.forEach(function (m, t) { if (m <= '2025-12') obs[m] = rets[t]; });
      if (h[1] !== 'Strategic') RE.addSeries(ds, { name: h[0], type: 'holding', kind: 'return', obs: obs });
      ds.months.forEach(function (m, a) { var r = a === 0 ? null : rets[months.indexOf(m)]; if (a > 0) v *= 1 + r; data[m] = { val: v, ret: r, w: null }; });
      ds.holdings.push({ name: h[0], sleeve: h[1], liquid: !!h[2], data: data });
      if (!sl[h[1]]) { sl[h[1]] = { name: h[1], data: {} }; ds.sleeves.push(sl[h[1]]); }
    });
    ds.months.forEach(function (m, a) {
      var tv = sum(ds.holdings.map(function (h) { return h.data[m].val; })), prev = ds.months[a - 1], tr = 0;
      ds.holdings.forEach(function (h) { h.data[m].w = h.data[m].val / tv; });
      ds.sleeves.forEach(function (s) {
        var hs = ds.holdings.filter(function (h) { return h.sleeve === s.name; }), v = sum(hs.map(function (h) { return h.data[m].val; })), r = null;
        if (a > 0) { var pv = sum(hs.map(function (h) { return h.data[prev].val; })); r = sum(hs.map(function (h) { return h.data[prev].val * h.data[m].ret; })) / pv; }
        s.data[m] = { val: v, ret: r, w: v / tv };
      });
      if (a > 0) { var ptv = sum(ds.holdings.map(function (h) { return h.data[prev].val; })); tr = sum(ds.holdings.map(function (h) { return h.data[prev].val * h.data[m].ret; })) / ptv; }
      ds.total.data[m] = { val: tv, ret: a > 0 ? tr : null, w: 1 };
    });
    function add(name, type, fnc, ticker) { var obs = {}; months.forEach(function (m, t) { obs[m] = fnc(F[t], t); }); RE.addSeries(ds, { name: name, type: type, ticker: ticker || '', kind: 'return', obs: obs }); }
    fn.forEach(function (n, a) { add(n, 'factor', function (f) { return f[a]; }); });
    var gb = F.map(function (f) { return 0.85 * f[1] - 0.2 * f[3] * 0.3 + 0.004 * gauss(); });
    add('Global bonds', 'index', function (f, t) { return gb[t]; });
    add('50/50 reference', 'benchmark', function (f, t) { return 0.5 * f[0] + 0.5 * gb[t]; });
    add('Multi-Asset 35 fund', 'benchmark', function (f, t) { return 0.35 * f[0] + 0.65 * gb[t] - 0.0006 + 0.002 * gauss(); });
    function sig(name, start, sd, lo, hi, rev) { var obs = {}, v = start; months.forEach(function (m) { v += sd * gauss() + rev * ((lo + hi) / 2 - v); v = Math.min(hi, Math.max(lo, v)); obs[m] = v; }); RE.addSeries(ds, { name: name, type: 'signal', kind: 'level', obs: obs }); }
    sig('Implied ERP', 5.2, 0.14, 3.6, 6.2, 0.03); sig('US 10Y yield', 2.4, 0.2, 0.6, 5.0, 0.01); sig('2s10s curve', 0.3, 0.14, -1.0, 1.6, 0.04); sig('High yield spread', 4.2, 0.4, 2.6, 9.0, 0.06); sig('Dollar index', 97, 1.6, 88, 114, 0.03);
    return ds;
  };

  root.RE = RE;
  if (typeof module !== 'undefined' && module.exports) module.exports = RE;
})(typeof globalThis !== 'undefined' ? globalThis : this);
