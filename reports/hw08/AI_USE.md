# HW8 AI Use

Sharan Lourduraj, SID4 9619

## 1. What did you use AI for, and what did you do yourself?

I used Claude for the Kafka request/response service the failure-test driver, the verification script and the offline tests, and as a help for the wording of the report. I ran every command on my own computer, kept the console output in RUN_LOG.txt, took all screenshots, chose the design (entity RECALL_NOTICE, qwen3:8b for the one full agent journey and a deterministic fast mode for the failure tests, extending the existing app on port 8619 instead of a new one), and did the commits and the tag.

## 2. Describe one thing the AI got wrong, or one thing you verified.

The assistant's code had several mistakes that only showed up when I ran it against the real Kafka broker. The worker container was marked "unhealthy" because it inherited the web image's health check for port 8619, which the worker does not serve. The test driver crashed twice (a generator that used `await`, and an environment setting passed twice), it could not read the partition count of `s9619_tasks` (the verification check failed even though Kafka had 2 partitions), and it tried to reset consumer groups that still listed killed agents as members. Separately, the assistant's offline tests used an in-memory fake of Kafka, so they passed even when real Kafka behaviour had not been shown yet.

## 3. How did you detect or verify it?

I saw each problem myself in the terminal output: the "(unhealthy)" status in `docker ps`, the Python tracebacks, and the failed verification line. I did not accept the offline tests as proof for Kafka: the duplicate, kill, poison-message and ordering results in the report come from runs against the real broker, each run twice (protection off and on), with the agent logs and topic contents saved in `reports/hw08/raw/`. I also checked that the "before" runs really show the failure (2 drafts for one question, a lost message, 30 retries and 0 good messages processed, 5 out-of-order pairs) and not only that the "after" runs look fine.

## 4. What changed, and why does it work?

The worker now has its own health check (a heartbeat file), the driver bugs were fixed, the partition count is read through Kafka's admin client, and the driver waits for killed agents to leave their consumer group before it resets offsets. The protections themselves work for these reasons: the offset is committed only after the result is published (so a killed Writer's message is delivered again), a correlation_id that was already processed is skipped (so the redelivery or a replay does no second work), a message that fails 3 times is moved to `s9619_dead_letter` and the offset is committed (so later messages are not blocked), and the Planner uses the recall notice as the message key (so related messages stay in one partition, in order). Limits I want to be clear about: the processed-id list is kept in memory (it can be written to a file, but that was not used in the recorded runs), the unkeyed ordering result is random from run to run, and the Part 3 tests used fast mode, not the model.
