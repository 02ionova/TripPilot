# Submitted execution evidence

These are two genuine successful OpenAI agent runs using Live providers, executed on **24 November 2026**. They are preserved evidence, not current travel offers. The demonstration inputs intentionally differ from the original simulated Rome/Paris scenarios: Live prices are variable, so both use a EUR 2,000 total budget and 3–5 December 2026 dates. The original course-style examples remain in `examples/rome.json` and `examples/paris.json` for explicit Demo Mode.

## Run 1 — Rome

Full JSON: [Rome Live trace](../traces/20261124T205633_19e1ba5b-0276-4169-b7f3-4944c8c82099.json). Input: [live_rome.json](../examples/live_rome.json).

Prague, Czechia → Rome, Italy; 3–5 December 2026; one traveler; relaxed pace; museums, architecture and local food; vegetarian.

| Iteration | Observable action | Result |
| --- | --- | --- |
| 1 | `search_flights` | Complete round-trip options retrieved |
| 2 | `search_hotels` | Priced accommodation retrieved |
| 3 | `get_weather` | Daily forecasts retrieved |
| 4 | `search_activities` | Real attractions retrieved |
| 5 | `search_restaurants` | Restaurant suggestions retrieved |
| 6 | `build_itinerary` | `pace_limit`: too many attractions for a relaxed day |
| 7 | `build_itinerary` | Revised selection accepted by Python |
| 8 | Structured final decision | `success` |

Flights arrive late on the first day and depart early on the last day. Those days contain appropriate travel/meal allowances rather than impossible destination sightseeing. The full sightseeing day contains retrieved venues.

## Run 2 — Paris: recoverable search failure

Full JSON: [Paris Live trace](../traces/20261124T205633_30127e40-3f4e-4b19-9f70-b3131cb94ac1.json). Input: [live_paris.json](../examples/live_paris.json).

Prague, Czechia → Paris, France; 3–5 December 2026; one traveler; relaxed pace; museums, architecture and local food; vegetarian.

| Iteration | Observable action | Result |
| --- | --- | --- |
| 1 | `search_flights` | Complete round-trip options retrieved |
| 2 | `search_hotels`, maximum EUR 10/night | `no_priced_hotels` |
| 3 | Broader `search_hotels` request | Cached real provider results reused; accommodation found |
| 4 | `get_weather` | Daily forecasts retrieved |
| 5 | `search_activities` | Real attractions retrieved |
| 6 | `search_restaurants` | Vegetarian-oriented real restaurant results retrieved |
| 7 | `build_itinerary` | Schedule and estimated budget accepted |
| 8 | Structured final decision | `success` |

This run explicitly used `--demonstrate-recovery`: the prompt requested an initially restrictive hotel filter for the teaching demonstration. The real tool returned the no-results error; the model chose the revised search. Neither the tool error nor a successful itinerary is fabricated or injected into the agent loop. Ordinary planning does not force this restrictive filter. Provider dietary indications are not a guarantee of dietary suitability.

## Independently checked costs

All figures are EUR for the whole party. Retrieved quotes are historical; estimated items are planning allowances.

| Cost | Rome | Paris | Provenance in these runs |
| --- | ---: | ---: | --- |
| Round-trip flights | 175 | 152 | Retrieved price |
| Entire accommodation stay | 32 | 45 | Retrieved price |
| Food | 75 | 135 | Estimated cost |
| Activities | 30 | 75 | Estimated cost |
| Local transportation | 48 | 48 | Estimated cost |
| **Total** | **360** | **455** | Retrieved + estimated |
| Original budget | 2,000 | 2,000 | User input |
| Remaining budget | 1,640 | 1,545 | Computed in Python |

Both runs use every Live tool and stay within the **original** requested budget. Rome used three new SerpApi searches and nine cache hits; Paris used two searches and ten cache hits. Cache entries came from earlier genuine provider requests, not mocked test fixtures. These warm-cache counts are not a guarantee for a fresh installation.

## Inspect without spending API credits

From the repository root:

```bash
python verify_submission.py
```

The checker reads only the two saved traces, validates their final Pydantic models, checks all six successful tools and tool-call IDs, independently sums cost items/categories with Decimal, checks the original budgets and confirms recorded error recovery. It does not re-run the scheduler, verify current provider inventory or independently prove the historical network origin; the full traces and [verification record](../VERIFICATION.md) provide that audit context.

To inspect manually, open `request`, `iterations`, `events` filtered by `kind: tool_call`, `final_response` and `budget_validation`. Match each assistant call ID to the tool event and its returned result. The next iteration shows the model's revised observable action. No hidden chain-of-thought is stored.

## Run new demonstrations

```bash
python main.py --mode live --input examples/live_rome.json --output results/live_rome.json
python main.py --mode live --input examples/live_paris.json --demonstrate-recovery --output results/live_paris.json
```

Update input dates when they are in the past; supported travel years are 2026–2027 and trip length is 1–14 days. Use your own keys. New runs incur OpenAI usage and potentially SerpApi search credits; exact offers, model decisions, iterations and totals can differ. The submitted traces are not overwritten by these commands.
