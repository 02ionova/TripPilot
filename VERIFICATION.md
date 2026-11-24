# Verification record

Verified on 24 November 2026, macOS, Python 3.14.0, OpenAI SDK 2.54.0, Pydantic 2.14.4, Streamlit 1.67.0, pytest 9.2.0.

- Ruff lint and formatting checks passed for all 24 Python files.
- Dependencies installed successfully into the existing workspace `.venv`.
- `python -m pytest -v`: **79 passed in 1.51 seconds (final run after formatting)**.
- Tests include full mocked five-tool success, hotel `no_results` → revised search → successful Paris build, trace generation, secret redaction, request tampering rejection, bounded API retry/iteration behavior, and real Streamlit rendering through AppTest.
- Streamlit launched at `http://127.0.0.1:8501`; `/_stcore/health` returned **HTTP 200**, body `ok`.
- Streamlit AppTest rendered the input form, a complete successful result (three budget metrics), and an error result without exceptions.
- `python main.py --input examples/rome.json --output results/rome.json` exited with code **1**, correctly explaining that `OPENAI_API_KEY` is missing and writing a final error JSON plus a timestamped trace.
- Deterministic mocked reference executions were generated through the actual agent loop and tools: Rome **EUR 243**, Paris **EUR 203**, both within budget. Paris includes one hotel no-results response and subsequent revised search. These are **mocked unit-test artifacts**, not real LLM demonstrations.
- Source, runtime trace and reference artifacts were reviewed for credentials. No actual API key was available or committed. Redaction tests use deliberately fake credential strings.
- The local Git repository is initialized on `main`. It has not been published or pushed.

## Genuine demonstration status

No API key was found in the process environment, project `.env` or workspace `.env`. Consequently **no genuine successful OpenAI runs were performed**. Paid API access, actual model planning quality and the two required genuine successful traces remain unverified.

After adding a key to the project's `.env`, activate an environment with the requirements installed and run from this directory:

```bash
python main.py --input examples/rome.json --output results/rome.json
python main.py --input examples/paris.json --output results/paris.json
```

Inspect the printed trace paths in `traces/`. Both must show `success`, all five tools and valid budgets. Paris must additionally show a failed hotel search, changed filters and successful recovery with vegetarian meals. If needed, transparently revise the documented prompt search heuristic/data and rerun. Do not relabel mocked reference traces as genuine.

## Included artifacts

- `traces/20261124T181356_315c663a-d2fc-4876-892d-74052a31ed87.json`: actual CLI missing-key failure trace, zero API iterations.
- `tests/artifacts/rome_mocked.json`: full mocked successful reference trace.
- `tests/artifacts/paris_recovery_mocked.json`: full mocked successful recovery reference trace.
- `requirements-tested.txt`: exact installed package versions.

Regenerate mocked artifacts with `python tests/generate_mock_traces.py`. This command never contacts OpenAI.

Screenshots remain manual placeholders in the README. Capture the form, genuine Rome itinerary and budget, and genuine Paris recovery with the trace expanded after supplying a key.
