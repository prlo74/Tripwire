/* Laura Screen paste-box parser. Runs in the page and in Node (tests).
 *
 * parse(text, map) -> { items: [...], attention: n }
 *   map: { TICKER: [name, "S"|"E", cik|null, commonClass 1|0|null] }  (site/tickers.json .t)
 * Each item: { input, status, ticker?, name?, suggestions?: [{ticker,name}], note?, aliases? }
 *   status: "stock" | "etf" | "name" | "ambiguous" | "notfound"
 *   "ambiguous" has kind "classes" (share classes) or "word" (an ordinary word that is also a ticker).
 */
(function (root) {
  "use strict";

  var SUFFIXES = /\b(incorporated|inc|corporation|corp|company|co|ltd|limited|plc|llc|holdings?|group|sa|nv|ag|the|class [a-c]|new|del|de|cl [a-c])\b/g;
  var CORP_WORD = /^(inc|corp|co|ltd|plc|llc|corporation|company|incorporated|holdings?|group)$/i;
  // Everyday words that also happen to be tickers; flagged instead of silently accepted.
  var STOPWORDS = ["a", "i", "an", "the", "and", "or", "for", "of", "in", "on", "at", "to", "is", "it", "my",
    "me", "we", "us", "our", "you", "own", "all", "new", "big", "key", "now", "low", "high", "cash", "plus",
    "one", "two", "see", "buy", "sell", "hold", "add", "also", "so", "be", "go", "do", "am", "are", "has",
    "have", "had", "was", "not", "no", "yes", "but", "with", "from", "by", "as", "up", "out", "any", "more",
    "most", "some", "etf", "etfs", "stock", "stocks", "fund", "funds", "want", "like", "this", "that", "these",
    "those", "maybe", "please", "list", "and/or", "vs", "via", "per", "each", "into", "over", "under", "about"];
  var STOP = {};
  STOPWORDS.forEach(function (w) { STOP[w] = true; });

  function canon(t) {
    return String(t).trim().toUpperCase().replace(/\.+$/, "").replace(/[./]/g, "-");
  }

  function normName(s) {
    return s.toLowerCase()
      .replace(/\/[a-z]{2,4}\/?$/i, " ")        // SEC state suffixes like /CAN/, /DE/
      .replace(/&/g, " and ")
      .replace(/[^a-z0-9 ]+/g, " ")
      .replace(SUFFIXES, " ")
      .replace(/\s+/g, " ").trim();
  }

  // Title-case word with a lowercase letter after the first ("Apple", "Inc.", "Newsmax"),
  // or a corporate suffix / connector inside a name.
  function isNameWord(tok) {
    return /^[A-Z][a-z][A-Za-z'&.\-]*$/.test(tok) || /^(Inc|Co|Corp|Ltd|Plc|LLC)\.?$/.test(tok) || tok === "&";
  }

  function preprocess(text) {
    var s = String(text || "");
    if (s.normalize) { s = s.normalize("NFKC"); }                     // full-width -> ASCII
    s = s.replace(/[​-‍⁠﻿]/g, " ")                // zero-width characters
      .replace(/[‒-―−]/g, " ")                        // figure/en/em dashes, minus
      .replace(/\b(?:NASDAQ|NYSE|NYSEARCA|NYSEAMERICAN|NYSEMKT|AMEX|ARCA|BATS|CBOE|OTC|OTCMKTS)\s*:\s*/gi, "")
      .replace(/\b([A-Za-z][A-Za-z.\-\/]{0,6})\s*:\s*US\b/g, "$1")      // AAPL:US
      .replace(/\b([A-Za-z][A-Za-z.\-\/]{0,6})\s+US\s+Equity\b/g, "$1"); // AAPL US Equity (Bloomberg)
    return s;
  }

  // Segments are split on hard separators; words inside a segment may form a company name.
  function segments(text) {
    return preprocess(text).split(/[,;\n\r\t$|•·]+/).map(function (seg) {
      return seg.split(/\s+/).map(function (t) {
        return t.replace(/^[^A-Za-z0-9&]+|[^A-Za-z0-9.&]+$/g, "");
      }).filter(Boolean);
    }).filter(function (s) { return s.length; });
  }

  function tokenize(text) {
    return [].concat.apply([], segments(text));
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

  function sugg(ts, map) { return ts.map(function (t) { return { ticker: t, name: map[t][0] }; }); }

  function exactName(phrase, map) {
    var p = normName(phrase);
    if (!p || p.length < 3) { return []; }
    return rank(makeIndex(map).byName[p] || [], map);
  }

  function prefixName(phrase, map) {
    var idx = makeIndex(map), p = normName(phrase), out = [];
    if (!p || p.length < 3) { return []; }
    idx.names.forEach(function (n) { if (n.indexOf(p + " ") === 0) { out = out.concat(idx.byName[n]); } });
    return rank(out, map).slice(0, 5);
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
    return sugg(rank(out.slice(0, 12).map(function (x) { return x[1]; }), map).slice(0, 4), map);
  }

  function tickerItem(input, t, map) {
    var r = map[t];
    if (!r) { return null; }
    return r[1] === "E" ? { input: input, status: "etf", ticker: t, name: r[0] }
      : { input: input, status: "stock", ticker: t, name: r[0], cik: r[2] };
  }

  function wordItem(input, t, map) {
    return { input: input, status: "ambiguous", kind: "word", tickers: [t], classes: [t],
             suggestions: sugg([t], map),
             note: "“" + input + "” is an ordinary word or single letter. Did you mean the ticker " + t + " (" + map[t][0] + ")?" };
  }

  function nameItem(input, cands, map, extraTicker) {
    var s = cands.slice(0, 3);
    if (extraTicker && s.indexOf(extraTicker) < 0) { s.push(extraTicker); }
    return { input: input, status: "name", suggestions: sugg(s, map), note: "Looks like a company name." };
  }

  // Parse one segment of whitespace-separated words into raw items.
  function parseSegment(words, map, out) {
    var i = 0, multi = words.length > 1;
    while (i < words.length) {
      var w = words[i];
      // "BRK B" -> BRK-B
      if (i + 1 < words.length && /^[A-Za-z]{1,5}$/.test(w) && /^[A-Za-z]$/.test(words[i + 1]) &&
          map[canon(w) + "-" + words[i + 1].toUpperCase()] && !map[canon(w)]) {
        out.push(tickerItem(w + " " + words[i + 1], canon(w) + "-" + words[i + 1].toUpperCase(), map));
        i += 2; continue;
      }
      // Company-name phrase: Title-case words (+ "Class X", "&", corporate suffixes).
      if (isNameWord(w)) {
        var j = i, parts = [];
        while (j < words.length) {
          if (isNameWord(words[j])) { parts.push(words[j]); j++; }
          else if (/^Class$/i.test(words[j - 1] || "") && /^[A-Ca-c]$/.test(words[j])) { parts.push(words[j]); j++; }
          else if (/^class$/i.test(words[j]) && j + 1 < words.length && /^[A-Ca-c]$/.test(words[j + 1])) { parts.push(words[j]); j++; }
          else { break; }
        }
        var phrase = parts.join(" ");
        var exact = exactName(phrase, map);
        if (exact.length) {
          var tk = parts.length === 1 && map[canon(w)] && exact.indexOf(canon(w)) < 0 ? canon(w) : null;
          out.push(nameItem(phrase, exact, map, tk));
        } else if (parts.every(function (p) { return map[canon(p)] && !CORP_WORD.test(p); })) {
          // "Aapl Msft", "Tsla": tickers typed in Title case.
          parts.forEach(function (p) {
            var t = canon(p);
            out.push(STOP[p.toLowerCase()] && multi ? wordItem(p, t, map) : tickerItem(p, t, map));
          });
        } else {
          var pre = prefixName(phrase, map);
          if (pre.length) { out.push(nameItem(phrase, pre, map)); }
          else { out.push({ input: phrase, status: "notfound", suggestions: [], note: "No US-listed company or ETF matches this name." }); }
        }
        i = j; continue;
      }
      var t = canon(w);
      if (!/^[A-Z0-9-]+$/.test(t)) {
        out.push({ input: w, status: "notfound", suggestions: [], note: "Not a ticker format." });
        i++; continue;
      }
      if (map[t]) {
        var isWord = multi && (STOP[w.toLowerCase()] && w !== w.toUpperCase() || (t.length === 1));
        out.push(isWord ? wordItem(w, t, map) : tickerItem(w, t, map));
        i++; continue;
      }
      if (/^[0-9-]+$/.test(t)) {
        out.push({ input: w, status: "notfound", suggestions: [], note: "Numbers are not tickers." });
        i++; continue;
      }
      // Unknown word: try it together with the following unknown words as a company name ("APPLE INC").
      var k = i, run = [];
      while (k < words.length && /^[A-Za-z&.'-]+$/.test(words[k]) && (!map[canon(words[k])] || CORP_WORD.test(words[k]))) {
        run.push(words[k]); k++;
      }
      var matched = false;
      for (var len = run.length; len >= 1 && !matched; len--) {
        var ph = run.slice(0, len).join(" ");
        if (len === 1 && t.length < 4) { break; }
        var ex = exactName(ph, map), pr = ex.length ? ex : (len === 1 && t.length >= 4 ? prefixName(ph, map) : []);
        if (pr.length) { out.push(nameItem(ph, pr, map)); i += len; matched = true; }
      }
      if (matched) { continue; }
      if (CORP_WORD.test(w)) { i++; continue; }   // stray "INC" after a name
      out.push({ input: w, status: "notfound", suggestions: closeTickers(t, map),
                 note: "Not found: a typo, a delisted company, or not listed on a US exchange." });
      i++;
    }
  }

  function parse(text, map) {
    var raw = [], idx = makeIndex(map);
    segments(text).forEach(function (words) { parseSegment(words, map, raw); });

    // De-duplicate, keeping first appearance.
    var items = [], seen = {};
    raw.forEach(function (it) {
      if (!it) { return; }
      var key = it.ticker ? it.ticker : it.status + ":" + normName(it.input) + ":" + it.input.toUpperCase();
      if (seen[key]) { return; }
      seen[key] = true;
      items.push(it);
    });

    // A company name whose best match is also pasted as a ticker becomes an alias of that ticker.
    var byTicker = {};
    items.forEach(function (it) { if (it.ticker && (it.status === "stock" || it.status === "etf")) { byTicker[it.ticker] = it; } });
    items = items.filter(function (it) {
      if (it.status !== "name" || !it.suggestions.length) { return true; }
      var host = byTicker[it.suggestions[0].ticker];
      if (!host) { return true; }
      (host.aliases = host.aliases || []).push(it.input);
      host.note = "Also pasted as “" + host.aliases.join("”, “") + "”.";
      return false;
    });

    // Share classes: collapse recognized stocks from the same company; prompt to add all classes.
    var byCikSeen = {}, out = [];
    items.forEach(function (it) {
      if (it.status !== "stock" || it.cik == null) { delete it.cik; out.push(it); return; }
      var sibs = idx.byCik[it.cik] || [];
      if (sibs.length < 2 || map[it.ticker][3] !== 1) { delete it.cik; out.push(it); return; }
      if (/[-.\/ ]/.test(it.input)) {
        // The user typed an explicit class (BRK.B, BRK B): take it as given, just mention the others.
        it.note = (it.note ? it.note + " " : "") + "Other share class" + (sibs.length > 2 ? "es" : "") + ": " +
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
    if (item.status === "ambiguous" && item.kind === "word") { return choice ? [choice] : []; }
    if (item.status === "ambiguous") { return choice === "all" ? item.classes.slice() : (choice ? [choice] : item.tickers.slice()); }
    if (item.status === "name") { return choice ? [choice] : []; }
    return [];
  }

  var api = { parse: parse, resolve: resolve, canon: canon, normName: normName, tokenize: tokenize };
  root.LauraParser = api;
  if (typeof module !== "undefined" && module.exports) { module.exports = api; }
})(typeof window !== "undefined" ? window : globalThis);
