/* Read FGR's management accounts workbook (sheet "2.1 FA by Invest") into the same shape as a parsed
   valuation sheet (XL.parseValuations), so it joins the estimates through sources.js.

   Layout: row 1 holds month-end dates from column D (a broken header such as #REF! leaves that month out);
   column A names the investment, column B its short "P. Pack ID", column C the accounting type.
   A "Financial assets at fair value" section (sub-headed Fixed Income, Equity, Alternatives, Managed Funds,
   Private Equity) is followed by a "Financial assets at cost" section listing the same investments in the
   same order.

   Monthly return per investment (Modified Dietz, flows at mid-month because their dates are not known):
     F_t = dCost_t (a purchase is booked at cost, which is its market value)
     r_t = (V_t - V_{t-1} - F_t) / (V_{t-1} + F_t / 2)
   so top-ups are not counted as performance. When cost falls (a sale or redemption) the realised gain is
   booked outside this sheet, so that month gets no return rather than a false loss. No return is given for
   a holding's first month, its exit month, or next to a missing month either. */
(function (root) {
  'use strict';
  var MG = {};
  var SLEEVE = { 'fixed income': 'Fixed Income', 'equity': 'Equities', 'alternatives': 'Alternative', 'managed funds': 'Global Multi-Asset', 'private equity': 'Strategic Investments' };
  var str = function (v) { return typeof v === 'string' ? v.replace(/\s+/g, ' ').trim() : ''; };
  var isNum = function (v) { return typeof v === 'number' && isFinite(v); };
  function serialYM(v) { var d = new Date(Math.round((v - 25569) * 86400000)); return d.getUTCFullYear() + '-' + ('0' + (d.getUTCMonth() + 1)).slice(-2); }
  function ymAdd(ym, k) { var y = +ym.slice(0, 4), m = +ym.slice(5, 7) - 1 + k; y += Math.floor(m / 12); m = ((m % 12) + 12) % 12; return y + '-' + ('0' + (m + 1)).slice(-2); }

  MG.sheetName = function (names) { return names.filter(function (n) { return /^2\.1\s*FA\s*by\s*Invest/i.test(n.trim()); })[0] || null; };

  /* Income lines ("Dividend Income - X", "Interest Income - X") from sheets 7.1 / 7.2: {label: {ym: amount}}. */
  MG.parseIncome = function (rows) {
    var hdr = (rows && rows[1]) || [], cols = [], out = {};
    for (var c = 1; c < hdr.length; c++) if (isNum(hdr[c]) && hdr[c] > 20000 && hdr[c] < 80000) cols.push({ c: c, ym: serialYM(hdr[c]) });
    for (var r = 2; r < (rows || []).length; r++) {
      var a = str(rows[r] && rows[r][1]), m = /income\s*-\s*(.+)$/i.exec(a);
      if (!m) continue;
      var d = out[m[1]] = out[m[1]] || {};
      cols.forEach(function (x) { var v = rows[r][x.c]; if (isNum(v) && v) d[x.ym] = (d[x.ym] || 0) + v; });
    }
    return out;
  };
  function incomeFor(full, id, income) {
    var f = full.toLowerCase(), hits = Object.keys(income).filter(function (k) {
      var key = k.toLowerCase().replace(/\.+$/, '').trim();
      return key.length >= 3 && (f.indexOf(key) === 0 || key.indexOf(f.slice(0, Math.max(8, key.length))) === 0 || (id && key === id.toLowerCase()));
    });
    return hits.length === 1 ? hits[0] : null;
  }

  MG.parse = function (rows, file, sheetName, income) {
    income = income || {};
    var issues = [], hdr = rows[1] || [], cols = [], bad = 0;
    for (var c = 4; c < hdr.length; c++) {
      var v = hdr[c];
      if (isNum(v) && v > 20000 && v < 80000) cols.push({ c: c, ym: serialYM(v) });
      else if (v && typeof v === 'object' && v.err) bad++;
    }
    if (!cols.length) throw new Error('no month-end dates in row 1 of “' + sheetName + '”');
    var seen = {}; cols = cols.filter(function (x) { if (seen[x.ym]) return false; seen[x.ym] = 1; return true; });
    var yms = cols.map(function (x) { return x.ym; }), missing = [];
    for (var i = 1; i < yms.length; i++) for (var m = ymAdd(yms[i - 1], 1); m < yms[i]; m = ymAdd(m, 1)) missing.push(m);
    if (bad || missing.length) issues.push({ level: 'warn', text: '“' + sheetName + '”: ' + (missing.length ? missing.length + ' month(s) have no readable date in row 1 (' + missing.slice(0, 3).join(', ') + (missing.length > 3 ? ', …' : '') + '), so they are missing and the returns next to them are not calculated.' : bad + ' header cells show an Excel error.') });

    var sec = null, sleeve = null, fv = [], cost = [];
    for (var r = 2; r < rows.length; r++) {
      var row = rows[r]; if (!row) continue;
      var a = str(row[1]), lo = a.toLowerCase();
      if (/assets\s+at\s+fair\s+value/.test(lo)) { sec = 'fv'; continue; }
      if (/assets\s+at\s+cost/.test(lo)) { sec = sec === 'fv' || sec === 'between' || sec === null ? 'cost' : 'end'; sleeve = null; continue; }
      if (lo === 'difference') { sec = sec === 'fv' ? 'between' : sec; continue; }
      if (SLEEVE[lo] !== undefined && !str(row[3])) { sleeve = SLEEVE[lo]; continue; }
      if (!a || (sec !== 'fv' && sec !== 'cost')) continue;
      var data = {}; cols.forEach(function (x) { var v = row[x.c]; data[x.ym] = isNum(v) ? v : null; });
      (sec === 'fv' ? fv : cost).push({ full: a, id: str(row[2]) || null, sleeve: sleeve, data: data });
    }
    if (!fv.length) throw new Error('no investments found under “Financial assets at fair value”');
    var costOk = cost.length === fv.length;
    if (!costOk) issues.push({ level: 'warn', text: '“' + sheetName + '”: the at-cost section lists ' + cost.length + ' investments and the fair-value section ' + fv.length + ', so flows cannot be separated; returns are the change in value and include top-ups and redemptions.' });

    var flowMonths = 0, disposals = 0, odd = [], peFlows = 0, incUsed = [];
    var holdings = fv.filter(function (h) { return yms.some(function (y) { return (h.data[y] || 0) !== 0; }); }).map(function (h) {
      var ci = fv.indexOf(h), C = costOk ? cost[ci].data : null, d = {}, ik = incomeFor(h.full, h.id, income), I = ik ? income[ik] : {};
      if (ik) incUsed.push(ik + ' → ' + h.full);
      yms.forEach(function (ym, k) {
        var V = h.data[ym], prev = k > 0 && yms[k - 1] === ymAdd(ym, -1) ? yms[k - 1] : null, ret = null;
        var V0 = prev ? h.data[prev] : null;
        if (prev && isNum(V) && isNum(V0) && V0 > 0 && V > 0) {
          var F = 0, dC = C && isNum(C[ym]) && isNum(C[prev]) ? C[ym] - C[prev] : 0;
          if (dC < -1e-6 * V0) { disposals++; ret = null; }  // realised gain is not in this sheet: leave the month out rather than show a false loss
          else {
            F = dC;
            if (F > 1e-6 * V0) { flowMonths++; if (h.sleeve === 'Strategic Investments') peFlows++; }
            var den = V0 + F / 2;
            ret = den > 0 ? (V - V0 - F + (I[ym] || 0)) / den : null;
            if (ret !== null && Math.abs(ret) > 0.5) { odd.push(ym + ' ' + (h.id || h.full) + ' (' + (ret * 100).toFixed(0) + '%)'); ret = null; }
          }
        }
        d[ym] = { val: isNum(V) ? V : null, ret: ret, w: null, err: null };
      });
      return { name: h.id || h.full, key: h.id || h.full, fullName: h.full, sleeve: h.sleeve || 'Other', liquid: null, data: d, incomeLine: ik };
    });
    if (flowMonths) issues.push({ level: 'info', text: '“' + sheetName + '”: ' + flowMonths + ' holding-months had a top-up; it is taken out of the return (its date is not known, so it is assumed mid-month).' });
    if (odd.length) issues.push({ level: 'warn', text: '“' + sheetName + '”: ' + odd.length + ' holding-month(s) would show a return beyond ±50% after taking out the change in cost, which suggests a cost entry that is not a cash flow (for example a reclassification). They are left out: ' + odd.slice(0, 4).join(', ') + (odd.length > 4 ? ', …' : '') + '.' });
    if (peFlows) issues.push({ level: 'warn', text: '“' + sheetName + '”: ' + peFlows + ' private-equity or strategic holding-month(s) had a capital call; their returns are less reliable.' });
    if (incUsed.length) issues.push({ level: 'info', text: '“' + sheetName + '”: income added for ' + incUsed.length + ' holding(s): ' + incUsed.slice(0, 5).join('; ') + (incUsed.length > 5 ? '; …' : '') + '.' });
    if (disposals) issues.push({ level: 'warn', text: '“' + sheetName + '”: ' + disposals + ' holding-months had a sale or redemption. The realised gain is not in this sheet, so those months have no return rather than a wrong one.' });
    return {
      sheet: sheetName, file: file, layout: 'management accounts', issues: issues, benchmarkNote: '',
      months: yms.map(function (y, k) { return { ym: y, hasReturn: k > 0 && yms[k - 1] === ymAdd(y, -1), date: null }; }),
      holdings: holdings, sleeves: [], total: null
    };
  };

  /* Match management-accounts holdings to holdings of the other files by value: the same investment shows the
     same month-end value in both (within tol) at a month both cover. Returns {accountsName: {to, months, how}}. */
  MG.matchByValue = function (mg, others, tol) {
    tol = tol || 0.0005;
    var cand = {};
    mg.holdings.forEach(function (h) {
      var votes = {};
      others.forEach(function (pv) {
        pv.holdings.forEach(function (o) {
          var seen = {};
          Object.keys(o.data).forEach(function (ym) {
            var a = h.data[ym], b = o.data[ym];
            if (!seen[ym] && a && b && a.val > 0 && b.val > 0 && Math.abs(a.val / b.val - 1) <= tol) { seen[ym] = 1; votes[o.name] = (votes[o.name] || {}); votes[o.name][ym] = 1; }
          });
        });
      });
      var ok = Object.keys(votes).filter(function (n) { return Object.keys(votes[n]).length >= 2; });
      if (ok.length === 1) cand[h.key] = { to: ok[0], months: Object.keys(votes[ok[0]]).length, how: 'value' };
    });
    var used = {}; Object.keys(cand).forEach(function (k) { used[cand[k].to] = (used[cand[k].to] || 0) + 1; });
    Object.keys(cand).forEach(function (k) { if (used[cand[k].to] > 1) delete cand[k]; });  // one-to-one only
    return cand;
  };

  /* Rename holdings in place: map {accountsName: otherName}. */
  MG.rename = function (mg, map) {
    mg.holdings.forEach(function (h) { h.name = map[h.key] || h.key; });
    return mg;
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = MG; else root.MG = MG;
})(this);
