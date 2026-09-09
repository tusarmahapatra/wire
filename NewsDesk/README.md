# Wire — a personal news desk

Two tabs: **Current Affairs** (UPSC-shaped) and **Investing** → India / World /
Crypto·Gold·Commodities. One Python process polls RSS in the background, dedupes,
scores and tags each story, and serves a single-page reader.

## Run

Two steps:

```bash
./startup.sh   # 1. first run creates .env — add your GROQ_API_KEY, then...
./startup.sh   # 2. ...run it again to install deps and start Wire
```

Get a free Groq key at https://console.groq.com/keys. No key? Wire still
runs — only the chat feature is disabled.

Open http://localhost:8000. The first fetch takes ~10 seconds; the page shows
"first fetch running" until it lands.

<details>
<summary>Manual setup (no script)</summary>

```bash
python -m venv .venv && source .venv/bin/activate  # .venv\Scripts\activate on Windows
pip install -r requirements.txt
python check_feeds.py          # optional — see "Feeds go stale" below
uvicorn app:app --reload --port 8000
```

</details>

## How it fits together

```
feeds.py       which RSS URLs belong to which tab      ← edit this most
relevance.py   syllabus/sector vocabulary + scoring    ← edit this second most
app.py         fetch loop, dedupe, store, JSON API
static/        the reader (vanilla JS, no build step)
check_feeds.py validates every URL in feeds.py
```

**Why a backend exists:** no news site sends CORS headers, so a browser cannot
fetch RSS directly. The server also caches, so the page loads in one request
instead of forty, and survives a feed going down.

**Dedupe:** the same story from Mint and Moneycontrol collapses into one row,
fingerprinted on the first nine words of the normalised headline. The
higher-weighted source wins.

**Scoring:** every item gets a score and up to two tags. On the UPSC tab the
tags are syllabus areas (POLITY, ECONOMY, IR, ENVIRONMENT…); on market tabs
they're sectors (EQUITY, MACRO, CRYPTO, METALS…). "Syllabus filter" hides
anything scoring below 1.5, which is roughly "matched nothing in the
vocabulary". Tune the cut in `static/index.html` (`min = 1.5`) and the
vocabulary in `relevance.py`.

## Feeds go stale

The URLs in `feeds.py` are a starting registry, not gospel — publishers retire
RSS paths quietly and PIB in particular has moved its feed more than once. Run
`check_feeds.py` and replace anything that prints DEAD or EMPTY.

The reliable fallback for any beat is `gnews("Label", "search query")`, which
builds a Google News RSS search URL. It needs no API key, never 404s, and
covers topics no single publisher does. The cost is that you get headlines and
publisher names but no summaries, so keep a few real publisher feeds as the
spine and use `gnews` for coverage.

## Keyboard

`j`/`k` move · `o` open · `/` search · `r` force refresh.

## Where to take it next

- **Better filtering than keywords.** Batch 20 headlines into one Azure OpenAI
  call and ask for `{relevant: bool, syllabus_area: str, one_line: str}` per
  item. Cache by item id so each headline is classified once. Swap it in at
  `score_item` in `relevance.py` — the interface is already the right shape.
- **A daily digest.** The store is already deduped and dated; a 6 a.m. job that
  renders the top 15 by score into an email is ~40 lines.
- **Persistence.** The store is in-memory, so a restart re-fetches. SQLite with
  a table keyed on the fingerprint gives you read-state, search over months of
  archive, and revision history for free.
- **Deploy.** Azure Container Apps is the cheapest fit: one container, min
  replicas 1 (the background loop needs a warm instance, so avoid scale-to-zero
  and avoid Consumption Functions for the polling half). `REFRESH_SECONDS`,
  `RETENTION_HOURS` and `MAX_PER_TAB` are environment variables.
