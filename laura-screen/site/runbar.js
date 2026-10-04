/* Laura Screen: run progress indicator ("runbar"). Inlined into site/index.html by
 * pipeline/build_page.py and tested with node (tests/runbar.test.js).
 * The phase ids must equal the stage ids in pipeline/progress.py.
 */
// ---------- run progress ("runbar") ----------
// Pure model + DOM renderer. No dependencies. ES5 to match the rest of site/index.html.
// Runbar.compute() turns timestamps + the runs/progress doc into a view model.
// Runbar.render() paints it. Nothing here reads the database or the clock by itself.
var Runbar = (function () {
  // Default steps. `w` is each step's share of a typical run's wall-clock time.
  // The defaults are placeholders: the page replaces them with the last run's measured
  // phase_ms as soon as one run has recorded them (see weightsFrom).
  var PHASES = [
    { id: "starting",   label: "Starting the run",          short: "Start",      w: 0.30 },
    { id: "universe",   label: "Ticker lists and S&P 500",  short: "Tickers",    w: 0.08 },
    { id: "records",    label: "Court and agency records",  short: "Records",    w: 0.24, unit: "sources opened" },
    { id: "financials", label: "Financial gates and new tickers", short: "Financials", w: 0.10, unit: "companies" },
    { id: "etf",        label: "ETF holdings",              short: "ETFs",       w: 0.09, unit: "funds" },
    { id: "discovery",  label: "Discovery and evidence review", short: "Discovery", w: 0.11, unit: "sources" },
    { id: "publish",    label: "Writing results",           short: "Publish",    w: 0.08 }
  ];
  var DEFAULT_TOTAL_MS = 3 * 60 * 1000;   // used only until a run has recorded its timing
  var MIN_SHARE = 0.03;                   // no step is ever weighted below 3%
  var RUN_TIMEOUT_MS = 45 * 60 * 1000;    // same limit as checkRunning()
  var SCHEDULED_FRESH_MS = 10 * 60 * 1000;
  var DONE_LINGER_MS = 2 * 60 * 1000;     // finished state stays up this long
  var STALL_MIN_MS = 90 * 1000;

  function ms(v) { var t = v ? Date.parse(v) : NaN; return isNaN(t) ? 0 : t; }
  function clamp(x, lo, hi) { return x < lo ? lo : x > hi ? hi : x; }
  function dur(t) {
    var s = Math.max(0, Math.floor(t / 1000)), h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), sec = s % 60;
    function p(n) { return n < 10 ? "0" + n : String(n); }
    return (h ? h + ":" + p(m) : p(m)) + ":" + p(sec);
  }

  // Shares and expected durations per step, from the last run's timing when it is complete.
  function weightsFrom(timing) {
    var pm = timing && timing.phase_ms, ok = !!pm, sum = 0, i;
    for (i = 0; ok && i < PHASES.length; i++) { var v = pm[PHASES[i].id]; if (!(v > 0)) ok = false; else sum += v; }
    var total = ok ? sum : (timing && timing.total_ms > 0 ? timing.total_ms : DEFAULT_TOTAL_MS);
    var shares = PHASES.map(function (p) { return Math.max(MIN_SHARE, ok ? pm[p.id] / sum : p.w); });
    var norm = shares.reduce(function (a, b) { return a + b; }, 0);
    shares = shares.map(function (s) { return s / norm; });
    return { shares: shares, expected: shares.map(function (s) { return s * total; }), total: total, measured: ok };
  }

  // input: { now, weekly, prog, timing, prev }
  //   weekly = settings/weekly doc (check_requested_at, check_completed_at)
  //   prog   = runs/progress doc (see the data contract in the request)
  //   timing = runs/latest .run.timing ({ total_ms, phase_ms }) from the last finished run
  //   prev   = the model this function returned last time (keeps the percent from going backwards)
  function compute(input) {
    var now = input.now, w = input.weekly || {}, prog = input.prog || null, prev = input.prev || null;
    var req = ms(w.check_requested_at), done = ms(w.check_completed_at);
    var progStart = prog ? ms(prog.started_at) : 0, progUpd = prog ? ms(prog.updated_at) : 0;
    // The run marks progress "done" a moment before it records check_completed_at; in between,
    // this run is finished, not back at step 1.
    var progDoneMine = !!prog && prog.state === "done" && req > 0 && progStart >= req - 60000;
    var onDemand = req > 0 && done < req && now - req < RUN_TIMEOUT_MS && !progDoneMine;
    var progLive = !!prog && prog.state === "running" && progUpd > 0;
    var progMine = progLive && onDemand && progStart >= req - 60000;
    var scheduled = !onDemand && progLive && progStart > Math.max(done, req) && now - progUpd < SCHEDULED_FRESH_MS;
    var W = weightsFrom(input.timing);

    if (!onDemand && !scheduled) {
      var finishedAt = Math.max(done, prog && prog.state === "done" ? ms(prog.updated_at) : 0);
      if (finishedAt && now - finishedAt >= 0 && now - finishedAt < DONE_LINGER_MS) {
        var tookFrom = req && (done >= req || progDoneMine) ? req : (prog && prog.state === "done" ? progStart : 0);
        return { state: "done", runKey: String(finishedAt), pct: 100, finishedAt: finishedAt,
          tookMs: tookFrom ? finishedAt - tookFrom : 0, segs: segs(W, PHASES.length, 1) };
      }
      return { state: "idle" };
    }

    var start = onDemand ? req : progStart, has = onDemand ? progMine : true;
    var idx = 0, phaseStart = start, counted = false, frac;
    if (has) {
      idx = -1;
      for (var i = 0; i < PHASES.length; i++) if (PHASES[i].id === prog.phase) idx = i;
      if (idx < 0) idx = clamp((prog.phase_index || 2) - 1, 1, PHASES.length - 1);
      phaseStart = ms(prog.phase_started_at) || progUpd;
    }
    if (has && prog.total > 0 && prog.done != null) { counted = true; frac = clamp(prog.done / prog.total, 0, 1); }
    else {
      // No count for this step: estimate from time. Approaches 92% of the step and never completes it.
      var t = Math.max(0, now - phaseStart) / Math.max(1, W.expected[idx]);
      frac = 0.92 * (1 - Math.exp(-2.2 * t));
    }
    var before = 0; for (var j = 0; j < idx; j++) before += W.shares[j];
    var runKey = String(start), raw = (before + W.shares[idx] * frac) * 100;
    var floorPct = prev && prev.state === "running" && prev.runKey === runKey ? prev.pct : 0;
    var pct = clamp(Math.max(floorPct, Math.floor(raw)), 0, 99);

    var lastSignal = has ? progUpd : start;
    var stalled = now - lastSignal > Math.max(STALL_MIN_MS, 3 * W.expected[idx]);
    var p = PHASES[idx];
    var detail = !has ? "Waiting for the run to report in"
      : counted ? prog.done + " of " + prog.total + " " + (prog.unit || p.unit || "done")
      : "In progress";
    return {
      state: "running", runKey: runKey, pct: pct, stalled: stalled, estimated: !counted,
      step: idx + 1, steps: PHASES.length, phaseId: p.id, label: (has && prog.label) || p.label, detail: detail,
      elapsedMs: Math.max(0, now - start), sinceSignalMs: Math.max(0, now - lastSignal),
      usualMs: W.measured ? W.total : 0, segs: segs(W, idx, frac)
    };
  }

  function segs(W, idx, frac) {
    var grow = W.shares.map(function (s) { return Math.max(s, 0.07); });
    return PHASES.map(function (p, i) {
      return { id: p.id, short: p.short, label: p.label, grow: Math.round(grow[i] * 1000),
        fill: i < idx ? 100 : i === idx ? Math.round(frac * 100) : 0,
        status: i < idx ? "done" : i === idx ? "now" : "next" };
    });
  }

  function valueText(m) {
    if (m.state === "done") return "Check finished" + (m.tookMs ? ", took " + dur(m.tookMs) : "") + ".";
    return (m.estimated ? "About " : "") + m.pct + " percent. Step " + m.step + " of " + m.steps + ": " + m.label + ". " + m.detail + "." +
      (m.stalled ? " Slower than usual." : "");
  }

  // ---- DOM ----
  var SVGNS = "http://www.w3.org/2000/svg";
  function h(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }

  function build(root) {
    root.textContent = "";
    var head = h("div", "rb-head");
    var ring = h("div", "rb-ring"); ring.setAttribute("aria-hidden", "true");
    var svg = document.createElementNS(SVGNS, "svg"); svg.setAttribute("viewBox", "0 0 100 100");
    ["rb-ring-track", "rb-ring-fill"].forEach(function (c) {
      var ci = document.createElementNS(SVGNS, "circle");
      ci.setAttribute("class", c); ci.setAttribute("cx", "50"); ci.setAttribute("cy", "50"); ci.setAttribute("r", "44");
      ci.setAttribute("pathLength", "100"); svg.appendChild(ci);
    });
    ring.appendChild(svg);
    var pct = h("div", "rb-pct"); pct.setAttribute("aria-hidden", "true");
    pct.appendChild(h("span", "rb-num", "0")); pct.appendChild(h("span", "rb-sign", "%"));
    var text = h("div", "rb-text");
    text.appendChild(h("div", "rb-eyebrow")); text.appendChild(h("div", "rb-title")); text.appendChild(h("div", "rb-detail"));
    var time = h("div", "rb-time");
    time.appendChild(h("span", "rb-elapsed")); time.appendChild(h("span", "rb-usual"));
    head.appendChild(ring); head.appendChild(pct); head.appendChild(text); head.appendChild(time);
    var segsEl = h("div", "rb-segs"); segsEl.setAttribute("aria-hidden", "true");
    var rows = h("ol", "rb-rows"); rows.setAttribute("aria-hidden", "true");
    var prog = h("progress", "sr"); prog.max = 100; prog.setAttribute("aria-label", "Check progress");
    var live = h("p", "sr"); live.setAttribute("role", "status");
    root.appendChild(head); root.appendChild(segsEl); root.appendChild(rows); root.appendChild(prog); root.appendChild(live);
    root._rb = { ring: svg.lastChild, pct: pct, num: pct.firstChild, eyebrow: text.children[0], title: text.children[1], detail: text.children[2],
      elapsed: time.children[0], usual: time.children[1], segs: segsEl, rows: rows, prog: prog, live: live, said: "" };
  }

  // opts: { fmtWhen(ms) -> "Oct 4, 9:06 PM" }
  function render(root, m, opts) {
    if (!root) return;
    if (!m || m.state === "idle") { root.hidden = true; root.removeAttribute("data-state"); return; }
    if (!root._rb) build(root);
    var r = root._rb, st = m.state === "done" ? "done" : m.stalled ? "stalled" : m.step === 1 && m.estimated ? "starting" : "running";
    root.hidden = false; root.setAttribute("data-state", st);
    r.num.textContent = String(m.pct);
    r.ring.style.strokeDashoffset = String(100 - m.pct);
    if (m.state === "done") {
      r.eyebrow.textContent = "Check finished";
      r.title.textContent = "Finished " + (opts && opts.fmtWhen ? opts.fmtWhen(m.finishedAt) : "") + (m.tookMs ? " · took " + dur(m.tookMs) : "");
      r.detail.textContent = ""; r.elapsed.textContent = ""; r.usual.textContent = "";
    } else {
      r.eyebrow.textContent = (m.stalled ? "Slower than usual" : st === "starting" ? "Starting" : "Check running") + " · step " + m.step + " of " + m.steps;
      r.title.textContent = m.label;
      r.detail.textContent = m.stalled ? "No update for " + dur(m.sinceSignalMs) + ". The bar holds until the run reports again." : m.detail;
      r.elapsed.textContent = dur(m.elapsedMs);
      r.usual.textContent = "elapsed" + (m.usualMs ? " · usually about " + dur(m.usualMs) : "");
    }
    if (r.segs.children.length !== m.segs.length) {
      r.segs.textContent = ""; r.rows.textContent = "";
      m.segs.forEach(function (s) {
        var seg = h("div", "rb-seg"), track = h("div", "rb-track"); track.appendChild(h("div", "rb-fill"));
        seg.appendChild(track); seg.appendChild(h("div", "rb-lab", s.short)); r.segs.appendChild(seg);
        var li = h("li", "rb-row"); li.appendChild(h("span", "rb-mark")); li.appendChild(h("span", "rb-row-name", s.label)); li.appendChild(h("span", "rb-row-detail"));
        r.rows.appendChild(li);
      });
    }
    m.segs.forEach(function (s, i) {
      var seg = r.segs.children[i], li = r.rows.children[i];
      seg.style.flexGrow = String(s.grow); seg.setAttribute("data-status", s.status);
      seg.firstChild.firstChild.style.width = s.fill + "%";
      li.setAttribute("data-status", s.status);
      li.lastChild.textContent = s.status === "done" ? "Done" : s.status === "now" ? m.detail : "Waiting";
    });
    r.prog.value = m.pct; r.prog.setAttribute("aria-valuetext", valueText(m));
    // Screen readers hear a change of step or state, not every percent.
    var say = m.state === "done" ? valueText(m) : "Step " + m.step + " of " + m.steps + ": " + m.label + (m.stalled ? ". Slower than usual." : ".");
    if (say !== r.said) { r.said = say; r.live.textContent = say; }
  }

  return { PHASES: PHASES, compute: compute, render: render, dur: dur };
})();
if (typeof module !== "undefined" && module.exports) module.exports = Runbar;
