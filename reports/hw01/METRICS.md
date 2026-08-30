# Homework 1 Experiment Metrics

- Model: `qwen3:8b`
- Generated (UTC): `2026-08-29T00:27:59Z`
- Runs per temperature: 20
- Percentile method: linear interpolation between adjacent ordered observations

## Tag variation

| Metric | Temp 0.7 | Temp 0.0 |
| --- | --- | --- |
| Distinct tag sets | 6 | 1 |
| Tags in all runs | None | `allergen warning`, `food recall`, `product safety` |
| Tags in exactly one run | `allergen recall` | None |

## Latency

| Metric | Temp 0.7 | Temp 0.0 |
| --- | ---: | ---: |
| p50 (ms) | 25716.793 | 22887.268 |
| p95 (ms) | 35811.859 | 23351.704 |
| p99 (ms) | 62209.399 | 24772.876 |

## Interpretation

The fixed input produced 6 distinct tag sets at temperature 0.7 and 1 distinct tag set at temperature 0.0. Therefore, two users submitting identical input may receive different but topically related tags when temperature 0.7 is used, while temperature 0.0 produces more consistent results. Variation is acceptable for optional discovery tags, such as “product safety” versus “allergen recall,” but it is not acceptable if a safety-critical warning about undeclared peanuts is omitted or changed.

