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

## Round 2 (2026-09-26)

> # Laura Screen: QA round 2 (adversarial reviewer, 2026-09-26)
>
> This round grades commit a682626: run-20260926T073050, `site/index.html` and `site/data.json`. I confirmed that `site/index.html` is byte-identical to a fresh build of `page.html`, `data.json`, `tickers.json`, `parser.js` and `lookthrough.js`.
>
> - **Sources:** every source was fetched fresh. SEC, courts, EEOC and CA AG were read directly. Justice.gov (the DOJ API and the Meta PDF) was read through `pipeline.http.fetch` with `ttl_hours=0`.
> - **Pipeline run:** done in an isolated copy (`/tmp/claude-0/qa/copy`), so no project files changed.
> - **Live page behaviour (M6, S7):** tested by injecting a fake `window.claude` (db + downloads) in Playwright.
> - **ArtifactData:** not called, so M8 is graded from code.
>
> ## MUST
>
> | # | Result | Reason |
> |---|---|---|
> | M1 Evidence | **PASS** | I re-opened all 6 Black sources and all 13 Watch sources (Ford 2, Accenture 2, Meta FHA 2, Meta states 3, Tesla CRD 2), plus the WBD 10-Q and both new financial-notes quotes. All 23 quotes are verbatim and 50 words or fewer. All dates match EDGAR indexes or the source headers: Newsmax 8-K is now 2025-08-18, correct; WBD 10-Q was filed 2026-08-06, correct. "Opened" now uses the real fetch time. |
> | M2 Rule fidelity | **PASS** | Fox and Newsmax clause text now adds "Scope: … knowledge (actual malice) was not adjudicated", and this is listed as open question (2) in Methodology and RUNBOOK. Tripwires are now required for every Watch outcome. No settlement goes to Black, nothing is proposed from Tier 2 (CNBC removed), and nothing from the do-not-list is proposed. Tesla Diaz is still a sound (b) jury verdict. |
> | M3 No fabrication | **PASS** (with defects) | Every gate figure matches fresh XBRL. SCHL uses `PaymentsToAcquireOtherPropertyPlantAndEquipment` = $48.4M, giving FCF $2.5M. NYT and SHOP D/E = 0 is backed by verified 10-K quotes; neither has a debt tag in XBRL. Missing capex or debt now gives "unknown" (WBTN D/E is unknown). The Ford caveat is corrected. Defects: SCHL's own cash-flow statement also has **Prepublication expenditures (17.9)**, so FCF by the company's statement is **−$15.4M**, not +$2.5M. Also, financial notes are not tied to a fiscal year (defect 3). |
> | M4 Parser | **PASS** (with defects) | The builder's `test_parser.py` passes. All 16 of my round-1 tests now pass, as does my combined round-1 regression test. I added 12 new round-2 tests and **11 fail**. None of the 11 affects the spec fixture. Only one silently saves a wrong ticker: sentence words such as love/car/fun/cat become stocks. Note: the builder changed the spec-fixture assertion. "Apple Inc." is now an alias on the AAPL chip, not a separate "suggests AAPL" chip. I accept that because the intent is met. |
> | M5 Look-through | **PASS** | `lookthrough.js` and its tests are unchanged, and the round-1 hand check (1.2334%) still holds. In the live simulation (SPY 40%, proposed FOXA+FOX) the what-if line shows 0.0123%, which matches my calculation of 40 × 0.030812 / 100 = 0.01232. |
> | M6 Human in loop | **PASS** | `currentLabels` now reads `S.approvals`. In the simulation, an approved Black on a proposal the latest run dropped still shows as Approved, a rejected TSLA Black does not appear, and everything else shows "Proposed". There is no path to "approved" without an approval document. Residual issue: proposal ids do not change when the evidence changes (defect 4). |
> | M7 Accessibility | **PASS** | `test_contrast.py` passes. List cards are now `<section>`s with a real "Open full … table" `<button>`, and the 3px focus outline was confirmed by tabbing. No orange text on white. The new "Ordinary word?" chip has a warn icon plus words. |
> | M8 Privacy | **PASS** (code only) | No emails in page source, `data.json`, `out/`, `db_writes` or tracked files. The `From` header is now sent to sec.gov only (`http.py:118`). Approval docs now store company, clause and evidence, but no emails. |
> | M9 Runs clean | **PASS** | A copy run exited 0 in 23.0s with `errors: []`. The stale fallback has been removed (`http.py:145`). I simulated this: I aged a cached EEOC page by 48h and forced a `ConnectionError`. `fetch` then raised `SourceError` after 2 tries, and `check_record` returned `outcome: lead` with "source unreachable this run" and `opened_at: None`. Minor: the SPDR issuer-file fallback note is dropped (defect 9). |
>
> ## SHOULD
>
> | # | Score | Reason |
> |---|---|---|
> | S1 Clarity | 1 | Card purposes are clear from the screenshots. But the ETF card's default state (no weights, approved only) shows **$0.00 and 0.0000% on every bar**. Proposed Black names are about 1.6–3.3% of each fund, and the what-if line appears only after weights are entered. A new teammate reads "no exposure". |
> | S2 Bento | 1 | Radius is 18px throughout, and there is no horizontal page scroll at 375 (scrollWidth 375). At 1280, the Paste card is stretched to the height of the stack column (1594px), which leaves about 650px of empty space under its content. The values-fit "Why" column in the narrow stack wraps one or two words per line. |
> | S3 Freshness | 2 | As-of lines now appear on the list cards, leads (event + checked), the values-fit note, ETF rows, evidence and the run status. |
> | S4 Speed | 2 | Cached run 23.0s. Page DCL about 0.57s at 1280 and 0.47s at 375. Page is 887 KB. |
> | S5 Discovery | 2 | 4 discovery proposals, ranked, all Tier-1. Ford's caveat is now accurate. Accenture is sound. Alphabet is defensible (Medium). WBD is honestly marked Low, with a thin-link caveat and a caveat on the pending PSKY merger; the team could reasonably reject it. The legal window is now an explicit config key. |
> | S6 Explainability | 2 | RUNBOOK has the new key rows (`legal_first_run_lookback_days`, financial notes) and the open rule questions. Methodology matches. |
> | S7 Export | 2 | Guarded when `window.claude` is missing (shows "Downloads are not available in this view", no error). In the simulation, `=`, `+`, `-` and `@` cells are prefixed with `'`, rows for dropped proposals are included, and caveat, tripwire and more_evidence_urls columns are present. BOM, CRLF and quoting are correct. |
> | S8 Tone | 2 | Neutral. The Fox/Newsmax scope is stated plainly. "Thin link" describes the evidence, not the company. Ford is now accurate. Treatment is consistent across Accenture, Meta, Ford and Tesla. |
>
> **Should total: 14/16 = 87.5%** (round 1: 69%).
>
> ## Defects (most severe first)
>
> 1. **pipeline/financial.py:20-25 (SCHL FCF):** the gate ignores capex-like outflows that XBRL doesn't expose under the tags it reads. SCHL's 10-K cash-flow statement lists "Prepublication expenditures (17.9)" beside "Additions to property, plant and equipment (48.4)", so FCF is **−$15.4M** by the company's own statement, but the page shows +$2.5M passing. The outcome is unchanged (SCHL already fails on market cap), but the number is wrong. Fix: add a `financial_note` (capex_extra) for SCHL from the 10-K line. More generally, when the cash-flow statement has more investing outflows of a capitalized-cost kind, mark FCF "partial" instead of pass.
> 2. **site/page.html:918 (look-through default):** with the new "approved only" default and no weights, every bar reads 0.0000% and the headline reads $0.00. The "If all proposed Black moves are approved" line only renders in portfolio mode. Fix: in per-$10K mode, also show the proposed-inclusive per-$10K figure (e.g. "SPY: $0.00 approved · $163.48 if proposed approved"), or show proposed shares as hatched bars.
> 3. **pipeline/financial.py:184 / run.py:157-160 (financial notes not tied to a year):** a `financial_note` debt = 0 is applied to whatever `fy_end` is latest. When NYT files its FY2026 10-K, still with no debt tag, the FY2025 quote still verifies and silently fills debt = 0 for FY2026. Fix: add `as_of` to each note and use it only when `as_of == fy_end`; otherwise return "unknown".
> 4. **pipeline/run.py:166, 212 (approval not tied to evidence version):** proposal ids are `p-{tickers}-{to}-{record_id}`, which stay the same when the record's quote, caveat, clause or sources change (this round's Ford and WBD edits would have kept any earlier approval). Fix: store a hash of the proposal's clause, evidence and caveat in the approval. On mismatch, show "Evidence changed since approval" and put it back in Pending.
> 5. **site/parser.js:56 (comma split vs SEC names):** "Tesla, Inc." gives TSLA plus a not-found "Inc." chip. This is the SEC's own naming style, as in the page's own chips, e.g. "Tesla, Inc.". Fix: when a segment is only a corporate suffix (`Inc.`, `Corp.`, `LLC`…), join it to the previous segment.
> 6. **site/parser.js:104-107 (class words ignored):** "Alphabet Class A" ranks GOOG first and offers GOOGM (notes, `commonClass 0`). "Berkshire Hathaway Class B" ranks BRK-A first. The chip buttons read "GOOG? Alphabet Inc." and "GOOGL? Alphabet Inc." with identical names, so users can't tell the classes apart. Fix: parse `Class [A-C]` and rank that class first; drop non-common classes; label buttons with the class.
> 7. **site/parser.js:192 / STOPWORDS (sentence words):** "I really love my new car" makes LOVE (Lovesac) and CAR (Avis) silently recognized stocks, and "we love fun cars" silently adds LOVE, FUN and CARS. Fix: if a segment contains 2 or more stopwords or non-ticker words, flag every lowercase ticker-word in it as a `word` item.
> 8. **tests/test_rules.py (coverage gap):** none of these new paths has a test:
>    - missing capex returns unknown;
>    - missing debt returns unknown;
>    - a financial note fills debt;
>    - a financial note only applies when verified;
>    - `fetch` raises instead of serving stale cache;
>    - `current_labels`/`currentLabels` keeps approvals of dropped proposals.
>
>    Add unit tests (the round-2 simulations in /tmp/claude-0/qa/fake.js and my `http` monkeypatch can be ported).
> 9. **pipeline/etf.py:117 → run.py:240:** when a SPDR issuer file fails and N-PORT is used, `h["note"]` is not carried into `etf_data` or `status`. The page shows "SEC N-PORT" but never says the issuer file failed. Fix: add the note to `status[f"ETF holdings {e}"]`.
> 10. **pipeline/financial.py:153:** if capex is missing but capitalized software is present, capex is still treated as 0 (`capex or 0`). Also only the first matching capex tag is used, so a filer reporting both PP&E and "Other PP&E" is undercounted. Fix: require the PP&E capex for a computed FCF, and sum the component tags when both are present.
> 11. **Parser, lower severity** (all tests are in `tests/test_parser_reviewer.py`):
>     - "Apple Microsoft Tesla" (space-separated names) → one not-found item.
>     - "AAPL/MSFT/TSLA" → not found.
>     - "AAPL、MSFT" (ideographic comma) is not split.
>     - "Estée Lauder" → two not-found chips; accents break `isNameWord`.
>     - "Vanguard S&P 500 ETF" → suggests VB/VO/VT plus 3 not-founds.
>     - "GOOGL Alphabet Inc." is not merged.
>     - "Apple Inc.\nApple\nAPPLE INC" gives 2+ items.
>     - "AT&T" → not found.
> 12. **site/page.html (layout 1280):** about 650px of empty space inside the Paste card; the values-fit "Why" column is cramped. Fix: `align-self: start` on the Paste card, and put the values-fit table at s8 or full width.
> 13. **site/parser.js:242:** the alias note renders as "Also pasted as “Apple Inc.”." (double period). Cosmetic.
>
> ## M4 detail: reviewer tests (`tests/test_parser_reviewer.py`), 17 pass / 11 fail
>
> | Test | Input | Result |
> |---|---|---|
> | 16 round-1 tests | | **all PASS** (were 12 fail) |
> | r2_combined_regressions | `Tsla, AAPL. NASDAQ:MSFT ＳＨＯＰ spy` | PASS |
> | r2_sec_style_name_with_comma | `Tesla, Inc.` | FAIL: extra "Inc." not-found |
> | r2_space_separated_company_names | `Apple Microsoft Tesla` | FAIL: one not-found |
> | r2_class_word_ranks_that_class | `Alphabet Class A`, `Berkshire Hathaway Class B` | FAIL: GOOG, BRK-A first; GOOGM offered |
> | r2_name_plus_class_ticker_merge | `GOOGL Alphabet Inc.` | FAIL: 2 items |
> | r2_slash_separated_list | `AAPL/MSFT/TSLA` | FAIL |
> | r2_accented_company_name | `Estée Lauder` | FAIL: 2 not-found |
> | r2_prose_words_not_silently_tickers | `I really love my new car` | FAIL: LOVE, CAR silent |
> | r2_ideographic_comma | `AAPL、MSFT` | FAIL |
> | r2_etf_by_name | `Vanguard S&P 500 ETF` | FAIL |
> | r2_duplicate_name_forms | `Apple Inc.` / `Apple` / `APPLE INC` | FAIL: 2 items |
> | r2_ampersand_company | `AT&T` | FAIL |
>
> Full suite: **144 passed, 11 failed** (all 11 are my new round-2 tests).
>
> ## Side effects of this review
> - The only file changed in the repo is `tests/test_parser_reviewer.py`: 12 tests appended, the 16 originals kept unchanged.
> - The pipeline ran in `/tmp/claude-0/qa/copy`.
> - My forced-fresh fetches re-wrote a few `cache/http` entries with the same content: the Meta PDF, the DOJ API queries, and the EEOC page. For the EEOC page I set its mtime back after the simulation.
> - Screenshots and simulations are in /tmp/claude-0/qa:
>   - `r2-shot-1280.png`, `r2-shot-375.png`
>   - `r2-c1.png`, `r2-c3.png`, `r2-c4.png`
>   - `r2-paste.png`, `r2-m1.png`, `r2-m2.png`, `r2-live.png`
>   - `fake.js`, `clip2.js`, `probe2.js`

### Fixes applied after round 2 (stop rule was already met; these fix real defects)
1. SCHL free cash flow now subtracts prepublication expenditures ($17.9M, verified quote from the FY2026 10-K cash-flow statement): FCF −$15.4M, fails.
2. Look-through shows the "if every proposed Black move is approved" figure in per-$10K mode and a table column for it.
3. Financial notes carry `fy_end` and apply only to that fiscal year.
4. Each proposal carries an evidence fingerprint; approvals store it; a changed fingerprint puts the proposal back in Pending and flags the list entry "Re-check".
5–7, 11, 13. Parser: greedy longest-name matching ("Apple Microsoft Tesla", "Vanguard S&P 500 ETF", "AT&T", "Estée Lauder"), "Tesla, Inc.", "Class A/B/C" ranking with class labels on buttons (non-common classes hidden), name+class-ticker merge, slash lists, ideographic separators, repeated name forms merged, prose sentences flag lowercase ticker-words. All 28 reviewer tests pass.
8. New tests: tests/test_pipeline_paths.py (unknown-not-zero, FY-bound notes, no stale cache, label survival, alert sentences).
9. An SPDR issuer-file fallback to N-PORT is reported as a source problem.
10. PP&E capex tags are summed; software-only capex is unknown.
12. Layout: Paste card no longer stretches; values-fit table moved to a wider card beside the audit log.
