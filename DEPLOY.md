# Deploying Charcha for free

**Platform: [Render](https://render.com), Free web service tier.**

Why Render and not GitHub Pages: Pages only serves static files, and Charcha
needs a persistent Python process (the background RSS-poll loop, the
in-memory store, `/api/chat`). Render runs the actual `app.py` process with
zero code changes. The free tier's real tradeoff is described below —
read it before you commit to this, since it changes how "always on" the
site actually is.

## 1. Create the service

1. Sign up at [render.com](https://render.com) (GitHub login is fine).
2. **New → Web Service** → connect the `tusarmahapatra/wire` repo.
3. Fill in:

   | Field | Value |
   |---|---|
   | Root Directory | `NewsDesk` |
   | Runtime | Python 3 |
   | Build Command | `pip install -r requirements.txt` |
   | Start Command | `uvicorn app:app --host 0.0.0.0 --port $PORT` |
   | Instance Type | **Free** |

4. Under **Health Check Path**, set `/api/health` — the app already exposes
   it (`app.py:309`), so Render can tell a real crash apart from a slow
   startup instead of killing the instance during the first feed fetch.

## 2. Environment variables

Add these in the service's **Environment** tab (never commit them — `.env`
is already git-ignored):

| Key | Required | Notes |
|---|---|---|
| `GROQ_API_KEY` | for chat | free key at https://console.groq.com/keys |
| `GROQ_CHAT_MODEL` | no | defaults to `openai/gpt-oss-120b` |
| `EMBED_MODEL` | no | defaults to `BAAI/bge-small-en-v1.5` |
| `CHAT_TOP_K` | no | defaults to `8` |
| `REFRESH_SECONDS` | no | defaults to `240` |
| `RETENTION_HOURS` | no | defaults to `72` |
| `MAX_PER_TAB` | no | defaults to `400` |

No `GROQ_API_KEY`? The reader still works — only `/api/chat` is disabled.

## 3. Deploy

Click **Create Web Service**. First build installs `fastembed`'s ONNX
runtime, so expect the initial build to take a few minutes. Once live,
Render auto-deploys on every push to `master` — no extra steps for future
updates.

## The free-tier tradeoff — read this

Render's free instances **spin down after 15 minutes with no HTTP traffic**
and cold-start (~30–50s) on the next request. This directly hits Charcha's
core design:

- The background `refresh_loop` (`app.py:211`) only runs while the process
  is alive — it pauses whenever the instance is asleep.
- Whoever wakes it (the first visitor after a gap) eats the cold start,
  then the existing "first fetch running" state (README) while it
  refetches everything from scratch, since the in-memory store is gone on
  every cold start.

For a personal reader you check a few times a day, this is a fine trade —
free, zero-maintenance, and "somewhat stale until you open it" is a minor
cost. If you want the background loop truly always-on (continuous polling
even with nobody watching), that requires an instance that never sleeps,
which is **not free** anywhere reputable — Render Starter is $7/mo, as is
Fly.io's cheapest always-on VM. Don't chase a free always-on tier; none
exists without abusing a platform's ToS (e.g. external cron-pinging a free
instance to fake traffic), which is unreliable and against most platforms'
terms.

## Where to take it next

- **Custom domain.** Free on Render — add it under the service's Settings →
  Custom Domains, HTTPS included.
- **Persistence across cold starts.** Swapping the in-memory store for
  SQLite (already on the README's radar) would mean a cold start serves
  yesterday's data instantly instead of blocking on a full refetch —
  worth doing before this feels annoying.
