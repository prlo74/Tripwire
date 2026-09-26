# QA log

Grading by a separate adversarial reviewer agent against the build prompt's rubric (Must M1–M9 pass/fail; Should S1–S8 scored 0–2). Stop rule: all Must pass and Should ≥ 85%, max 5 rounds.

## Round 1 (2026-09-26)

> # Laura Screen: QA round 1 (adversarial reviewer, 2026-09-26)
>
> Graded against local `site/index.html`, `site/page.html`, `pipeline/*`, `evidence/*`. I re-fetched every source live (bypassing the builder's cache, except for justice.gov press releases, where I used `pipeline.http.fetch` with `ttl_hours=0` to force a fresh DOJ API call). I checked quotes, dates and financials against EDGAR filing indexes and fresh XBRL companyfacts. I could not call ArtifactData, so M6 and M8 are graded from code only.
>
> ## MUST
>
> | # | Result | Reason |
> |---|---|---|
> | M1 Evidence | **PASS** (with defects) | I re-opened all 6 Black sources and all 11 Watch sources (Ford, Accenture, Meta x2, Tesla CRD). All 17 quotes are verbatim, 50 words or fewer, Tier 1, and support the stated clause. Every date is correct except one: the Newsmax 8-K was filed 2025-08-18, not 2025-08-15. "Opened this run" is really a read from a cache that can be up to 30 days old. |
> | M2 Rule fidelity | **PASS** (flag) | No settlement goes to Black, no old finding goes to Black, nothing is proposed from Tier 2, and nothing from the do-not-list is proposed. Tesla Diaz is a qualifying (b) jury verdict inside the window. Fox and Newsmax meet the spec's literal "SJ on falsity" example, but both opinions expressly leave actual malice (the "knowingly" part) for trial, and the clause text still says "Knowingly spread false information". Findings older than 7 years that become Watch are not required to have a tripwire. |
> | M3 No fabrication | **FAIL** | Tickers, CIKs and every gate figure match fresh XBRL. But the Ford caveat says "The release states no admission by Ford", and the EEOC release says nothing about admission. Missing capex and missing debt are turned into 0 instead of "unknown": SCHL FCF is shown as $50.9M although $48.4M of capex is tagged as `PaymentsToAcquireOtherPropertyPlantAndEquipment`. |
> | M4 Parser | **FAIL** | The builder's `test_parser.py` passes (15/15). My `tests/test_parser_reviewer.py` fails 12 of 16. |
> | M5 Look-through | **PASS** | The tests cover single ETF, several ETFs, an ETF with several Black names, zero exposure, per-$10K fallback, direct holding and the boundary. My hand check on live data (SPY 35%, VTI 20%, QQQ 10%; Black = FOXA, FOX, NMAX, TSLA) gives 0.572189 + 0.331624 + 0.329635 = **1.2334%**, and the JS returns the same 1.23344795. |
> | M6 Human in loop | **PASS** (code-only) | Labels come only from `approvals` docs (`currentLabels`). Chips are marked "Proposed" and list counts say "approved · proposed". Defects: approved labels are keyed to the live proposal list and can vanish; the look-through counts proposed Black by default; approve/reject needs no reason. |
> | M7 Accessibility | **PASS** | `test_contrast.py`: 82/82. No orange (#FB8D1A) text on white; it is only used as a background with dark ink (7.3:1). Status always shows icon + word, including "OK:" and "Unavailable:" on source chips. A 3px `:focus-visible` outline was confirmed by tabbing. Buttons are real buttons. Minor: list-card `<button>`s contain `<h2>` and `<ul>`, which is invalid content. |
> | M8 Privacy | **PASS** (code-only) | No emails in page source, data.json, `out/`, `db_writes` or tracked files. `config/local.yaml` and `cache/` are gitignored. The ledger stores hashes of uid and key, not emails. The page reads only `subscribers/<own uid>`. Low: the SEC contact email goes in the `From` header to every host (courts, DOJ, SSGA, CourtListener). |
> | M9 Runs clean | **FAIL** | `python3 -m pipeline.run` exits 0 in 22s with no errors, and there is one retry. But `http.fetch` serves stale cache on failure without raising, so an outage is reported as OK with fresh `opened_at` stamps. That is not "reported", and it contradicts "never route around it". |
>
> ## SHOULD
>
> | # | Score | Reason |
> |---|---|---|
> | S1 Clarity | 2 | From the screenshots alone I could tell what each card is for: run status and freshness; Black, Watch and Aligned counts (0 approved / N proposed); Needs approval with rule, quote and source; ETF look-through gauge and bars; paste chips; values-fail table; leads; alerts; audit; methodology. Understandable in 5 seconds. Only snag: TSLA shows as "Proposed" on both the Black and Watch cards. |
> | S2 Bento | 1 | Consistent 18px radius and 20px gap. At 375px, scrollWidth is 375 (tables scroll inside `.tbl-wrap`). At 1280px the Paste card (s4) grows very tall with the example chips, which leaves a large empty area under the ETF card (s8). |
> | S3 Freshness | 1 | As-of dates appear on run status, sources, ETF rows, evidence and gate FY. The Black/Watch/Aligned cards and the Leads card have no as-of date. The values-fail row shows a date only for a failing market-cap check. |
> | S4 Speed | 2 | Cached full run took 21.8s. Page load (DCL) is about 0.45s at 1280 and 375. The page is 874 KB. |
> | S5 Discovery | 1 | There are 4 discovery proposals (10 or fewer), ranked by confidence, each with a Tier-1 source. Accenture (Watch) is sound. Ford Watch is sound but its caveat is wrong. Alphabet (YouTube Partner Program "creator economy") is defensible at Medium. WBD's quote is only a segment list, so the values link is thin. Legal discovery is silently capped at 45 days, not the configured 365-day first-run lookback. |
> | S6 Explainability | 2 | The RUNBOOK key table plus the Methodology card are enough to change thresholds without code. |
> | S7 Export | 1 | The CSV has a BOM, CRLF line ends, quoting, 2 evidence links + dates + quotes, and the approval trail. But without `window.claude` it throws a TypeError, so the read-only view fails silently. Other gaps: no formula-injection guard (=,+,-,@); caveat, tripwire and evidence beyond 2 are dropped; decisions on proposals deleted by `dbsync` are missing from the export. |
> | S8 Tone | 1 | Wording is neutral and mostly in the sources' own words. Accenture and Meta-FHA get consistent Watch treatment. But the Fox/Newsmax clause text asserts "Knowingly" when the court did not decide that, and the Ford caveat misstates the source. That is the kind of error most likely to be attacked on politically sensitive names. |
>
> **Should total: 11/16 = 69%.**
>
> ## Defects (most severe first)
>
> 1. **evidence/discovery-2026-09.yaml:17**: The Ford caveat says "The release states no admission by Ford"; the EEOC release is silent on admission. Change it to "The EEOC release does not mention an admission; the conciliation agreement was not reviewed." Also, `kind: settlement_no_admission` is unverified: add a lead to get the agreement, or say "admission status unknown".
> 2. **pipeline/http.py:142-146**: After both retries fail, it returns stale cache silently, so status stays `ok` and `opened_at` is stamped now. Instead raise, or return a `stale=True` flag that `evidence.check_record` records ("served from cache dated X") and that `run.py` surfaces as `ok: False` / "stale". Also cut the `doc_text` TTL (**pipeline/docs.py:38**, 30 days) to under one run interval, or record the real fetch time from `fetched_at()` as `opened_at` (**pipeline/evidence.py:74**).
> 3. **pipeline/evidence.py:93** (Fox/Newsmax): The clause text reads "Black (a) Knowingly spread false information…" but both opinions leave actual malice undecided ("actual malice as to FNN and/or FC" for trial; Newsmax granted only on per se, falsity, publication and defenses). Add "(falsity found; knowledge not adjudicated)" to the clause text for `merits_ruling` on clause (a), and list it as an open rule question for the team, next to the EEOC one.
> 4. **pipeline/financial.py:151, 177-179**: A missing capex tag becomes 0 and a missing debt tag becomes 0, and both then pass. Return `pass: None` / "unknown" instead. Add `PaymentsToAcquireOtherPropertyPlantAndEquipment` (SCHL: $48.4M) and prepublication-cost tags to the `TAGS["capex"]` list. For D/E, only treat debt as 0 when a tag explicitly reports 0 (e.g. SHOP `ConvertibleDebtCurrent` = 0).
> 5. **site/parser.js:27-35, 100-110**: Title-case grouping swallows tickers and separators. Examples: "Tsla" gives not found; "Aapl Msft" and "Apple, Microsoft" merge into one phrase (the comma is lost because `tokenize` drops separators before grouping). Fix: keep separator boundaries while grouping, and try a ticker lookup on title-case tokens of 5 characters or fewer before treating them as a name.
> 6. **site/parser.js:31-34**: `tokenize` issues:
>    - Trailing "." is kept, so "AAPL." becomes AAPL- and is not found.
>    - Full-width "ＡＡＰＬ" is silently dropped (0 items).
>    - ZWSP and em dash do not split tokens.
>    - "NASDAQ:AAPL", "AAPL:US" and "BRK B" are not handled.
>
>    Fix: NFKC-normalize, split on `[\s,;$​—–|]`, strip trailing ".", strip `EXCH:` / `:US`, and join `XXX [A-C]` into class tickers.
> 7. **site/parser.js:136-138**: Single letters and prose words are silently accepted. "Alphabet Class A" gives Agilent (A), "BRK B" gives B, and "I own AAPL" gives the OWN ETF, all with no attention flag. Flag tokens of 1-2 letters and lowercase dictionary words as "check" items, not silent matches.
> 8. **site/page.html:511-520** (`currentLabels`): Approved labels come only from the current `S.proposals`. `dbsync.export` deletes proposals that drop out of a run (e.g. a source goes down and the record becomes a lead), so an **approved Black label silently disappears**. Derive labels from `approvals` (which already store tickers and `to`), as `run.py:current_labels` does.
> 9. **pipeline/evidence.py:121-123**: The tripwire check excludes `kind == "finding"`, so an old finding that becomes Watch has no tripwire, which breaks the spec's "each Watch entry needs a tripwire". Require a tripwire whenever the outcome is watch.
> 10. **site/page.html:1020**: `window.claude.use("downloads")` throws when `window.claude` is undefined (the read-only view), so the CSV button fails silently. Guard with `window.claude && window.claude.use`. Also: prefix cells starting with `=+-@` with `'` (**site/page.html:1005**); add caveat, tripwire and all evidence URLs; include approvals whose proposal no longer exists.
> 11. **site/page.html:334**: "Count proposed Black too" is checked by default, so the headline exposure includes unapproved labels (TSLA). Default it to off (approved only), or show both numbers.
> 12. **pipeline/run.py:252**: Legal discovery is capped at 45 days, while `rules.yaml discovery.first_run_lookback_days: 365` and the page's `run.discovery_since` says 2025-09-26. Either honour the config or document the cap and report the real window in one place.
> 13. **evidence/records.yaml:78**: The Newsmax 8-K `doc_date` of 2025-08-15 is the event date; EDGAR shows it was filed 2025-08-18. Use the filing date, or label the field "event date".
> 14. **evidence/records.yaml:248**: CNBC is labelled "Tier 2" but cnbc.com is not in `tier2_domains`, so it is scored as unlisted/banned. Fix the label, or add the domain to Tier 2 if the team agrees.
> 15. **pipeline/http.py:130-137**: The "bot challenge page" error is overwritten by `last_err = f"HTTP {r.status_code}"`, which gives the confusing "HTTP 200" failure message seen in testing. Use `continue`/`elif` so the specific error is kept.
> 16. **tesla-crd-eeoc-open-2026** (records.yaml): The "survived a motion to dismiss" basis is inferred from "trial set" and "in discovery". The source does not mention an MTD. Say so in the caveat.
> 17. **site/page.html:294-310**: List cards are `<button>`s containing `<header>`, `<h2>` and `<ul>`, which is invalid content for a button (screen readers flatten it). Make the card a `<section>` with a real "Open full table" button inside.
> 18. **site/page.html (layout)**: At 1280px the Paste card is much taller than the ETF card, which leaves dead space. Put Paste at `s12` below, or cap the chip area with scroll.
> 19. **site/page.html:574-580**: The Black/Watch/Aligned cards and the Leads card show no as-of date. Add "as of <run date>" and the event dates for leads.
> 20. **pipeline/http.py (headers)**: The SEC contact email is sent as `From` to every host, not just sec.gov. Limit it to sec.gov.
>
> ## M4 detail: reviewer parser tests (`tests/test_parser_reviewer.py`), 12 of 16 fail
>
> | Test | Input | Result |
> |---|---|---|
> | mixed_case_ticker_resolves | `Tsla` | FAIL: not found, no suggestion |
> | mixed_case_tickers_not_merged | `Aapl Msft` | FAIL: one merged not-found item |
> | trailing_period_after_ticker | `AAPL. MSFT.` | FAIL: not found |
> | comma_separates_company_names | `Apple, Tesla` | FAIL: merged "Apple Tesla" not found |
> | fullwidth_input_not_silently_dropped | `ＡＡＰＬ` | FAIL: 0 items, 0 attention |
> | invisible_and_dash_separators | `AAPL​MSFT—TSLA` | FAIL: one not-found item |
> | exchange_prefix_and_suffix | `NASDAQ:AAPL AAPL:US` | FAIL |
> | class_letter_not_silently_recognized | `Alphabet Class A` | FAIL: A (Agilent) accepted silently |
> | space_separated_class | `BRK B` | FAIL: BRK not found + B accepted |
> | prose_word_not_silently_an_etf | `I own AAPL` | FAIL: OWN ETF accepted silently |
> | name_and_ticker_same_company_dedup | `Apple Inc. AAPL` | FAIL: 2 items, 1 attention |
> | uppercase_name_with_suffix | `APPLE INC` | FAIL: extra "INC" not-found chip |
> | etf_forms / class_dot_then_bare / spec_fox_live_map / resolve_name_without_choice | | PASS |
>
> ## Side effects of this review
> - Ran `pipeline.run`, which rewrote `site/data.json`, `out/state.json`, `out/alerts.json` and `site/tickers.json`. The run id changed to run-20260926T071541; content is otherwise the same. `site/index.html` was not rebuilt.
> - My forced-fresh fetches (`ttl_hours=0`) re-wrote the cache entries for the Meta settlement PDF (`justice.gov/crt/case-document/file/1516666/dl`), the Accenture press-release page and the two DOJ press-release API queries in `cache/http`, with the same content.
> - Added `tests/test_parser_reviewer.py`. Artifacts are in /tmp/claude-0/qa/ (screenshots shot-1280.png, shot-375.png, c1-c3.png, m1.png; fresh source texts in texts.json).

### Fixes applied after round 1
1. Ford caveat now says the EEOC release does not mention admission and the agreement was not reviewed.
2. `http.fetch` no longer serves stale cache after a failed retry; sources are re-opened each run (TTL 20h) and "opened" uses the real fetch time.
3. Fox/Newsmax clause text now states the scope: falsity found, knowledge not adjudicated. Added as an open rule question (Methodology, RUNBOOK).
4. Financial gate: missing capex or debt tags are "unknown", not 0. Added `PaymentsToAcquireOtherPropertyPlantAndEquipment` (SCHL FCF now $2.5M). Zero debt for NYT and SHOP comes from verified quotes in their 10-Ks (`evidence/financial-notes.yaml`).
5–7. Parser rewritten: NFKC, zero-width and dash separators, exchange prefixes/suffixes, "BRK B", Title-case tickers, comma-separated names, "APPLE INC", ordinary words and single letters flagged, name+ticker duplicates merged as aliases. All 16 reviewer tests pass.
8. Page labels come from approval records (which now store company, clause, evidence), so approved labels survive later runs.
9. Every Watch outcome requires a tripwire.
10. CSV export guarded when the runtime is missing; formula-injection guard; adds caveat, tripwire, extra evidence URLs and decisions on dropped proposals.
11. Look-through counts approved Black only by default, and shows the "if all proposed are approved" figure.
12. Legal discovery first-run window is an explicit setting (`discovery.legal_first_run_lookback_days: 45`).
13. Newsmax 8-K date corrected to the filing date, 2025-08-18.
14. CNBC removed; the lead cites the CA AG release.
15. Bot-challenge error message kept.
16. Tesla caveat says the motion-to-dismiss status is inferred.
17. List cards are sections with a real "Open full table" button.
18. Layout: ETF full width; Paste beside a stacked column (values-fit, leads, alerts).
19. As-of lines on list cards, leads and the values-fit table.
20. SEC contact email sent only to sec.gov hosts.
Also: WBD values link downgraded to Low with a caveat about its pending Paramount Skydance merger (per its Q2 2026 10-Q).
