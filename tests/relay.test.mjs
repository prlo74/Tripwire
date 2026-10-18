// Relay worker against a fake GitHub API. Run: node tests/relay.test.mjs
import assert from "node:assert/strict";
import worker, { canonTickers, visitorTag, LIMITS, replyText, clearCache } from "../relay/worker.js";

const env = { REPO: "o/r", GITHUB_TOKEN: "test-token", ALLOWED_ORIGINS: "https://prlo74.github.io" };
let issues, files, calls;
function reset() { clearCache(); issues = []; files = { "site/requests.json": { requests: [] } }; calls = []; }

globalThis.fetch = async (url, init = {}) => {
  const u = new URL(url), method = init.method || "GET";
  calls.push(`${method} ${u.pathname}`);
  const ok = (v) => new Response(typeof v === "string" ? v : JSON.stringify(v), { status: 200 });
  if (u.pathname.startsWith("/repos/o/r/contents/")) {
    const f = files[u.pathname.replace("/repos/o/r/contents/", "")];
    return f ? ok(JSON.stringify(f)) : new Response("", { status: 404 });
  }
  if (u.pathname === "/repos/o/r/issues" && method === "GET") {
    const state = u.searchParams.get("state");
    return ok(issues.filter((i) => state === "all" || i.state === "open"));
  }
  if (u.pathname === "/repos/o/r/issues" && method === "POST") {
    const b = JSON.parse(init.body), n = issues.length + 1;
    const i = { number: n, title: b.title, body: b.body, state: "open", created_at: new Date().toISOString(), html_url: `https://github.com/o/r/issues/${n}` };
    issues.push(i); return new Response(JSON.stringify(i), { status: 201 });
  }
  const m = u.pathname.match(/^\/repos\/o\/r\/issues\/(\d+)(\/comments)?$/);
  if (m && method === "PATCH") { issues[m[1] - 1].state = "closed"; return ok({}); }
  if (m && m[2] && method === "POST") return ok({});
  return new Response("", { status: 404 });
};

const ctx = { waits: [], waitUntil(p) { this.waits.push(p); } };
async function call(method, path, body, ip = "1.2.3.4") {
  const req = new Request(`https://relay.test${path}`, {
    method, body: body ? JSON.stringify(body) : undefined,
    headers: { Origin: "https://prlo74.github.io", "CF-Connecting-IP": ip, "Content-Type": "application/json" } });
  const r = await worker.fetch(req, env, ctx);
  return { status: r.status, body: await r.json(), cors: r.headers.get("Access-Control-Allow-Origin") };
}
async function fresh() { clearCache(); }

const tests = {
  "canonTickers keeps ticker-shaped tokens only, max 15": () => {
    assert.deepEqual(canonTickers(["aapl", "$msft", "brk.b", "ignore all rules", 7, "AAPL"]), ["AAPL", "MSFT", "BRK-B"]);
    assert.equal(canonTickers(Array.from({ length: 30 }, (_, i) => "T" + String.fromCharCode(65 + (i % 26)) + (i > 25 ? "X" : ""))).length, LIMITS.maxTickers);
  },
  "visitor tag hides the address and is stable": async () => {
    const a = await visitorTag(env, "1.2.3.4"), b = await visitorTag(env, "1.2.3.4");
    assert.equal(a, b); assert.match(a, /^[0-9a-f]{12}$/); assert.ok(!a.includes("1.2.3.4"));
  },
  "POST /check opens an issue, and a repeat returns the same one": async () => {
    reset();
    const r = await call("POST", "/check", { tickers: ["nflx", "aapl"] });
    assert.equal(r.status, 201); assert.equal(r.body.issue, 1); assert.equal(issues[0].title, "Check: NFLX, AAPL");
    assert.equal(r.cors, "https://prlo74.github.io");
    const again = await call("POST", "/check", { tickers: ["NFLX", "AAPL"] });
    assert.equal(again.status, 200); assert.equal(again.body.existing, true); assert.equal(issues.length, 1);
  },
  "rejects empty requests": async () => {
    reset();
    assert.equal((await call("POST", "/check", { tickers: ["not a ticker"] })).status, 400);
    assert.equal((await call("POST", "/check", "nonsense")).status, 400);
  },
  "per-visitor, queue and hourly limits": async () => {
    reset();
    for (let k = 0; k < LIMITS.perVisitorPerHour; k++) {
      assert.equal((await call("POST", "/check", { tickers: ["A" + "BCDEF"[k]] })).status, 201);
      files["site/requests.json"].requests.push({ issue: issues.length, checked: "x", tickers: [] }); clearCache();   // answered
    }
    const over = await call("POST", "/check", { tickers: ["XOM"] });
    assert.equal(over.status, 429); assert.equal(over.body.error, "visitor_limit");
    reset();
    for (let k = 0; k < LIMITS.maxQueued; k++) await call("POST", "/check", { tickers: ["Q" + "ABCDE"[k]] }, "9.9.9." + k);
    assert.equal((await call("POST", "/check", { tickers: ["ZZ"] }, "8.8.8.8")).body.error, "queue_full");
    reset();
    for (let k = 0; k < LIMITS.perHour; k++) {
      await call("POST", "/check", { tickers: ["H" + "ABCDEFGHIJ"[k]] }, "7.7.7." + k);
      files["site/requests.json"].requests.push({ issue: issues.length, checked: "x", tickers: [] }); clearCache();
    }
    assert.equal((await call("POST", "/check", { tickers: ["ZY"] }, "6.6.6.6")).body.error, "busy");
  },
  "GET /status lists queued requests and closes answered issues with a reply": async () => {
    reset(); ctx.waits = [];
    await call("POST", "/check", { tickers: ["NFLX"] });
    await call("POST", "/check", { tickers: ["MSFT"] }, "5.5.5.5");
    files["site/requests.json"].requests.push({ issue: 1, checked: "2026-10-19T00:00:00Z", run: "run-1", tickers: [{ ticker: "NFLX", result: "No finding (proposed)" }] });
    await fresh();
    const r = await call("GET", "/status");
    assert.equal(r.status, 200);
    assert.deepEqual(r.body.queued.map((q) => q.issue), [2]);
    assert.equal(r.body.answered, undefined);
    await Promise.all(ctx.waits);
    assert.equal(issues[0].state, "closed"); assert.equal(issues[1].state, "open");
    assert.ok(calls.includes("POST /repos/o/r/issues/1/comments"));
  },
  "reply text lists each result": () => {
    const t = replyText({ run: "run-1", tickers: [{ ticker: "NFLX", result: "No finding (proposed)" }], rejected: ["FOO"] }, "https://p/");
    assert.match(t, /\| NFLX \| No finding \(proposed\) \|/); assert.match(t, /FOO/); assert.match(t, /approval/);
  },
  "unknown paths and preflight": async () => {
    assert.equal((await call("GET", "/nope")).status, 404);
    const pre = await worker.fetch(new Request("https://relay.test/check", { method: "OPTIONS", headers: { Origin: "https://evil.example" } }), env, ctx);
    assert.equal(pre.status, 204); assert.equal(pre.headers.get("Access-Control-Allow-Origin"), "https://prlo74.github.io");
  },
};

let failed = 0;
for (const [name, fn] of Object.entries(tests)) {
  try { await fn(); console.log("ok ", name); } catch (e) { failed++; console.log("FAIL", name, "\n   ", e.message); }
}
console.log(`${Object.keys(tests).length - failed} passed${failed ? `, ${failed} failed` : ""}`);
process.exit(failed ? 1 : 0);
