/* Laura Screen paste-box parser. Runs in the page and in Node (tests).
 *
 * parse(text, map) -> { items: [...], attention: n }
 *   map: { TICKER: [name, "S"|"E", cik|null, commonClass 1|0|null] }  (site/tickers.json .t)
 * Each item: { input, status, ticker?, tickers?, name?, suggestions?: [{ticker,name}], note? }
 *   status: "stock" | "etf" | "name" | "ambiguous" | "notfound"
 */
(function (root) {
  "use strict";

  var SUFFIXES = /\b(incorporated|inc|corporation|corp|company|co|ltd|limited|plc|holdings?|group|sa|nv|ag|the|class [a-c]|new|del|de|cl [a-c])\b/g;

  function canon(t) {
    return t.trim().toUpperCase().replace(/[./]/g, "-");
  }

  function normName(s) {
    return s.toLowerCase()
      .replace(/\/[a-z]{2,4}\/?$/i, " ")        // SEC state suffixes like /CAN/, /DE/
      .replace(/&/g, " and ")
      .replace(/[^a-z0-9 ]+/g, " ")
      .replace(SUFFIXES, " ")
      .replace(/\s+/g, " ").trim();
  }

  // Title-case word with at least one lowercase letter after the first: "Apple", "Inc.", "Newsmax".
  function isNameWord(tok) {
    return /^[A-Z][a-z][A-Za-z'&.\-]*$/.test(tok) || /^(Inc|Co|Corp|Ltd|Plc|LLC)\.?$/.test(tok);
  }

  function tokenize(text) {
    return String(text || "").split(/[\s,;$]+/).map(function (t) {
      return t.replace(/^[^A-Za-z0-9]+|[^A-Za-z0-9.]+$/g, "");
    }).filter(Boolean);
  }

  function lev(a, b) {
    var m = a.length, n = b.length, d = [], i, j;
    for (i = 0; i <= m; i++) { d[i] = [i]; }
    for (j = 0; j <= n; j++) { d[0][j] = j; }
    for (i = 1; i <= m; i++) {
      for (j = 1; j <= n; j++) {
        d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      }
    }
    return d[m][n];
  }

  function makeIndex(map) {
    if (map.__idx) { return map.__idx; }
    var byName = {}, byCik = {}, keys = Object.keys(map);
    keys.forEach(function (t) {
      var r = map[t], n = normName(r[0]);
      (byName[n] = byName[n] || []).push(t);
      if (r[1] === "S" && r[2] != null && r[3] === 1) { (byCik[r[2]] = byCik[r[2]] || []).push(t); }
    });
    Object.keys(byCik).forEach(function (c) { byCik[c].sort(); });
    var idx = { byName: byName, byCik: byCik, keys: keys, names: Object.keys(byName) };
    Object.defineProperty(map, "__idx", { value: idx, enumerable: false });
    return idx;
  }

  function rank(tickers, map) {
    // Prefer stocks over ETFs, common classes, then shorter tickers.
    return tickers.slice().sort(function (a, b) {
      var ra = map[a], rb = map[b];
      return (ra[1] === "S" ? 0 : 1) - (rb[1] === "S" ? 0 : 1) ||
        (rb[3] === 1 ? 1 : 0) - (ra[3] === 1 ? 1 : 0) || a.length - b.length || (a < b ? -1 : 1);
    });
  }

  function nameMatches(phrase, map) {
    var idx = makeIndex(map), p = normName(phrase);
    if (!p || p.length < 3) { return []; }
    var exact = idx.byName[p] || [];
    if (exact.length) { return rank(exact, map).map(function (t) { return { ticker: t, name: map[t][0] }; }); }
    var starts = [];
    idx.names.forEach(function (n) {
      if (n.indexOf(p + " ") === 0) { starts = starts.concat(idx.byName[n]); }
    });
    return rank(starts, map).slice(0, 5).map(function (t) { return { ticker: t, name: map[t][0] }; });
  }

  function closeTickers(t, map) {
    var idx = makeIndex(map), out = [];
    if (!/[A-Z]/.test(t)) { return out; }
    idx.keys.forEach(function (k) {
      if (Math.abs(k.length - t.length) > 1) { return; }
      var d = lev(t, k);
      if (d <= 1) { out.push([d, k]); }
    });
    out.sort(function (a, b) { return a[0] - b[0] || (a[1] < b[1] ? -1 : 1); });
    return rank(out.slice(0, 12).map(function (x) { return x[1]; }), map).slice(0, 4)
      .map(function (k) { return { ticker: k, name: map[k][0] }; });
  }

  function parse(text, map) {
    var toks = tokenize(text), groups = [], i = 0;
    // Group consecutive Title-case words into company-name phrases.
    while (i < toks.length) {
      if (isNameWord(toks[i])) {
        var j = i;
        while (j < toks.length && isNameWord(toks[j])) { j++; }
        groups.push({ kind: "phrase", text: toks.slice(i, j).join(" ") });
        i = j;
      } else {
        groups.push({ kind: "tok", text: toks[i] });
        i++;
      }
    }

    var items = [], seen = {}, idx = makeIndex(map);
    function add(item, key) {
      if (seen[key]) { return; }
      seen[key] = true;
      items.push(item);
    }

    groups.forEach(function (g) {
      if (g.kind === "phrase") {
        var cands = nameMatches(g.text, map);
        if (cands.length) {
          add({ input: g.text, status: "name", suggestions: cands.slice(0, 3),
                note: "Looks like a company name." }, "name:" + normName(g.text));
        } else {
          add({ input: g.text, status: "notfound", suggestions: [],
                note: "No US-listed company or ETF matches this name." }, "name:" + normName(g.text));
        }
        return;
      }
      var t = canon(g.text);
      if (!/^[A-Z0-9-]+$/.test(t)) {
        add({ input: g.text, status: "notfound", suggestions: [], note: "Not a ticker format." }, "bad:" + t);
        return;
      }
      var r = map[t];
      if (r && r[1] === "E") { add({ input: g.text, status: "etf", ticker: t, name: r[0] }, t); return; }
      if (r) { add({ input: g.text, status: "stock", ticker: t, name: r[0], cik: r[2] }, t); return; }
      if (/^[0-9-]+$/.test(t)) {
        add({ input: g.text, status: "notfound", suggestions: [], note: "Numbers are not tickers." }, t);
        return;
      }
      var byName = t.length >= 4 ? nameMatches(t, map) : [];
      if (byName.length) {
        add({ input: g.text, status: "name", suggestions: byName.slice(0, 3), note: "Looks like a company name." }, "name:" + t);
        return;
      }
      add({ input: g.text, status: "notfound", suggestions: closeTickers(t, map),
            note: "Not found: a typo, a delisted company, or not listed on a US exchange." }, t);
    });

    // Share classes: collapse recognized stocks from the same company; prompt to add all classes.
    var byCikSeen = {}, out = [];
    items.forEach(function (it) {
      if (it.status !== "stock" || it.cik == null) { out.push(it); return; }
      var sibs = idx.byCik[it.cik] || [];
      if (sibs.length < 2 || map[it.ticker][3] !== 1) { delete it.cik; out.push(it); return; }
      if (/[-.\/]/.test(it.input)) {
        // The user typed an explicit class (BRK.B): take it as given, just mention the others.
        it.note = "Other share class" + (sibs.length > 2 ? "es" : "") + ": " +
          sibs.filter(function (s) { return s !== it.ticker; }).join(", ") + ".";
        delete it.cik; out.push(it); return;
      }
      var grp = byCikSeen[it.cik];
      if (!grp) {
        grp = { input: it.input, status: "ambiguous", kind: "classes", name: it.name,
                classes: sibs.slice(), tickers: [it.ticker],
                note: it.name + " has " + sibs.length + " share classes (" + sibs.join(", ") + "). Add all share classes?" };
        byCikSeen[it.cik] = grp;
        out.push(grp);
      } else {
        grp.input += " " + it.input;
        if (grp.tickers.indexOf(it.ticker) < 0) { grp.tickers.push(it.ticker); }
      }
    });
    out.forEach(function (it) { delete it.cik; });
    var attention = out.filter(function (it) {
      return it.status === "name" || it.status === "ambiguous" || it.status === "notfound";
    }).length;
    return { items: out, attention: attention };
  }

  /* Resolve an item to the tickers that would be saved. choice: ticker, "all", or undefined. */
  function resolve(item, choice) {
    if (item.status === "stock" || item.status === "etf") { return [item.ticker]; }
    if (item.status === "ambiguous") { return choice === "all" ? item.classes.slice() : (choice ? [choice] : item.tickers.slice()); }
    if (item.status === "name") { return choice ? [choice] : []; }
    return [];
  }

  var api = { parse: parse, resolve: resolve, canon: canon, normName: normName, tokenize: tokenize };
  root.LauraParser = api;
  if (typeof module !== "undefined" && module.exports) { module.exports = api; }
})(typeof window !== "undefined" ? window : globalThis);
