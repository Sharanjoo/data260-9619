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

Replace this paragraph with your interpretation of the measured values. Explain what two users
sending the fixed input might see, then give one acceptable and one unacceptable example of
run-to-run variation.
