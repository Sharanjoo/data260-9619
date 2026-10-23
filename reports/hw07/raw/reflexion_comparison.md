| Metric | Original (Part 2 as built) | Reflexion (Part 2 loop + verifier + reflections) | Ablation, 1st attempt only (no step-repair, no Reflexion) | Ablation with Reflexion (no step-repair) |
|---|---|---|---|---|
| Runs | 21 | 21 | 12 | 12 |
| Task success (verifier accepts) | 21/21 (100.0%) | 21/21 (100.0%) | 6/12 (50.0%) | 12/12 (100.0%) |
| Unsupported claims in final answers | 0 (in 0 runs) | 0 (in 0 runs) | 0 (in 0 runs) | 0 (in 0 runs) |
| Retry rate (runs with >=1 retry) | 0/21 (0.0%) | 0/21 (0.0%) | 0/12 (0.0%) | 6/12 (50.0%) |
| Mean retries per run | 0.00 | 0.00 | 0.00 | 0.50 |
| Mean tool calls per run | 2.67 | 2.67 | 1.83 | 3.50 |
| Mean tokens per run | 2867 | 2737 | 1703 | 3249 |
| Mean latency per run (ms) | 119265 | 123909 | 83615 | 180270 |
| Verifier false rejections | 0 | 0 | 4 | 4 |
| Stop reasons | success: 21 | success: 21 | rejected: 6, success: 6 | success: 12 |
