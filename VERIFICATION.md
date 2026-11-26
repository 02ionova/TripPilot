# Verification record — Live provider migration

Verified on **24 November 2026**, macOS, Python 3.14.0, OpenAI SDK 2.54.0, Pydantic 2.14.4, Streamlit 1.67.0, pytest 9.2.0. The project targets Python 3.11+; this record describes the actual installed environment.

## Automated verification

- `python -m pytest -v`: **142 passed in 2.90 seconds**. All SDK responses and provider HTTP responses are mocked in automated tests. The autouse HTTP transport guard prevents accidental real network calls. No test consumes SerpApi or OpenAI credits.
- HTTP-shaped fixtures cover complete round-trip return selection/group pricing, hotel totals/nightly prices/taxes/rooms, missing prices, null coordinates, restaurants/diets, forecasts and three-season archives, opening hours and transfers, cache reuse/isolation, no-results memoization, request limits, invalid credentials, quota exhaustion and bounded timeouts.
- Agent regressions cover all six Live tools, hotel error recovery, trusted IDs, request binding, unsupported/ambiguous locations, provider/key failures, termination, structured final output, traces/redaction and Streamlit results. Original Demo tests are retained with explicit Demo settings.
- Both final genuine Live responses were parsed again with Pydantic. Cost-item sums were independently recomputed using Decimal and matched the Python budget breakdown; each was within the original user budget. Both saved schedules were also replayed through the current strict live builder using only their traced provider offers (no HTTP/model calls); all timing, opening-hour, geographic, pace and budget checks passed again.
- `python -m pip check`: **No broken requirements found**. Required httpx was already installed; no additional paid API/library/service was enabled.
- Streamlit was launched headlessly on a temporary local port 8502. `/_stcore/health` returned **HTTP 200**, body `ok`. Only that verification process was stopped afterward.
- Streamlit AppTest rendered the actual saved Rome and Paris Live results without exceptions. Each showed three correct budget metrics. These rendering checks reused saved results and made no provider searches.
- Ruff lint and formatting checks passed for all 43 Python files. `git diff --check` passed.

## Actual successful Live demonstrations

These runs used the real `gpt-4.1-mini` OpenAI API client and genuine SerpApi/Open-Meteo responses. No mock transport or scripted model was used. Provider cache hits refer to actual responses retrieved earlier during integration verification, not test data.

| Property | Rome | Paris recovery |
| --- | --- | --- |
| Input | `examples/live_rome.json` | `examples/live_paris.json` |
| Origin | Prague, Czechia | Prague, Czechia |
| Destination | Rome, Italy | Paris, France |
| Dates | 3–5 December 2026 | 3–5 December 2026 |
| Travelers / budget | 1 / EUR 2,000 | 1 / EUR 2,000 |
| Pace / diet | Relaxed / vegetarian | Relaxed / vegetarian |
| Model iterations | 8 | 8 |
| Successful tools | All six Live tools | All six Live tools |
| New SerpApi search attempts | 3 | 2 |
| Provider cache hits | 9 | 10 |
| Retrieved flights | EUR 175 | EUR 152 |
| Retrieved accommodation | EUR 32 | EUR 45 |
| Estimated food | EUR 75 | EUR 135 |
| Estimated activities | EUR 30 | EUR 75 |
| Estimated local transport | EUR 48 | EUR 48 |
| Total / remaining | EUR 360 / EUR 1,640 | EUR 455 / EUR 1,545 |

Full sanitized traces, including requests, model actions, provider results, sources, timestamps, tool feedback and final budget validation:

- [Rome Live trace](traces/20261124T205633_19e1ba5b-0276-4169-b7f3-4944c8c82099.json)
- [Paris Live recovery trace](traces/20261124T205633_30127e40-3f4e-4b19-9f70-b3131cb94ac1.json)

The Paris CLI run explicitly enabled `--demonstrate-recovery`. The real model first called `search_hotels` with `max_nightly_price=10`. The actual priced results did not meet that filter, producing `no_priced_hotels`. The model removed the restrictive filter; the broader search reused the cached provider response, succeeded and led to a validated itinerary. This is a disclosed demonstration constraint, not a hardcoded fake provider failure. Ordinary planning does not force this filter.

Rome also demonstrates genuine replanning: an initial relaxed day selected three attractions. Python returned `pace_limit`; the model reduced that day to two retrieved attractions and rebuilt successfully.

Rome's selected flight arrived at 19:40 on the first day and departed at 06:10 on the last day. Those days contain travel allowances rather than impossible destination sightseeing. The actual full sightseeing day uses retrieved venues and meal options. The program never manufactures destination visits to make a travel-only day appear full.

Flight and hotel figures are quotes retrieved on the trace timestamps, not promises of current inventory. In these two runs, their combined retrieved costs were EUR 207 and EUR 197 respectively. The remaining EUR 153 and EUR 258 were explicitly estimated. Restaurant names/dietary search indications are real provider data, but dietary compliance is not guaranteed. No bookings occurred.

## Real provider and quota verification

The user's existing `.env` had working OpenAI and SerpApi keys; it was not overwritten. Official documentation was reviewed for Flights, return-selection results, autocomplete, Hotels, Maps, Search, Account, and Open-Meteo forecast/geocoding/archive.

- Initial free Account API check: active account, **250 searches remaining**.
- Final fresh free Account API check at **2026-11-24T21:09:43 UTC**: active account, **228 searches remaining**.
- **22 SerpApi search requests in total** during integration/debugging, including the two final successful runs. Earlier failed integration runs account for 17 requests; the final successful runs used 5 new searches. Failures exposed location qualification, request binding and unreliable model-generated times, which were corrected before the final demonstrations.
- Account API checks do not consume search credits. No plan/subscription changes were requested or made. The remaining-quota value inside an individual trace is a per-run snapshot, not an account-wide reconciliation across simultaneous runs; the fresh final Account API result is authoritative for this verification.
- Real Flights autocomplete/outbound/return-selection, Hotels, Maps attractions and Maps restaurants were exercised. Both successful runs have real forecast data.
- A separate Open-Meteo historical check for Rome, 10–13 April 2027, returned four correctly labeled **Historical climate estimate** days using 2025, 2024 and 2023 seasonal observations. This used three archive requests (plus cached geocoding), zero SerpApi searches. Historical wet-day frequency was kept separate from forecast rain probability.

The 15-search cap is enforced per run, including all search attempts/retries, airport autocomplete, return selections and pagination. A cold cache may require more searches than these warm-cache final runs. Unit tests never use production caches.

## Security review and artifact distinctions

- `.env`, `.cache/`, temporary results and virtual environments are ignored. The existing `.env` was preserved.
- Known configured keys are checked against source and selected commit artifacts without printing their values. Sensitive account fields and credential-bearing URLs are redacted before cache/trace persistence. HTTP wire logging is suppressed; raw provider exception bodies are not recorded.
- Only the two new selected successful Live traces are added for this migration. Incidental failed/user traces remain local; they are not represented as successful demonstrations.
- Older already tracked genuine OpenAI traces used simulated travel tools. They remain historical **Demo** artifacts and do not prove real travel-data integration.
- `tests/artifacts/rome_mocked.json` and `paris_recovery_mocked.json` are **mocked unit-test artifacts**, not genuine API demonstrations. Their generator explicitly selects Demo settings and uses a scripted SDK.

## Reproduction and remaining manual work

```bash
python -m pytest -v
streamlit run app.py
python main.py --mode live --input examples/live_rome.json --output results/live_rome.json
python main.py --mode live --input examples/live_paris.json --demonstrate-recovery --output results/live_paris.json
```

Update example dates after their departure date. Keep keys in your own `.env`; no source changes are required. Repeated real runs spend OpenAI tokens and may consume SerpApi credits after cache expiry, so they are not part of automated testing.

Manual submission screenshots remain to be captured: Live input form, actual daily plan and budget, flights/hotel sources, and Paris recovery trace. Source hours/prices, room inventory, actual transfer routes and dietary suitability must be rechecked before travel; this application plans trips but does not reserve or certify offers.

## Budget and design regression verification — 25 November 2026

- Full automated suite: **156 passed in 3.23 seconds**, zero external API calls. Ruff lint passed.
- Streamlit AppTest verifies the top mode toggle/help, empty sidebar, mode-switch result clearing, separate meal/visit cards, four day illustrations and clear EUR 13 overrun display for a EUR 230 target / EUR 243 plan.
- HTTP fixtures verify provider thumbnails are reused without extra searches. Original Live rendering tests still pass.
- Budget tests cover original-target success, accepted alternatives, exact 10% and one-cent boundary rejection, Demo precheck, Live/Demo builders, final JSON round-trip and trace overrun disclosure.
- A closed-Monday museum regression confirms that the builder names the actual closed attraction/date, suggests retrieved alternatives, and succeeds after replacement without additional API calls.
- Fixed the weather adapter's captured date reference so the test clock remains deterministic after midnight.
- These design checks use Streamlit's test harness; a full browser screenshot is not claimed.

## Subtle notice and traveler budget adjustment — 25 November 2026

The provider disclaimer now uses a muted inline information note instead of an alert. Input widgets update independently so traveler count changes can immediately adjust the editable budget by EUR 500 per person. Planning remains exclusively button-triggered. Tests cover increases, multi-person changes, decreases, preserving manual edits, minimum EUR 1, repeated reruns without duplicate additions and no accidental agent invocation. Full suite: **158 passed in 3.12 seconds**; Ruff and whitespace checks passed, no external API calls.

## Madrid scheduling and iteration regression — 26 November 2026

The actual failed Milan-to-Madrid run (10–13 April 2027, three travelers, EUR 1,600) was inspected locally. Two initial builds were rejected for non-zero-padded `7:30`/`8:15` fields, but incorrectly received `request_mismatch`. Repeated failures subsequently blocked a corrected build. The original request itself matched.

Corrections normalize H:MM, distinguish field-validation errors from request tampering, allow revised arguments after previous different failures, and retain bounded identical-call/iteration protections. A validated last-iteration build finishes successfully. Late arrival no longer forces a destination attraction into a short evening window.

The saved provider records were replayed offline with the original first build and a disclosed replacement of Monday's closed/outdoor selections by an already retrieved open museum. The current scheduler/validator produced a EUR 989 estimate (flights 210, accommodation 116, food 360, activities 135, transport 168; EUR 611 remaining). This is **an offline replay of historical offers with revised selections**, not a new real LLM run, fresh quote or fabricated successful trace. Zero new OpenAI/SerpApi requests were made.

Automated regression coverage: H:MM normalization, invalid-clock rejection, precise field errors, valid corrections after four distinct failed builds, final-iteration success and late-arrival/full-day distinction. Full suite: **168 passed**.

## Consolidated information and visual itinerary — 26 November 2026

- Automated suite: **171 passed**. New checks cover a single information control, preservation/escaping of actual trip caveats, explicit over-budget metrics without alert banners, main-page flight/hotel/transfer cards, and unchanged budget/provider counters after rendering.
- Real Chromium verification used the saved genuine Rome response, not a new LLM execution. Confirmed one hover/focus information panel, availability on the Weather tab, desktop/mobile panel bounds at widths 1440 and 390, and no mobile horizontal overflow. Flight/stay cards rendered existing provider records. Screenshots were inspected locally in ignored `results/`.
- Browser external requests were blocked; zero SerpApi/OpenAI searches were made. Playwright was installed only in a temporary verification directory, not as an application dependency. The temporary local Streamlit process was stopped afterward.
- The day-by-day plan is outside the supporting tabs. Provider caveats, pricing assumptions and practical notes are aggregated in the single edge popover; input/generation failures and explicit budget-overrun metrics remain visible. Actual trace/JSON warnings are unchanged.
