// Run with: node tests/runbar.test.js  (also run by tests/test_runbar.py under pytest)
var R = require('../site/runbar.js'), assert = require('assert');
var T0 = Date.parse('2026-10-04T12:03:30Z'), iso = function (t) { return new Date(t).toISOString(); };
var weekly = { check_requested_at: iso(T0), check_completed_at: iso(T0 - 86400000) };
var n = 0; function ok(name, c) { assert.ok(c, name); n++; console.log('ok  ' + name); }

// 1 idle when nothing requested
ok('idle with no request', R.compute({ now: T0, weekly: {}, prog: null }).state === 'idle');
// 2 starting: no progress doc
var m = R.compute({ now: T0 + 5000, weekly: weekly, prog: null });
ok('starting step 1, estimated', m.state === 'running' && m.step === 1 && m.estimated && m.pct >= 0 && m.pct < 30);
// 3 starting never leaves step 1 share on its own
m = R.compute({ now: T0 + 20 * 60000, weekly: weekly, prog: null });
ok('starting caps below its share, stalls', m.pct < 30 && m.stalled);
// 4 stale progress doc from an older run is ignored
var old = { state: 'running', phase: 'publish', started_at: iso(T0 - 3600000), updated_at: iso(T0 - 3500000) };
m = R.compute({ now: T0 + 5000, weekly: weekly, prog: old });
ok('older run progress ignored', m.step === 1);
// 5 counted phase
var prog = { state: 'running', phase: 'records', phase_index: 3, done: 14, total: 28, unit: 'sources opened',
  started_at: iso(T0 + 60000), phase_started_at: iso(T0 + 70000), updated_at: iso(T0 + 90000) };
m = R.compute({ now: T0 + 91000, weekly: weekly, prog: prog });
ok('records 14/28 = 30+8+12 = 50%', m.pct === 50 && m.step === 3 && !m.estimated && m.detail === '14 of 28 sources opened');
// 6 monotonic
var prev = m; var back = JSON.parse(JSON.stringify(prog)); back.done = 3;
m = R.compute({ now: T0 + 92000, weekly: weekly, prog: back, prev: prev });
ok('never goes backwards', m.pct === 50);
// 7 cap 99
var end = { state: 'running', phase: 'publish', done: 5, total: 5, started_at: iso(T0 + 60000), phase_started_at: iso(T0 + 140000), updated_at: iso(T0 + 150000) };
m = R.compute({ now: T0 + 151000, weekly: weekly, prog: end });
ok('caps at 99 until completion is recorded', m.pct === 99);
// 8 done lingers then idle
var wk2 = { check_requested_at: iso(T0), check_completed_at: iso(T0 + 154000) };
m = R.compute({ now: T0 + 160000, weekly: wk2, prog: end });
ok('done state with took', m.state === 'done' && m.pct === 100 && m.tookMs === 154000);
ok('idle after linger', R.compute({ now: T0 + 154000 + 121000, weekly: wk2, prog: end }).state === 'idle');
// 9 measured weights
var timing = { total_ms: 200000, phase_ms: { starting: 100000, universe: 10000, records: 50000, financials: 10000, etf: 10000, discovery: 10000, publish: 10000 } };
m = R.compute({ now: T0 + 91000, weekly: weekly, prog: prog, timing: timing });
ok('measured weights: 50+5+12.5 = 67%', m.pct === 67 && m.usualMs === 200000);
// 10 incomplete timing falls back to defaults
m = R.compute({ now: T0 + 91000, weekly: weekly, prog: prog, timing: { phase_ms: { starting: 1 } } });
ok('partial timing falls back', m.pct === 50 && m.usualMs === 0);
// 11 time-estimated phase approaches but never completes
var fin = { state: 'running', phase: 'financials', started_at: iso(T0 + 60000), phase_started_at: iso(T0 + 100000), updated_at: iso(T0 + 100000) };
var a = R.compute({ now: T0 + 101000, weekly: weekly, prog: fin }), b = R.compute({ now: T0 + 100000 + 3600000 / 2, weekly: weekly, prog: fin });
ok('estimated phase moves', a.pct >= 62 && a.pct < 72 && a.estimated);
ok('estimated phase never reaches next step, and stalls', b.pct < 72 && b.stalled);
// 12 scheduled run (no request) shows from progress doc
m = R.compute({ now: T0 + 30000, weekly: { check_requested_at: iso(T0 - 86400000), check_completed_at: iso(T0 - 86300000) },
  prog: { state: 'running', phase: 'universe', started_at: iso(T0), phase_started_at: iso(T0), updated_at: iso(T0 + 20000) } });
ok('scheduled run is shown', m.state === 'running' && m.step === 2);
// 13 scheduled, stale -> idle
m = R.compute({ now: T0 + 30 * 60000, weekly: { check_requested_at: iso(T0 - 86400000), check_completed_at: iso(T0 - 86300000) },
  prog: { state: 'running', phase: 'universe', started_at: iso(T0), updated_at: iso(T0 + 20000) } });
ok('abandoned scheduled progress hides', m.state === 'idle');
// 14 unknown phase id falls back to phase_index
m = R.compute({ now: T0 + 91000, weekly: weekly, prog: Object.assign({}, prog, { phase: 'mystery', phase_index: 4, done: null, total: null }) });
ok('unknown phase uses phase_index', m.step === 4);
// 15 45-minute timeout
ok('timeout hides', R.compute({ now: T0 + 46 * 60000, weekly: weekly, prog: null }).state === 'idle');
// 16 segs sum
ok('7 segments, statuses consistent', a.segs.length === 7 && a.segs.filter(function (s) { return s.status === 'now'; }).length === 1);
// 17 gap between progress "done" and check_completed_at: finished, never back to step 1
var doneDoc = Object.assign({}, end, { state: 'done', updated_at: iso(T0 + 152000) });
m = R.compute({ now: T0 + 153000, weekly: weekly, prog: doneDoc, prev: R.compute({ now: T0 + 151000, weekly: weekly, prog: end }) });
ok('progress done before check_completed_at shows finished', m.state === 'done' && m.pct === 100 && m.tookMs === 152000);
// 18 a "done" doc from an older run does not end the current request
var oldDone = Object.assign({}, old, { state: 'done' });
m = R.compute({ now: T0 + 5000, weekly: weekly, prog: oldDone });
ok('older run done doc ignored', m.state === 'running' && m.step === 1);
console.log(n + ' passed');
