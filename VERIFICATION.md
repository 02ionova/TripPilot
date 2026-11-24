# Verification record

Verified on 24 November 2026, macOS, Python 3.14.0, OpenAI SDK 2.54.0, Pydantic 2.14.4, Streamlit 1.67.0, pytest 9.2.0.

- Ruff lint and formatting checks passed for all 24 Python files.
- Dependencies installed successfully into the existing workspace `.venv`.
- `python -m pytest -v`: **107 passed in 1.42 seconds (after arbitrary-city support)**.
- Tests include full mocked five-tool success, hotel `no_results` → revised search → successful Paris build, trace generation, secret redaction, request tampering rejection, bounded API retry/iteration behavior, and real Streamlit rendering through AppTest.
- Streamlit launched at `http://127.0.0.1:8501`; `/_stcore/health` returned **HTTP 200**, body `ok`.
- Streamlit AppTest rendered the input form, a complete successful result (three budget metrics), and an error result without exceptions.
- `python main.py --input examples/rome.json --output results/rome.json` exited with code **1**, correctly explaining that `OPENAI_API_KEY` is missing and writing a final error JSON plus a timestamped trace.
- Deterministic mocked reference executions were generated through the actual agent loop and tools: Rome **EUR 243**, Paris **EUR 203**, both within budget. Paris includes one hotel no-results response and subsequent revised search. These are **mocked unit-test artifacts**, not real LLM demonstrations.
- Source, runtime traces and reference artifacts were reviewed for credentials. The API key is stored locally in ignored configuration and is not committed. Redaction tests use deliberately fake credential strings.
- The local Git repository is on `main`; the user subsequently authorized synchronization with the designated GitHub remote.

## Genuine demonstration status

An API key became available after initial implementation. Two genuine successful runs were executed with `gpt-4.1-mini` on 24 November 2026:

- Rome: 7 model iterations, all five tools, **EUR 341 total / EUR 600 budget**, EUR 259 remaining.
- Paris: 11 model iterations, all five tools, **EUR 209 total / EUR 350 budget**, EUR 141 remaining. Hotel search at EUR 30/night returned `no_results`, followed by a successful hostel search. All scheduled meals are vegetarian-compatible.

Both full final responses were revalidated with Pydantic. Component totals and daily costs plus flights/accommodation matched the total budget calculations. All successful tool names and Paris recovery events were verified from the genuine traces. All travel data remains simulated; no bookings occurred, regardless of model conversational wording.

Earlier real runs stopped on schedule errors or concluded infeasibility prematurely. These exposed incomplete meal planning and ineffective corrections. The updated prompt explicitly requires per-day meal/time audits and affordable alternatives; the loop gives one bounded corrective opportunity before accepting an error/infeasible decision after a recoverable builder failure. A regression test covers this behavior.

The screenshot's failed run used `gpt-5.1-mini` and returned `NotFoundError`. Separate actionable diagnostics now distinguish model-not-found, authentication, permissions and unsupported requests, recording only class and HTTP status. Past dates and invalid city labels are rejected before API calls. The earlier Prague-only restriction was subsequently replaced with arbitrary-city support. The date picker starts at the current date, and tests use a fixed clock for reproducibility.

The repository is connected to the user-authorized remote `https://github.com/02ionova/TripPilot`. Source changes and the two reviewed genuine successful traces are committed for synchronization there. Keys and incidental user traces remain local.

## Included artifacts

- `traces/20261124T182657_e85c4d77-3850-4df6-8ad1-af5326f86d7f.json`: genuine successful Rome trace, EUR 341.
- `traces/20261124T182658_1bc27b17-5ca7-4ca0-b721-f697a70fcf60.json`: genuine successful Paris recovery trace, EUR 209.
- `traces/20261124T181356_315c663a-d2fc-4876-892d-74052a31ed87.json`: actual CLI missing-key failure trace, zero API iterations.
- `tests/artifacts/rome_mocked.json`: full mocked successful reference trace.
- `tests/artifacts/paris_recovery_mocked.json`: full mocked successful recovery reference trace.
- `requirements-tested.txt`: exact installed package versions.

Regenerate mocked artifacts with `python tests/generate_mock_traces.py`. This command never contacts OpenAI.

Screenshots remain manual placeholders in the README. Capture the form, genuine Rome itinerary and budget, and genuine Paris recovery with the trace expanded from the running application.

## Budget-screening and progress regression

The two subsequent Vienna runs shown in the user screenshot attempted an unaffordable trip repeatedly. The request was 24–29 November 2026, two travelers, EUR 600. Independent catalogue arithmetic establishes a EUR 712 minimum (170 flights + 230 hostel + 252 meals + 60 transport). New early screening returns an explained EUR 112 shortfall before creating the OpenAI client, with no model iterations.

The actual CLI regression completed with `infeasible`, zero model requests and the expected component breakdown. Streamlit AppTest submitted the same form and rendered EUR 600 / EUR 712 / EUR 112 metrics with an informative warning and no application errors. A separate deterministic builder test proves that a complete valid schedule is attainable at exactly EUR 712 for this dataset. Passing the general lower-bound check alone does not guarantee a valid schedule.

The main progress area now replaces one status message instead of appending technical logs. Full results/errors remain in the expandable trace and downloaded JSON. Artificial restrictive hotel searches are disabled for ordinary planning and available only through the explicit `--demonstrate-recovery` CLI flag. The successful final message is generated by Python and never claims actual bookings.

A genuine OpenAI run of the same six-day, two-traveler Vienna request with an affordable EUR 900 budget completed successfully: **EUR 816 total, EUR 84 remaining**, all five tools, 9 model iterations. Trace: `traces/20261124T183529_19030e95-2daf-4660-a1d2-409348da8511.json`. The normal planning mode did not deliberately force restrictive hotel filters.

## Arbitrary-city verification

Both city dropdowns were replaced with free-text inputs. The catalogue preserves the original five destinations and Prague route fixtures, and creates repeatable generic synthetic fixtures for other routes and destinations. Budget screening and itinerary building use the same route-specific flight source. Extra warnings explicitly identify generic flights, fictional venues and neutral climate placeholders. No geocoding or external travel APIs were added.

Tests cover Berlin to Lisbon through all five mocked tools, shared search/precheck/builder costs, Unicode/global city labels, stable catalogue IDs, route ID rejection for a different origin, input normalization, identical-city rejection and actual free-text form submission. Existing Rome, Paris and Vienna budget regressions continue to pass.

A genuine `gpt-4.1-mini` run with `examples/berlin_lisbon.json` completed successfully: **EUR 338 / EUR 600**, EUR 262 remaining. Full trace: `traces/20261124T190154_dd0222c2-6ab2-43a6-960e-9e18fc077252.json`. This is a genuine LLM execution over synthetic travel data, not a real-world Lisbon recommendation.
