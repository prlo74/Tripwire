# Tripwire relay (Cloudflare Worker)

Lets the public page start a check with one click, with no GitHub account and no new tab.
The page posts the tickers here; the Worker opens a `Check: ...` issue with its own token, and
that issue fires the Claude cloud routine (see `../ROUTINE.md`). It also serves results
(`/status`, `/data`) and closes answered issues with a reply.

- `POST /check {"tickers": [...]}`: up to 15 tickers. Limits: 3 checks per visitor per hour,
  10 per hour overall, 5 waiting at once. Visitors are told apart by an HMAC of their IP
  (keyed with the token), so the public issue never shows an address.
- `GET /status`: queued requests and results (`site/requests.json`); closes answered issues.
- `GET /data`: fresh `site/data.json` and `site/decisions.json` after a run.
- Tests: `node tests/relay.test.mjs` (also run by `pytest`).

## Deploy (once)

1. Create a fine-grained GitHub token at https://github.com/settings/personal-access-tokens/new:
   Repository access "Only select repositories" -> `prlo74/Tripwire`; Permissions ->
   Repository -> Issues: Read and write. Nothing else. Pick an expiry after the competition.
2. `cd relay && npx wrangler login` (creates or opens a free Cloudflare account).
3. `npx wrangler deploy`. It prints the address, e.g. `https://tripwire-relay.<you>.workers.dev`.
4. `npx wrangler secret put GITHUB_TOKEN` and paste the token from step 1.
5. Put the address in `site/config.json` (`{"relay": "https://..."}`), commit and push. The page
   uses the relay from then on; with an empty address it falls back to GitHub's issue form.

To stop it: `npx wrangler delete`, or empty `site/config.json`. Revoke the token on GitHub
when the competition is over.
