/* Minimal .xlsx reader: zip + inflate + sheet XML, no dependencies.
   Works in browsers (file:// included) and in Node for testing. */
(function (root) {
  'use strict';
  var XL = {};

  // ---------- inflate (RFC 1951) ----------
  var LBASE = [3,4,5,6,7,8,9,10,11,13,15,17,19,23,27,31,35,43,51,59,67,83,99,115,131,163,195,227,258];
  var LEXT  = [0,0,0,0,0,0,0,0,1,1,1,1,2,2,2,2,3,3,3,3,4,4,4,4,5,5,5,5,0];
  var DBASE = [1,2,3,4,5,7,9,13,17,25,33,49,65,97,129,193,257,385,513,769,1025,1537,2049,3073,4097,6145,8193,12289,16385,24577];
  var DEXT  = [0,0,0,0,1,1,2,2,3,3,4,4,5,5,6,6,7,7,8,8,9,9,10,10,11,11,12,12,13,13];
  var CLORDER = [16,17,18,0,8,7,9,6,10,5,11,4,12,3,13,2,14,1,15];

  function buildHuff(lengths, off, n) {
    var count = new Uint16Array(16), symbol = new Uint16Array(n), offs = new Uint16Array(16), i;
    for (i = 0; i < n; i++) count[lengths[off + i]]++;
    count[0] = 0;
    for (i = 1; i < 16; i++) offs[i] = offs[i - 1] + count[i - 1];
    for (i = 0; i < n; i++) if (lengths[off + i]) symbol[offs[lengths[off + i]]++] = i;
    return { count: count, symbol: symbol };
  }
  var FIXED = null;
  function fixedTables() {
    if (FIXED) return FIXED;
    var l = new Uint8Array(288), i;
    for (i = 0; i < 144; i++) l[i] = 8;
    for (; i < 256; i++) l[i] = 9;
    for (; i < 280; i++) l[i] = 7;
    for (; i < 288; i++) l[i] = 8;
    var d = new Uint8Array(30).fill(5);
    FIXED = { len: buildHuff(l, 0, 288), dist: buildHuff(d, 0, 30) };
    return FIXED;
  }

  XL.inflateRaw = function (src, expectedLen) {
    var pos = 0, bitBuf = 0, bitCnt = 0, op = 0;
    var out = new Uint8Array(expectedLen || Math.max(4096, src.length * 4));
    function grow(n) {
      if (op + n <= out.length) return;
      var nl = out.length * 2;
      while (nl < op + n) nl *= 2;
      var o2 = new Uint8Array(nl); o2.set(out.subarray(0, op)); out = o2;
    }
    function bits(n) {
      if (n === 0) return 0;
      while (bitCnt < n) {
        if (pos >= src.length) throw new Error('Unexpected end of compressed data');
        bitBuf |= src[pos++] << bitCnt; bitCnt += 8;
      }
      var v = bitBuf & ((1 << n) - 1);
      bitBuf >>>= n; bitCnt -= n;
      return v;
    }
    function decode(h) {
      var code = 0, first = 0, index = 0, len, c;
      for (len = 1; len <= 15; len++) {
        code |= bits(1);
        c = h.count[len];
        if (code - c < first) return h.symbol[index + (code - first)];
        index += c; first += c; first <<= 1; code <<= 1;
      }
      throw new Error('Invalid Huffman code');
    }
    function codes(lh, dh) {
      var sym, len, dist, d, i;
      for (;;) {
        sym = decode(lh);
        if (sym < 256) { grow(1); out[op++] = sym; }
        else if (sym === 256) return;
        else {
          sym -= 257;
          if (sym >= 29) throw new Error('Invalid length symbol');
          len = LBASE[sym] + bits(LEXT[sym]);
          d = decode(dh);
          if (d >= 30) throw new Error('Invalid distance symbol');
          dist = DBASE[d] + bits(DEXT[d]);
          if (dist > op) throw new Error('Invalid distance');
          grow(len);
          for (i = 0; i < len; i++) { out[op] = out[op - dist]; op++; }
        }
      }
    }
    var last, type;
    do {
      last = bits(1); type = bits(2);
      if (type === 0) {
        bitBuf = 0; bitCnt = 0;
        var n = src[pos] | (src[pos + 1] << 8); pos += 4;
        grow(n); out.set(src.subarray(pos, pos + n), op); op += n; pos += n;
      } else if (type === 1) {
        var f = fixedTables(); codes(f.len, f.dist);
      } else if (type === 2) {
        var nlen = bits(5) + 257, ndist = bits(5) + 1, ncode = bits(4) + 4;
        var lengths = new Uint8Array(320), i;
        for (i = 0; i < ncode; i++) lengths[CLORDER[i]] = bits(3);
        var ch = buildHuff(lengths, 0, 19);
        var ll = new Uint8Array(320), idx = 0, s, prev, rep;
        while (idx < nlen + ndist) {
          s = decode(ch);
          if (s < 16) ll[idx++] = s;
          else {
            prev = 0;
            if (s === 16) { if (idx === 0) throw new Error('Invalid repeat'); prev = ll[idx - 1]; rep = 3 + bits(2); }
            else if (s === 17) rep = 3 + bits(3);
            else rep = 11 + bits(7);
            if (idx + rep > nlen + ndist) throw new Error('Invalid code lengths');
            while (rep--) ll[idx++] = prev;
          }
        }
        codes(buildHuff(ll, 0, nlen), buildHuff(ll, nlen, ndist));
      } else throw new Error('Invalid block type');
    } while (!last);
    return out.subarray(0, op);
  };

  // ---------- zip ----------
  function u16(b, o) { return b[o] | (b[o + 1] << 8); }
  function u32(b, o) { return (b[o] | (b[o + 1] << 8) | (b[o + 2] << 16) | (b[o + 3] << 24)) >>> 0; }
  var decoder = new TextDecoder('utf-8');

  XL.unzip = function (buf) {
    var b = buf instanceof Uint8Array ? buf : new Uint8Array(buf);
    var e = -1, i;
    for (i = b.length - 22; i >= Math.max(0, b.length - 66000); i--) {
      if (b[i] === 0x50 && b[i + 1] === 0x4b && b[i + 2] === 0x05 && b[i + 3] === 0x06) { e = i; break; }
    }
    if (e < 0) throw new Error('This does not look like an Excel .xlsx file.');
    var n = u16(b, e + 10), p = u32(b, e + 16), files = {};
    for (i = 0; i < n; i++) {
      if (u32(b, p) !== 0x02014b50) throw new Error('The file looks damaged (zip directory).');
      var method = u16(b, p + 10), csize = u32(b, p + 20), usize = u32(b, p + 24);
      var nl = u16(b, p + 28), el = u16(b, p + 30), cl = u16(b, p + 32), lo = u32(b, p + 42);
      var name = decoder.decode(b.subarray(p + 46, p + 46 + nl));
      files[name] = { method: method, csize: csize, usize: usize, lo: lo };
      p += 46 + nl + el + cl;
    }
    return {
      names: Object.keys(files),
      has: function (name) { return !!files[name]; },
      bytes: function (name) {
        var f = files[name];
        if (!f) return null;
        if (u32(b, f.lo) !== 0x04034b50) throw new Error('The file looks damaged (zip entry).');
        var start = f.lo + 30 + u16(b, f.lo + 26) + u16(b, f.lo + 28);
        var data = b.subarray(start, start + f.csize);
        if (f.method === 0) return data;
        if (f.method === 8) return XL.inflateRaw(data, f.usize);
        throw new Error('Unsupported compression in this file.');
      },
      text: function (name) { var d = this.bytes(name); return d ? decoder.decode(d) : null; }
    };
  };

  // ---------- xlsx ----------
  function unesc(s) {
    if (s.indexOf('&') < 0) return s;
    return s.replace(/&#x([0-9a-fA-F]+);/g, function (m, h) { return String.fromCodePoint(parseInt(h, 16)); })
      .replace(/&#(\d+);/g, function (m, d) { return String.fromCodePoint(parseInt(d, 10)); })
      .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&amp;/g, '&');
  }
  function attr(s, name) {
    var m = new RegExp('(?:^|\\s)' + name + '="([^"]*)"').exec(s);
    return m ? m[1] : null;
  }
  function colIndex(ref) {
    var c = 0, i, ch;
    for (i = 0; i < ref.length; i++) {
      ch = ref.charCodeAt(i);
      if (ch >= 65 && ch <= 90) c = c * 26 + (ch - 64); else break;
    }
    return c;
  }
  XL.colLetter = function (n) { var s = ''; while (n > 0) { var m = (n - 1) % 26; s = String.fromCharCode(65 + m) + s; n = (n - m - 1) / 26; } return s; };

  XL.open = function (buf) {
    var zip = XL.unzip(buf);
    var wbXml = zip.text('xl/workbook.xml');
    if (!wbXml) throw new Error('This file is not an Excel workbook (.xlsx).');
    var rels = {}, relXml = zip.text('xl/_rels/workbook.xml.rels') || '', m;
    var relRe = /<Relationship\b([^>]*)\/?>/g;
    while ((m = relRe.exec(relXml))) {
      var t = attr(m[1], 'Target') || '';
      if (t.charAt(0) === '/') t = t.slice(1); else if (t.indexOf('xl/') !== 0) t = 'xl/' + t;
      rels[attr(m[1], 'Id')] = t;
    }
    var sheets = [], shRe = /<sheet\b([^>]*)\/?>/g;
    while ((m = shRe.exec(wbXml))) {
      sheets.push({ name: unesc(attr(m[1], 'name') || ''), path: rels[attr(m[1], 'r:id')], hidden: !!attr(m[1], 'state') && attr(m[1], 'state') !== 'visible' });
    }
    var shared = null;
    function sharedStrings() {
      if (shared) return shared;
      shared = [];
      var x = zip.text('xl/sharedStrings.xml');
      if (!x) return shared;
      var siRe = /<si\b[^>]*>([\s\S]*?)<\/si>|<si\b[^>]*\/>/g, mm;
      while ((mm = siRe.exec(x))) {
        var body = (mm[1] || '').replace(/<rPh\b[\s\S]*?<\/rPh>/g, '');
        var s = '', tRe = /<t\b[^>]*>([\s\S]*?)<\/t>/g, tm;
        while ((tm = tRe.exec(body))) s += tm[1];
        shared.push(unesc(s));
      }
      return shared;
    }
    return {
      sheetNames: sheets.map(function (s) { return s.name; }),
      /* returns rows[r][c] (1-based, sparse). Values: number | string | boolean | {err:'#NAME?'} */
      sheet: function (name, maxRow) {
        var sh = sheets.filter(function (s) { return s.name === name; })[0];
        if (!sh || !sh.path) return null;
        var x = zip.text(sh.path);
        if (!x) return null;
        var ss = sharedStrings(), rows = [], rowRe = /<row\b([^>]*)>([\s\S]*?)<\/row>/g, rm, rn = 0;
        maxRow = maxRow || 5000;
        while ((rm = rowRe.exec(x))) {
          var ra = attr(rm[1], 'r'); rn = ra ? parseInt(ra, 10) : rn + 1;
          if (rn > maxRow) break;
          var cells = [], cRe = /<c\b([^>]*?)(?:\/>|>([\s\S]*?)<\/c>)/g, cm, cn = 0;
          while ((cm = cRe.exec(rm[2]))) {
            var ref = attr(cm[1], 'r'); cn = ref ? colIndex(ref) : cn + 1;
            if (cm[2] === undefined) continue;
            var ty = attr(cm[1], 't'), vm = /<v\b[^>]*>([\s\S]*?)<\/v>/.exec(cm[2]), v;
            if (ty === 'inlineStr') { var im = /<t\b[^>]*>([\s\S]*?)<\/t>/.exec(cm[2]); v = im ? unesc(im[1]) : ''; }
            else if (!vm) continue;
            else if (ty === 's') v = ss[parseInt(vm[1], 10)];
            else if (ty === 'str') v = unesc(vm[1]);
            else if (ty === 'b') v = vm[1] === '1';
            else if (ty === 'e') v = { err: unesc(vm[1]) };
            else { v = parseFloat(vm[1]); if (isNaN(v)) v = unesc(vm[1]); }
            if (v !== undefined && v !== '') cells[cn] = v;
          }
          if (cells.length) rows[rn] = cells;
        }
        return rows;
      }
    };
  };

  // ---------- helpers shared by the parsers ----------
  var isNum = function (v) { return typeof v === 'number' && isFinite(v); };
  var isErr = function (v) { return v && typeof v === 'object' && v.err; };
  var str = function (v) { return typeof v === 'string' ? v.replace(/\s+/g, ' ').trim() : ''; };
  var isDateSerial = function (v) { return isNum(v) && v > 32000 && v < 73050; };
  XL.serialToYM = function (v) {
    var d = new Date(Math.round((v - 25569) * 86400000));
    return d.getUTCFullYear() + '-' + ('0' + (d.getUTCMonth() + 1)).slice(-2);
  };
  XL.serialToISO = function (v) { return new Date(Math.round((v - 25569) * 86400000)).toISOString().slice(0, 10); };

  /* ---------- FGR valuations sheet ----------
     Layout: col A liquidity flag, col B asset class, col C name; row 1 has a date at the
     start of every month block, followed by "M-%Return", "%", "M-Return", ... */
  XL.findValuationSheets = function (wb) {
    return wb.sheetNames.filter(function (n) { return /actual\s+valuation/i.test(n); });
  };

  XL.parseValuations = function (rows, sheetName) {
    var out = { sheet: sheetName, months: [], holdings: [], sleeves: [], total: null, issues: [], benchmarkNote: '' };
    var hdr = rows[1];
    if (!hdr) throw new Error('Sheet "' + sheetName + '" has no header row.');
    var c, blocks = [];
    for (c = 1; c < hdr.length; c++) if (isDateSerial(hdr[c])) {
      var ymc = XL.serialToYM(hdr[c]), prevB = blocks[blocks.length - 1];
      if (prevB && ymc <= prevB.ym) {
        var yy = +prevB.ym.slice(0, 4), mm = +prevB.ym.slice(5, 7) + 1; if (mm > 12) { mm = 1; yy++; }
        var fixed = yy + '-' + ('0' + mm).slice(-2);
        out.issues.push({ level: 'info', text: '"' + sheetName + '": the date ' + XL.serialToISO(hdr[c]) + ' in row 1 is out of order and was read as ' + fixed + '.' });
        ymc = fixed;
      }
      blocks.push({ col: c, ym: ymc, date: XL.serialToISO(hdr[c]) });
    }
    if (!blocks.length) throw new Error('No month-end dates found in row 1 of "' + sheetName + '". If the file has never been opened in Excel, open it there, let it calculate, save it and load it again.');
    blocks.forEach(function (b, i) {
      var end = i + 1 < blocks.length ? blocks[i + 1].col : b.col + 6;
      b.valCol = b.col;
      for (c = b.col + 1; c < end; c++) {
        var h = str(hdr[c]);
        if (/^m-?\s*%\s*return/i.test(h) && !b.retCol) b.retCol = c;
        else if ((h === '%' || /^%\s*exposure/i.test(h)) && !b.wCol) b.wCol = c;
      }
    });
    // de-duplicate months (keep the first block for each month)
    var seen = {};
    blocks = blocks.filter(function (b) { if (seen[b.ym]) return false; seen[b.ym] = 1; return true; });
    out.months = blocks.map(function (b) { return { ym: b.ym, date: b.date, hasReturn: !!b.retCol }; });

    function readRow(r) {
      var d = {};
      blocks.forEach(function (b) {
        var v = r[b.valCol], ret = b.retCol ? r[b.retCol] : undefined, w = b.wCol ? r[b.wCol] : undefined;
        d[b.ym] = {
          val: isNum(v) ? v : null, ret: isNum(ret) ? ret : null, w: isNum(w) ? w : null,
          err: isErr(v) || isErr(ret) ? (isErr(v) ? v.err : ret.err) : null
        };
      });
      return d;
    }
    var curSleeve = null, r, n = rows.length, flagged = false;
    for (r = 2; r < Math.min(n, 120); r++) if (rows[r] && /^(liquid|illiquid)$/i.test(str(rows[r][1]))) { flagged = true; break; }
    out.layout = flagged ? 'flagged' : 'class-name';
    for (r = 2; r < n; r++) {
      var row = rows[r];
      if (!row) continue;
      if (!flagged) {
        var a2 = str(row[1]), b2 = str(row[2]), nb = b2.replace(/^-\s*/, '');
        if (/portfolio/i.test(a2)) { out.total = { name: a2, data: readRow(row) }; break; }
        if (!b2 || /^roi$/i.test(b2) || /^\*?\s*note/i.test(b2)) continue;
        if (a2 && a2.toLowerCase().replace(/\W+/g, '') === b2.toLowerCase().replace(/\W+/g, '')) { curSleeve = b2; out.sleeves.push({ name: b2, data: readRow(row) }); continue; }
        if (!curSleeve || (!a2 && b2.charAt(0) !== '-')) continue;
        out.holdings.push({ name: nb, sleeve: curSleeve, liquid: null, data: readRow(row) });
        continue;
      }
      var liq = str(row[1]).toLowerCase(), cls = str(row[2]), name = str(row[3]);
      if (/portfolio/i.test(cls) && !name) { out.total = { name: cls, data: readRow(row) }; break; }
      if (/^\*?\s*note/i.test(name)) { out.benchmarkNote = name; continue; }
      if (!name) continue;
      if (!liq) {
        if (cls) { curSleeve = name; out.sleeves.push({ name: name, data: readRow(row) }); }
        continue; // sub-breakdowns (no flag, no class) are skipped
      }
      if (liq !== 'liquid' && liq !== 'illiquid') continue;
      if (!curSleeve) continue;
      out.holdings.push({ name: name.replace(/^-\s*/, ''), sleeve: curSleeve, liquid: liq === 'liquid', data: readRow(row) });
    }
    // benchmark note may sit below the total row
    for (var rr = r; rr < Math.min(n, r + 12) && !out.benchmarkNote; rr++) {
      var nr = rows[rr]; if (!nr) continue;
      for (c = 1; c <= 4; c++) if (/benchmark is/i.test(str(nr[c]))) out.benchmarkNote = str(nr[c]);
    }
    if (!out.total) out.issues.push({ level: 'warn', text: 'No "Portfolio" total row was found in "' + sheetName + '"; totals are rebuilt from the holdings.' });
    if (!out.holdings.length) throw new Error('No holdings were found in "' + sheetName + '". The app expects either the liquidity flag in column A, the asset class in B and the name in C, or the asset class in A and the name in B. If the file has never been opened in Excel, open it there, let it calculate, save it and load it again.');
    // month-level checks
    out.months.forEach(function (m) {
      var bad = out.holdings.filter(function (h) { return h.data[m.ym].err; }).map(function (h) { return h.name; });
      var mt = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][+m.ym.slice(5, 7) - 1] + ' ' + m.ym.slice(0, 4);
      if (bad.length) out.issues.push({ level: 'error', ym: m.ym, text: mt + ': ' + bad.length + (bad.length === 1 ? ' holding shows' : ' holdings show') + ' an Excel error such as #NAME? (' + bad.slice(0, 4).join(', ') + (bad.length > 4 ? ', …' : '') + '). Re-save the workbook with Bloomberg connected, or paste those cells as values.' });
    });
    return out;
  };

  /* ---------- history template ----------
     Sheet "Prices": column A holds labels; each series uses two columns (date, level).
     Sheet "Manual": row 1 names, row 2 types, column A month dates; values in percent. */
  XL.parseHistory = function (wb) {
    var res = { series: [], issues: [] };
    var names = wb.sheetNames;
    var pName = names.filter(function (n) { return /^(market\s+)?prices?$/i.test(n.trim()); })[0];
    var mName = names.filter(function (n) { return /^(market\s+)?manual/i.test(n.trim()); })[0];
    if (!pName && !mName) throw new Error('This workbook has no "Market prices" or "Market manual" sheet, so it holds no market history.');
    if (pName) {
      var rows = wb.sheet(pName, 2000) || [], lab = {}, r, c;
      for (r = 1; r < Math.min(rows.length, 30); r++) {
        var a = str(rows[r] && rows[r][1]).toLowerCase();
        if (/series name/.test(a)) lab.name = r; else if (/ticker/.test(a)) lab.ticker = r;
        else if (/^type/.test(a)) lab.type = r; else if (/^field/.test(a)) lab.field = r;
      }
      if (!lab.name) res.issues.push({ level: 'error', text: 'The "Prices" sheet has no "Series name" row in column A.' });
      else {
        var nameRow = rows[lab.name] || [];
        for (c = 2; c < nameRow.length; c++) {
          var nm = str(nameRow[c]); if (!nm) continue;
          var s = { name: nm, ticker: lab.ticker ? str((rows[lab.ticker] || [])[c]) : '', type: (lab.type ? str((rows[lab.type] || [])[c]) : '').toLowerCase() || 'holding', kind: 'level', obs: {} }, cnt = 0, errs = 0;
          for (r = lab.name + 1; r < rows.length; r++) {
            var rw = rows[r]; if (!rw) continue;
            if (isErr(rw[c]) || isErr(rw[c + 1])) { errs++; continue; }
            if (isDateSerial(rw[c]) && isNum(rw[c + 1])) { s.obs[XL.serialToYM(rw[c])] = rw[c + 1]; cnt++; }
          }
          if (cnt) res.series.push(s);
          else res.issues.push({ level: errs ? 'error' : 'warn', text: 'Prices: "' + nm + '" has no data' + (errs ? ' (Excel shows an error – is Bloomberg connected, and is the ticker/field right?)' : ' yet.') });
        }
      }
    }
    if (mName) {
      var mr = wb.sheet(mName, 2000) || [], h1 = mr[1] || [], h2 = mr[2] || [], cc, r2, maxAbs = 0;
      var cols = [];
      for (cc = 2; cc < h1.length; cc++) if (str(h1[cc])) cols.push({ c: cc, s: { name: str(h1[cc]), ticker: '', type: str(h2[cc]).toLowerCase() || 'holding', kind: 'return', obs: {} } });
      for (r2 = 3; r2 < mr.length; r2++) {
        var row2 = mr[r2]; if (!row2 || !isDateSerial(row2[1])) continue;
        var ym = XL.serialToYM(row2[1]);
        cols.forEach(function (k) { if (isNum(row2[k.c])) { k.s.obs[ym] = row2[k.c]; if (k.s.type !== 'signal') maxAbs = Math.max(maxAbs, Math.abs(row2[k.c])); } });
      }
      var pct = !(maxAbs > 0 && maxAbs < 0.5);
      if (!pct) res.issues.push({ level: 'warn', text: 'Manual sheet: values look like decimals (0.012) rather than percent (1.2), so they were read as decimals.' });
      cols.forEach(function (k) {
        if (!Object.keys(k.s.obs).length) return;
        if (k.s.type === 'signal') k.s.kind = 'level';
        else if (pct) Object.keys(k.s.obs).forEach(function (y) { k.s.obs[y] /= 100; });
        res.series.push(k.s);
      });
    }
    return res;
  };

  root.XL = XL;
  if (typeof module !== 'undefined' && module.exports) module.exports = XL;
})(typeof globalThis !== 'undefined' ? globalThis : this);
