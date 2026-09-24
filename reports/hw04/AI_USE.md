# AI_USE.md — HW4 (SID4 9619)

## 1. What I used an AI assistant for, and what I did myself

I used AI assistant for the MySQL backend (CRUD + session auth) improvement and the Part 4 RAG pipeline approach, along with drafting the report wording (METRICS.md, this file, RUN_LOG.txt) and some targeted code improvements along the way.

What I did myself: ran every command that touched my machine Docker, npm, every Python script, all Postman/browser testing and reviewed the output. I made the architectural calls and caught a real environment issue on my own.

## 2. One AI-produced output that was wrong/unsuitable

AI suggest that the Home page's record list (client/src/api.js, listRecords()) to call GET /api/hw4/records with no limit parameter. That's the naive N+1 endpoint the one that's intentionally inefficient for the Part 3 benchmark and with no limit it returned and lazy-loaded related data for all 5,000 seeded rows, then rendered all 5,000 into one HTML table.

## 3. How I detected the problem

I noticed it directly after the build, I opened my browser and the record list took a very long time to load. Had to check and updated the limit parameter.

## 4. What was changed, and why it works now

Re-read api.js and Home.jsx, found the missing limit and the wrong endpoint choice, and changed listRecords()to call GET /api/hw4/records-fixed?limit=50 instead the eager-loaded endpoint, capped to a reasonable page size instead of the full 5,000-row table. That cut the request from roughly 100+ SQL statements down to 3 and capped the amount of data the browser has to render. I confirmed the fix myself by refreshing the page and watching it load quickly.
