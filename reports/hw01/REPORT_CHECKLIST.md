# Homework 1 Final Report Checklist

Do not submit until every item below is complete and the PDF has no `EVIDENCE NEEDED` box.

## Configuration

- [ ] Hardware is stated as HP Pavilion laptop, 32 GB RAM, 512 GB storage.
- [ ] The exact model actually used for every run is stated.
- [ ] The report contains the intended submission commit reference.
- [ ] The report contains the working GitHub link `https://github.com/Sharanjoo/data260-9619`.
- [ ] All six personal configuration values match SID4 `9619`.

## Part 1 and deployment

- [ ] `01_web_form.png` shows the domain form and localhost URL.
- [ ] `02_js_console.png` shows JSON, destructuring, timestamp, and submission counter.
- [ ] `03_docker_localhost.png` shows the Docker-served app at port `8619`.
- [ ] `08_aws_ecs_service.png` shows exactly one RUNNING ECS task.
- [ ] `09_aws_public_ip.png` shows the app loaded from the public IP.

## Part 2, Part 3, and Part 4

- [ ] `04_agents_console.png` shows Planner, Reviewer, Finalized, and Publish JSON.
- [ ] The report gives the exact three tags, final summary, and whether Reviewer changed them.
- [ ] The fixed input file was not edited between the 40 experiment runs.
- [ ] `METRICS.md` has measured values rather than `Pending`.
- [ ] Raw JSON and CSV contain 40 runs: 20 at `0.7` and 20 at `0.0`.
- [ ] The interpretation uses the measured results and includes acceptable/unacceptable examples.
- [ ] `05_client_stats_turn3.png` and `06_client_stats_turn5.png` show `/stats` and token counts.
- [ ] `client_token_counts.json` contains five real model turns.

## Final repository

- [ ] Shared application code is under `code/` and `src/`, not under `reports/hw01/`.
- [ ] `python scripts/verify_hw01.py` passes and writes `verification.json`.
- [ ] `RUN_LOG.txt` contains real timestamps and outputs.
- [ ] `report.pdf` is visually reviewed page by page.
- [ ] `report.pdf` in the Git tag is byte-identical to the uploaded PDF.
- [ ] Final repository state is tagged `hw1` and pushed.
- [ ] `Sbnikitha` and `supriyaselvanganesan` accepted collaborator access.
- [ ] AWS resources are deleted after evidence is captured.
