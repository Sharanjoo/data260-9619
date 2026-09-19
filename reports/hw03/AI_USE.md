# AI Use Homework 3

## 1. What I used AI for / what I did myself
AI helped source the corpus data, the Part 2 chunking/retrieval approach, and the Dockerfile. I then tested login/logout/idle-timeout, read the real retrieval numbers and wrote the conclusions, fixed file placement, and made the commits.

## 2. One AI output that was wrong
The Dockerfile didn't copy `auth.py`/`templates/`, and later `auth.py` crashed in Docker with `TypeError: unhashable type: 'dict'` from an old-style `TemplateResponse(name, context)` call — Docker had a newer Starlette that needs `TemplateResponse(request, name, context)`.

## 3. How I verified it
`docker compose up --build` succeeded but `GET /` returned 500. `docker compose logs web` showed the real tracebacks for both bugs, not just "healthy" from `docker compose ps`.

## 4. What I changed
Fixed the Dockerfile's `COPY` lines and build context, and updated all 4 `TemplateResponse` calls to the new signature. Confirmed `GET /` → 200 after.

Also caught two bugs in `verify_hw03.py` itself: `requests` drops `Secure` cookies over HTTP (fixed by resending the cookie as a raw header), and the logout check reused a stale cookie (fixed by capturing `/logout`'s own `Set-Cookie`). Both fixed — 18/18 checks pass now.