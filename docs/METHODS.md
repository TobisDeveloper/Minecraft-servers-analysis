# Measurement contract

This radar is a research heuristic, not a forecast. A high score is neither a success probability nor a player-population estimate. Missing data never becomes a positive gap.

## Acquisition and discovery

The seed catalog contains hypotheses, not asserted trends. Modrinth searches popular/newest modpacks plus seed queries and proposes up to five unmatched packs created within 180 days with >=5,000 cumulative downloads. Creator discovery proposes up to five previously unmatched named SMPs or "Minecraft but/ale" challenges from dated videos with >=50k views. Both use title/description heuristics and can propose a series that does not generalize to a server. A proposal does not prove a distinct game mode or acceleration. Independent demand and repeated snapshots are required. Custom `watch_terms` expand the catalog without code changes.

Each observation has a source, family, market, original URL, metric, publication/collection dates, raw series and annotations. Stable IDs hash candidate/source/URL/metric/market. Within a candidate, identical URL/metric/market evidence is deduplicated, even across imports. A project may match more than one candidate; those matches are not independent cross-candidate evidence.

## Measurements

- **Search:** 12-month complete weekly points; at least 12 required. Compare the latest four with the prior four (denominator floor 5). Sustained growth requires eight-week slope >0.5 index points/week, >10% growth, and >=4 non-decreasing steps. Mean <5 or >60% zeros marks low volume. A >3x median spike (minimum 10) that is no longer maintained is discounted. Google rescales batches: compare momentum **within a series**, not country sizes or levels across batches.
- **Local search:** CZ and SK signals are summed and divided by two even when one is missing. Sustained US growth adds at most five corroborating points. No reweighting for missing sources.
- **Creators:** dated videos within the configured lookback (default 90 days). A 50k–500k subscriber channel with views >= subscribers within 1–30 days is a breakout proxy. This is **not** a channel historical-view baseline or measured view velocity. Missing dates/counts cannot prove a breakout. Language/name hints do not verify audience geography.
- **Modpacks:** one lifetime-download snapshot contributes at most 15/100 ecosystem points. Velocity uses same-project counters >=24h apart and within 60 days, choosing the baseline closest to seven days ago. Counter decreases invalidate velocity. Two snapshots measure velocity, **not acceleration**; examine several daily reports for that.
- **Community:** dated unique posts with format keywords. Hosting/setup/friends keywords proxy intent. Last/prior 14-day question counts are shown, but pagination, sampling and feed selection can bias them. They are not a complete archive or buyer counts.
- **Servers:** strip navigation, identify listing-sized containers, remove nested duplicates. Sampled matched-listing share is not total market share. Positive count changes require equal sample sizes. A changing page rank/mix can still mimic adoption; audit citations. Unrecognized markup produces no estimate.
- **Lag:** report positive international/local take-off gaps <=26 weeks only when both series have detectable, maintained onset windows. This is a heuristic, not causation or a guaranteed future delay.
- **General reporting:** contextual, lagging, zero score weight.

## Score and gate

Weights: creators 25%, local search 30%, mods 15%, hosting intent 20%, measured local server adoption 10%.

`raw = sum(weight * signal)`

`score = max(0, raw - supply_penalty - spike_penalty) * (0.45 + 0.55 * confidence / 100)`

Supply penalty = `min(18, local sampled share * 45)`. Isolated local search spikes add 8. Confidence is **coverage**: 12 points/non-report family, up to 20 from local observations, 12 for temporal evidence, 8 for both usable local search markets; capped at 100. Sources are correlated; this is not a calibrated statistical interval.

Pilot gate: score >=45, confidence >=60, >=3 families, temporal evidence, and local demand: sustained local search, >=2 local hosting questions, or >=2 local creator channels. Low supply alone cannot qualify. Other outcomes are watch/validate, established/crowded (>=20% sampled local supply), or insufficient evidence.

## Operational fit

Unit contribution = monthly price minus RAM, CPU/storage, support and payment fees. Excludes VAT, licensing, acquisition, bandwidth overages and fixed overhead. Currency is a configurable label, not live FX conversion. RAM budgets and pilot targets are starting assumptions, not benchmarks.

Validate licensed distribution, matching clients, first join, restore, load, churn, support minutes and willingness to pay. Seasonality, moderation, creator concentration, accessibility and crossplay compatibility are explicit review tasks rather than fabricated automated measurements.
