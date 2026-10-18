/* Tripwire ETF look-through math. Runs in the page and in Node (tests).
 *
 * Whole-portfolio Black exposure (percent of total portfolio) =
 *   sum over held ETFs of (ETF weight % x Black share inside that ETF %) / 100
 *   + weight % of any Black-list stock held directly.
 * Flag when the total exceeds the threshold (default 2%) or any Black stock is held directly.
 *
 * compute({rows, etfData, black, thresholdPct, perAmount})
 *   rows:    [{ticker, weightPct}]  team inputs; weightPct may be null/"" (not entered)
 *   etfData: {ETF: {holdings: {TICKER: pctOfEtf}, asOf, source}}
 *   black:   array of Black-list tickers to count
 */
(function (root) {
  "use strict";

  function num(x) {
    if (x === null || x === undefined || x === "") { return null; }
    var n = typeof x === "number" ? x : parseFloat(String(x).replace(/[%,\s]/g, ""));
    return isFinite(n) ? n : null;
  }

  function etfBlackShare(etf, black) {
    // percent of the ETF held in Black-list stocks
    var h = (etf && etf.holdings) || {}, s = 0, names = [];
    black.forEach(function (t) {
      var v = num(h[t]);
      if (v) { s += v; names.push(t); }
    });
    return { pct: s, names: names };
  }

  function compute(opts) {
    var rows = opts.rows || [], etfData = opts.etfData || {}, black = opts.black || [];
    var threshold = opts.thresholdPct == null ? 2 : opts.thresholdPct;
    var perAmount = opts.perAmount || 10000;
    var blackSet = {};
    black.forEach(function (t) { blackSet[t] = true; });

    var perEtf = [], direct = [], missingData = [], total = 0, anyWeight = false, missingWeight = [];
    rows.forEach(function (r) {
      var t = String(r.ticker || "").toUpperCase(), w = num(r.weightPct);
      if (!t) { return; }
      if (w !== null && w > 0) { anyWeight = true; }
      if (blackSet[t]) {
        direct.push({ ticker: t, weightPct: w });
        if (w) { total += w; }
        return;
      }
      var d = etfData[t];
      if (!d) { missingData.push(t); return; }
      var bs = etfBlackShare(d, black);
      var row = { ticker: t, weightPct: w, blackSharePct: bs.pct, blackNames: bs.names, asOf: d.asOf,
                  perAmountUsd: perAmount * bs.pct / 100, contributionPct: null };
      if (w !== null) { row.contributionPct = w * bs.pct / 100; total += row.contributionPct; }
      else { missingWeight.push(t); }
      perEtf.push(row);
    });

    var mode = anyWeight ? "portfolio" : "per_amount";
    var directHeld = direct.filter(function (d) { return d.weightPct === null || d.weightPct > 0; });
    return {
      mode: mode,
      totalPct: mode === "portfolio" ? total : null,
      thresholdPct: threshold,
      overThreshold: mode === "portfolio" ? total > threshold : false,
      flagged: (mode === "portfolio" && total > threshold) || directHeld.length > 0,
      perEtf: perEtf,
      direct: directHeld,
      missingData: missingData,
      missingWeight: anyWeight ? missingWeight : [],
      perAmountUsd: perAmount
    };
  }

  function round(x, dp) {
    var f = Math.pow(10, dp);
    return Math.round(x * f) / f;
  }

  var api = { compute: compute, etfBlackShare: etfBlackShare, round: round };
  root.LauraLookthrough = api;
  if (typeof module !== "undefined" && module.exports) { module.exports = api; }
})(typeof window !== "undefined" ? window : globalThis);
