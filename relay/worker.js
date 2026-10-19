// Tripwire relay (Cloudflare Worker).
// Lets the public page start a check with one click, without a GitHub account. It holds a
// fine-grained GitHub token (Issues: read and write on this one repo, secret GITHUB_TOKEN),
// turns a request into a "Check: ..." issue, which fires the Claude cloud routine, and serves
// the latest results. Rate limits keep anyone from spending the owner's Claude credits.
//
//   POST /check  {"tickers": ["AAPL", "MSFT"]}  -> 201 {issue, url} | 200 {issue, url, existing}
//   GET  /status -> {requests, queued, progress, limits}   (also closes answered issues with a reply;
//                   progress = the running cloud run's progress doc, from the repo's progress branch)
//   GET  /data   -> {data, decisions}            (fresh site/data.json and site/decisions.json)
//
// Limits are counted from the repo's own issues (no extra storage): per visitor (an HMAC of the
// IP keyed with the token, so the public issue body never shows an address), per hour overall,
// and how many requests may wait at once.

export const LIMITS = { maxTickers: 15, perVisitorPerHour: 3, perHour: 10, maxQueued: 5 };
const TICKER = /^[A-Z]{1,6}(-[A-Z]{1,2})?$/;
const TITLE = /^\s*check\s*:/i;
const STATUS_TTL_MS = 15000, DATA_TTL_MS = 60000;
const memo = {};                       // per-isolate cache: {key: {at, value}}
export function clearCache() { for (const k of Object.keys(memo)) delete memo[k]; }   // tests

export function canonTickers(list) {
  if (!Array.isArray(list)) return [];
  const out = [];
  for (const raw of list.slice(0, 50)) {
    if (typeof raw !== "string") continue;
    const t = raw.trim().replace(/^\$/, "").toUpperCase().replace(/[./]/g, "-");
    if (TICKER.test(t) && !out.includes(t)) out.push(t);
  }
  return out.slice(0, LIMITS.maxTickers);
}

function cors(env, req) {
  const allowed = (env.ALLOWED_ORIGINS || "https://prlo74.github.io").split(",").map((s) => s.trim());
  const origin = req.headers.get("Origin") || "";
  return {
    "Access-Control-Allow-Origin": allowed.includes(origin) ? origin : allowed[0],
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
    Vary: "Origin",
  };
}

function json(body, status, headers) {
  return new Response(JSON.stringify(body), { status, headers: { ...headers, "Content-Type": "application/json", "Cache-Control": "no-store" } });
}

async function gh(env, path, init = {}) {
  const r = await fetch(`https://api.github.com/repos/${env.REPO}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${String(env.GITHUB_TOKEN || "").trim()}`,
      Accept: init.raw ? "application/vnd.github.raw+json" : "application/vnd.github+json",
      "User-Agent": "tripwire-relay",
      "X-GitHub-Api-Version": "2022-11-28",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
    },
  });
  if (!r.ok) {
    let why = "";
    try { why = (await r.json()).message || ""; } catch (e) { /* no body */ }
    throw new Error(`GitHub ${r.status} on ${path}${why ? ": " + String(why).slice(0, 200) : ""}`);
  }
  return init.raw ? r.text() : r.json();
}

async function cached(key, ttl, fn) {
  const m = memo[key];
  if (m && Date.now() - m.at < ttl) return m.value;
  const value = await fn();
  memo[key] = { at: Date.now(), value };
  return value;
}

export async function visitorTag(env, ip) {
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(env.GITHUB_TOKEN), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(ip || "unknown"));
  return [...new Uint8Array(sig)].slice(0, 6).map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function readFile(env, path, ref = "main") {
  try { return JSON.parse(await gh(env, `/contents/${path}?ref=${ref}`, { raw: true })); } catch (e) { return null; }
}

async function checkIssues(env, sinceIso) {
  const q = `/issues?state=${sinceIso ? "all" : "open"}&per_page=100&sort=created&direction=desc${sinceIso ? `&since=${sinceIso}` : ""}`;
  return (await gh(env, q)).filter((i) => !i.pull_request && TITLE.test(i.title || ""));
}

export async function status(env) {
  return cached("status", STATUS_TTL_MS, async () => {
    const [store, open, progress] = await Promise.all([readFile(env, "site/requests.json"), checkIssues(env),
      readFile(env, "progress.json", "progress")]);
    const done = new Map(((store && store.requests) || []).filter((r) => r.checked).map((r) => [r.issue, r]));
    const queued = open.filter((i) => !done.has(i.number))
      .map((i) => ({ issue: i.number, url: i.html_url, title: i.title, created_at: i.created_at }));
    const answered = open.filter((i) => done.has(i.number)).map((i) => done.get(i.number));
    return { requests: ((store && store.requests) || []).slice(-30), queued, answered, progress, limits: LIMITS, updated: new Date().toISOString() };
  });
}

export function replyText(r, page) {
  const rows = (r.tickers || []).map((x) => `| ${x.ticker} | ${x.result} |`);
  return [`Checked in run \`${r.run || "?"}\`.`, "",
    ...(rows.length ? ["| Ticker | Result |", "|---|---|", ...rows] : ["Full screen run. The lists on the page are up to date."]),
    ...((r.rejected || []).length ? ["", "Not recognised as US tickers: " + r.rejected.join(", ")] : []),
    "", `Proposals still need a team member's approval before anything is on a list. Page: ${page}`].join("\n");
}

async function closeAnswered(env, answered) {
  for (const r of answered.slice(0, 5)) {
    try {
      await gh(env, `/issues/${r.issue}/comments`, { method: "POST", body: JSON.stringify({ body: replyText(r, env.PAGE_URL || "https://prlo74.github.io/Tripwire/") }) });
      await gh(env, `/issues/${r.issue}`, { method: "PATCH", body: JSON.stringify({ state: "closed", state_reason: "completed" }) });
    } catch (e) { /* try again on the next status call */ }
  }
}

export async function check(env, req) {
  let body;
  try { body = await req.json(); } catch (e) { return [400, { error: "bad_request", message: "Send JSON: {\"tickers\": [\"AAPL\"]}." }]; }
  const tickers = canonTickers(body && body.tickers);
  if (!tickers.length) return [400, { error: "no_tickers", message: "No valid tickers in the request." }];
  const title = "Check: " + tickers.join(", ");
  const tag = await visitorTag(env, req.headers.get("CF-Connecting-IP"));
  const hourAgo = new Date(Date.now() - 3600e3).toISOString();
  const [recent, st] = await Promise.all([checkIssues(env, hourAgo), status(env)]);
  const lastHour = recent.filter((i) => i.created_at >= hourAgo);
  const same = st.queued.find((q) => q.title === title);
  if (same) return [200, { issue: same.issue, url: same.url, existing: true }];
  if (st.queued.length >= LIMITS.maxQueued) return [429, { error: "queue_full", message: `${st.queued.length} checks are already waiting. Try again in a few minutes.` }];
  if (lastHour.length >= LIMITS.perHour) return [429, { error: "busy", message: "The hourly limit for checks is reached. Try again later this hour." }];
  if (lastHour.filter((i) => (i.body || "").includes(`visitor: ${tag}`)).length >= LIMITS.perVisitorPerHour) {
    return [429, { error: "visitor_limit", message: `You can start ${LIMITS.perVisitorPerHour} checks an hour. Try again later.` }];
  }
  const issue = await gh(env, "/issues", { method: "POST", body: JSON.stringify({
    title, body: `Requested from the Tripwire page. A Claude cloud run checks these tickers and posts the result here.\n\nvisitor: ${tag}` }) });
  delete memo.status;
  return [201, { issue: issue.number, url: issue.html_url }];
}

export default {
  async fetch(req, env, ctx) {
    const h = cors(env, req);
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: h });
    const path = new URL(req.url).pathname.replace(/\/+$/, "") || "/";
    try {
      if (path === "/check" && req.method === "POST") {
        const [code, body] = await check(env, req);
        return json(body, code, h);
      }
      if (path === "/status" && req.method === "GET") {
        const st = await status(env);
        if (st.answered.length) ctx.waitUntil(closeAnswered(env, st.answered).then(() => { delete memo.status; }));
        const { answered, ...out } = st;
        return json(out, 200, h);
      }
      if (path === "/data" && req.method === "GET") {
        const out = await cached("data", DATA_TTL_MS, async () => {
          const [data, decisions] = await Promise.all([readFile(env, "site/data.json"), readFile(env, "site/decisions.json")]);
          return { data, decisions };
        });
        return json(out, 200, h);
      }
      return json({ error: "not_found" }, 404, h);
    } catch (e) {
      console.log("upstream error:", e && e.message);   // e.g. "GitHub 401 on /issues?..."; never the token
      return json({ error: "upstream", message: "GitHub did not answer. Try again in a minute." }, 502, h);
    }
  },
};
