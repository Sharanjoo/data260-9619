# HW7 AI Use

Sharan Lourduraj, SID4 9619

## 1. What did you use AI for, and what did you do yourself?

I used Claude as a coding assistant and tests for the six parts (login and roles, the agent loop, Reflexion, the bike-share agent and its page, the prompt-injection test, and the file tools with the safety gate). I ran every command on my own computer, kept the console output in RUN_LOG.txt, took the screenshots, made the decisions (LangGraph for the framework, Streamlit for the page, how to build the second bike scenario), and did the commits and pushes.

## 2. Describe one thing the AI got wrong, or one thing you verified.

In Part 6, the model-driven safety-gate test printed PASS even though the model never called the bash tool, so nothing had actually been tested. Also in Part 4, the bike-share agent often gave wrong totals or a wrong decision. For example, in scenario P it recommended the membership even though its own totals showed pay-per-use was cheaper.

## 3. How did you detect or verify it?

For the safety-gate test I saw in my screenshot that bash was never called while the result said PASS. For the bike-share agent, every run is compared with a separate reference calculation that the agent never sees, and the page shows a warning when the decision does not match the agent's own totals. I kept every attempt, including the failed ones, in RUN_LOG.txt and PART4_NOTES.md.

## 4. What changed, and why does it work?

The safety-gate test now says PASS only if bash was really called and every command was blocked; otherwise it says NOT EXERCISED, and I re-ran it until the gate was actually tested. For the bike-share agent, the pricing tool now rebuilds the page's plan table, repeated tool calls get a reminder, and the prompt explains how to compute the totals. This made the runs better but did not make the 8B model reliable, so the report shows the results as they happened.
