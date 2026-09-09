# Product Audit — "Wire" / NewsDesk

Prepared as a read-only code audit for monetization planning. No code was modified. All file references are `path:line`. Items marked **[INFERRED]** are judgment calls or general/background knowledge, not something read directly from the code — treat them as things to verify, not facts. Everything else is a direct citation of what's in the repository.

**Repo scope actually found on disk:** a single directory, `NewsDesk/`, containing 7 source files (1,175 lines including a checked-in `uvicorn.log`), plus a `files (2).zip` in the parent folder that is a byte-identical backup of the same 7 files (confirmed by listing its contents — not a second version). There is also a local `.venv/` (not source) and no `.git` directory — **this project is not under version control.**

---

## 1. What it actually does today

**End-to-end flow:** A single Python process (`NewsDesk/app.py`) starts a FastAPI app. On startup it launches one `asyncio` background task (`refresh_loop`, `app.py:211-217`) that, every `REFRESH_SECONDS` (default 240s / 4 min), fetches all configured RSS feeds concurrently, parses them, scores/tags each entry, deduplicates against an in-memory store, trims by age and count, and updates a global in-process dict. A static single-page frontend (`NewsDesk/static/index.html`) polls a JSON API on an interval and renders the current store as a scrollable "wire" of headlines, grouped by day, with client-side search/filter/read-state. There is no separate build step, no client framework — it's one 536-line HTML file with inline CSS and vanilla JS.

**Every content source** (all defined in `NewsDesk/feeds.py:37-97`), 40 feeds total across 4 tabs:

| Tab | Feed | Access method | URL |
|---|---|---|---|
| upsc | PIB | RSS | `https://www.pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3` |
| upsc | RBI | RSS | `https://www.rbi.org.in/pressreleases_rss.xml` |
| upsc | The Hindu · National | RSS | `https://www.thehindu.com/news/national/feeder/default.rss` |
| upsc | The Hindu · Editorial | RSS | `https://www.thehindu.com/opinion/editorial/feeder/default.rss` |
| upsc | The Hindu · Lead | RSS | `https://www.thehindu.com/opinion/lead/feeder/default.rss` |
| upsc | Indian Express · Explained | RSS | `https://indianexpress.com/section/explained/feed/` |
| upsc | Indian Express · India | RSS | `https://indianexpress.com/section/india/feed/` |
| upsc | Down To Earth | RSS | `https://www.downtoearth.org.in/feed` |
| upsc | Mint · Economy | RSS | `https://www.livemint.com/rss/economy` |
| upsc | Judiciary, Parliament, Diplomacy, Schemes, Sci-Tech | Google News RSS search (`gnews()`, `feeds.py:25-31`) | `https://news.google.com/rss/search?q=...` |
| india | Moneycontrol · Markets/Business/Results | RSS | `moneycontrol.com/rss/*.xml` |
| india | ET Markets | RSS | `economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms` |
| india | Business Standard · Markets | RSS | `business-standard.com/rss/markets-106.rss` |
| india | Mint · Markets | RSS | `livemint.com/rss/markets` |
| india | RBI | RSS | (same as above) |
| india | Indices, Regulator | Google News RSS search | — |
| world | CNBC · Markets/World | RSS | `cnbc.com/id/*/device/rss/rss.html` |
| world | MarketWatch | RSS | `feeds.content.dowjones.io/public/rss/mw_topstories` |
| world | Yahoo Finance | RSS | `finance.yahoo.com/news/rssindex` |
| world | Investing.com | RSS | `investing.com/rss/news.rss` |
| world | Fed, Europe, Asia | Google News RSS search | — |
| alt | CoinDesk, Cointelegraph, Decrypt | RSS | `coindesk.com`, `cointelegraph.com`, `decrypt.co` feeds |
| alt | OilPrice | RSS | `oilprice.com/rss/main` |
| alt | Kitco, Gold, Crude, MCX, Mining | Google News RSS search | — |

Breakdown: **25 direct publisher RSS feeds + 15 Google News search-RSS feeds = 40 total.** No official/licensed paid API is used anywhere. No HTML scraping (no BeautifulSoup/lxml/scrapy in the codebase or `requirements.txt`) — the only parser is `feedparser` operating on RSS/Atom XML.

**Fetch cadence:** Purely time-driven. `REFRESH_SECONDS` env var, default 240 seconds (`app.py:37`), drives an infinite `asyncio.sleep` loop (`app.py:211-217`) started in the FastAPI `lifespan` context manager (`app.py:220-226`). There is also a manual trigger: `POST /api/refresh` (`app.py:264-267`), which the frontend's "Refresh" button and the `r` keyboard shortcut call. No cron, no external scheduler, no on-request-only mode — the loop runs continuously for as long as the one process is alive.

**Processing pipeline, in order** (all inside `fetch_feed`, `app.py:117-166`, and `refresh_all`, `app.py:169-208`):
1. **Fetch** — `httpx.AsyncClient.get` per feed, 15s timeout, redirects followed, 8-way concurrency via `asyncio.Semaphore(CONCURRENCY)` (`app.py:40-41,171-175`).
2. **Parse** — `feedparser.parse` on raw bytes, off the event loop via `asyncio.to_thread` (`app.py:121`). First 40 entries per feed only (`app.py:131`).
3. **Clean/normalize** — HTML-unescape and whitespace-collapse the title; strip HTML tags and truncate the summary to 260 characters (`strip_html`, `app.py:92-95`, called at `app.py:143`). For Google News feeds, the "Headline - Publisher" suffix is split out to recover the real source name (`app.py:138-141`), and the summary is discarded entirely because Google's is link markup, not prose (`app.py:144-145`).
4. **Language filter** — a regex over Unicode blocks (Arabic, Indic scripts, Cyrillic, CJK/Hangul) drops any non-English-looking title/summary (`is_english`, `app.py:74-89`, applied at `app.py:147-148`). This is a script-detection heuristic, not real language detection.
5. **Scoring/tagging** — `score_item()` in `relevance.py:100-114`. Pure substring keyword matching: normalize text, count hits against a hand-curated vocabulary (8 UPSC syllabus categories / 9 market sector categories, `relevance.py:16-73`), subtract a noise penalty for ~25 tabloid/entertainment phrases (`relevance.py:75-81`), add a per-feed trust weight. No ML, no embeddings, no LLM call anywhere in this path — it's `if substring in text: count += 1`.
6. **Dedup** — SHA1 fingerprint of the first 9 normalized words of the title (`fingerprint`, `app.py:98-102`). On collision, the higher-scoring version wins but keeps the original `first_seen` timestamp (`app.py:190-196`).
7. **Retention/trim** — items older than `RETENTION_HOURS` (default 72) are dropped; each tab is capped at `MAX_PER_TAB` (default 400), sorted by publish date (`app.py:200-204`).

**Output surface:** A JSON API plus one bundled static page. No email, no separate feed (RSS/Atom out), no mobile app.
- `GET /` → serves `static/index.html` (`app.py:288-290`)
- `GET /api/nav` → tab structure (`app.py:235-237`)
- `GET /api/items?tab=&min_score=&tag=&limit=` → the actual content (`app.py:240-261`)
- `POST /api/refresh` → force a fetch cycle (`app.py:264-267`)
- `GET /api/sources` → health/count per feed (`app.py:270-272`)
- `GET /api/health` → overall status (`app.py:275-282`)

None of these routes have authentication. `/api/sources` and `/api/health` are publicly readable and fully enumerate the entire feed registry and its live status to anyone who requests them (see §6).

---

## 2. Stack and architecture

**Languages/frameworks/libraries** (from `requirements.txt`, all floor-pinned with `>=`, no lockfile):
- Python — local dev interpreter is 3.13.14 (`.venv/pyvenv.cfg`); no `pyproject.toml`, no `.python-version`, so the required version isn't actually pinned anywhere in source.
- FastAPI `>=0.115`, Uvicorn `[standard] >=0.30`, httpx `>=0.27`, feedparser `>=6.0.11`.
- Frontend: no framework. Vanilla JS, hand-rolled CSS custom properties for theming, Google Fonts (Newsreader, Public Sans, IBM Plex Mono, IM Fell English family) loaded via `<link>` in `static/index.html:7-9`.
- Stray dependency: `python-dotenv` is installed in the local `.venv` but is **not** in `requirements.txt` and **not imported** anywhere in the `.py` files — dead/unused, likely leftover from experimentation.

**Component diagram (text):**
```
Browser (static/index.html, vanilla JS)
   │  fetch() polling: /api/nav, /api/items, /api/health, /api/sources, POST /api/refresh
   ▼
FastAPI app  (app.py — single process, single Uvicorn worker)
   │
   ├── asyncio background task: refresh_loop() ── sleeps REFRESH_SECONDS, then:
   │        └── httpx.AsyncClient  ──(8-way concurrent GET, 15s timeout)──▶  40 external RSS/Atom endpoints
   │                                                                          (25 publisher feeds + 15 Google News search)
   │        └── feedparser.parse (off-loop thread)
   │        └── relevance.score_item()  — keyword scoring, in-process, no network
   │
   └── in-memory dict:  STORE: dict[tab] -> dict[fingerprint] -> Item
        (no external datastore; lost entirely on process restart)
```
No queue, no cache layer, no CDN, no external LLM, no message broker, no reverse proxy config checked in.

**Database:** **NOT PRESENT.** There is no DB engine, no schema, no migrations, no ORM. The "store" is a plain Python `dict` held in process memory (`STORE`, `app.py:65`). Retention is time+count based only (72h / 400 items per tab), enforced in-memory on every refresh (`app.py:200-204`). A process restart discards everything — the README explicitly acknowledges this and proposes SQLite as future work (`README.md:67-69`), but it isn't implemented.

**Where state lives / machine-specific assumptions:** All state is transient, in the memory of one Python process. There's nothing hardcoded to a personal account (no embedded API keys, no personal file paths — `BASE = Path(__file__).parent`, `app.py:44`, is portable). But the *architecture* is implicitly single-viewer: the `Item` dataclass (`app.py:52-62`) and every API response carry no `user_id`/tenant concept at all — there is exactly one global feed store shared by every request, with no notion of "whose" data it is. That's a data-model-level single-tenancy assumption, not just a deployment-config one. Also architecturally single-process: the fetch loop is started via `asyncio.create_task` inside `lifespan` (`app.py:220-226`) — running more than one Uvicorn worker would spin up N independent fetch loops (N× the outbound request volume to every publisher) with N independent, inconsistent in-memory stores, since nothing is shared across processes.

The checked-in `uvicorn.log` (4,493 lines, spanning 2026-08-12 20:30 to 2026-08-14 18:01, i.e. this is where it has actually been run) confirms it was run with local dev settings (`uvicorn app:app --reload`, per the README) on what is evidently a personal laptop — see §7.

**LOC by file** (all in one flat directory, no subpackages):
| File | Lines | Nature |
|---|---|---|
| `app.py` | 290 | Custom — fetch loop, dedupe, store, API |
| `static/index.html` | 536 | Custom — entire frontend (HTML+CSS+JS) |
| `relevance.py` | 114 | Custom — scoring logic + curated keyword data |
| `feeds.py` | 111 | Custom — hand-curated source registry (mostly data, not logic) |
| `check_feeds.py` | 51 | Custom — dev/ops tooling (feed health checker) |
| `README.md` | 73 | Docs |
| **Total app code** | **1,102** | |

100% custom, hand-written code — there is no generated scaffolding, no ORM boilerplate, no framework CLI cruft. But a large fraction of `feeds.py` and `relevance.py` is *data* (URLs, keyword lists) rather than *logic*; see §6 for how defensible that data actually is.

**NOT PRESENT anywhere in the repo:** tests (no `test_*.py`, no `pytest` dependency), CI config (no `.github/workflows`, no other CI file), `Dockerfile`, any IaC/deploy manifest, `.env`/`.env.sample`, database migrations, `llm_hook.py` (referenced by name in `relevance.py:9`'s own docstring as where you'd plug in an LLM, but the file does not exist).

---

## 3. Cost to run

**Current actual cost: $0/month in paid dependencies.** There is no LLM API call anywhere in the code (`score_item` is pure regex/substring matching, `relevance.py:100-114`), no paid hosting (it runs on `localhost`), no paid database, no paid search service, no email service. Every grep for `openai`, `anthropic`, `azure`, `api_key`, `stripe`, `sqlite`, `postgres` etc. across the `.py`/`.html` files comes up empty except as prose in the README's "where to take it next" wishlist (`README.md:61,67,70`) — those are unimplemented ideas, not code paths.

**LLM call sites today: zero.** So "calls per fetch cycle" = 0, and "cost per 1,000 articles processed" = **$0** at current settings, full stop. The only thing worth costing out is the README's *proposed, unbuilt* enhancement — batch 20 headlines per Azure OpenAI call (`README.md:61-64`) — shown here as a **[INFERRED]** forward-looking estimate, not a measurement of anything that exists:

- Assume a small/cheap chat model at roughly $0.15 / 1M input tokens and $0.60 / 1M output tokens **[INFERRED — verify current provider pricing before relying on this]**.
- Batch size 20 headlines/call. Prompt ≈ instructions (~200 tokens) + 20 headlines (~300 words ≈ 400 tokens) ≈ 600 input tokens. Output ≈ 20 × `{relevant, syllabus_area, one_line}` (~25 tokens each) ≈ 500 output tokens. So **~1,100 tokens/call, ~55 tokens/article**.
- **Per 1,000 articles:** 1000/20 = 50 calls → 30,000 input tokens + 25,000 output tokens → (30,000 × $0.15/1M) + (25,000 × $0.60/1M) = $0.0045 + $0.015 = **≈ $0.02 per 1,000 articles**.
- **Per user per month:** this classification would be shared infrastructure (one global feed, not per-user personalization — see §2/§4), so the relevant number isn't "per user," it's "total, divided across however many users share it." At an observed volume in the log of ~750-800 "new" items registered per 4-minute refresh cycle (`uvicorn.log`, e.g. "refresh complete: 754 new items") — which, note, looks anomalously high for genuinely novel stories in 4 minutes and may indicate the dedupe fingerprint is under-collapsing near-duplicates or feed churn (see §7) — even at a generous 10,000 truly-new items/month, total LLM cost ≈ **$0.20/month for the whole platform**. Divided across 1,000 paying users, that's **$0.0002/user/month**. LLM cost is not a meaningful constraint on this business even if fully built out; it rounds to noise next to hosting and engineering time.

**Fixed vs. linear with users:**
- **Fixed (today, and under the current architecture):** feed-fetch bandwidth/compute, hosting compute, the keyword-scoring CPU cost, and the hypothetical shared LLM classification cost above — all of these happen once per fetch cycle regardless of how many people are looking at the result, because there is exactly one global store serving everyone identically.
- **Linear with users (would only appear if you build the features described in §4):** any per-user personalization/private feed set, any per-user LLM call, database storage per user, and email/push delivery (e.g., a digest email costs roughly $0.0005–$0.001/recipient via typical transactional email providers **[INFERRED]** — this scales directly with subscriber count).

**Hosting cost:** **NOT PRESENT** in the repo (no Dockerfile, no deploy manifest) — currently $0 because it runs locally. The README suggests Azure Container Apps, one container, min replicas 1 (to keep the background loop warm, avoiding scale-to-zero) (`README.md:70-73`). **[INFERRED]** a small always-on container for this workload would likely run on the order of $10-40/month, but this has not been priced or deployed.

---

## 4. Multi-tenancy and productization gaps

Today it serves exactly one implicit "user" — there is no user concept at all, just one global feed. Checklist to serve 1,000 paying strangers, with effort estimates:

| Gap | Current state | Effort |
|---|---|---|
| **User accounts / auth / sessions** | NOT PRESENT. Every API route is unauthenticated (`app.py:235-282`). No login, no cookies, no tokens. | 3-5 days for a minimal email+password or magic-link flow with a session store |
| **Per-user preferences/personalization storage** | NOT PRESENT. `Item`/`STORE` have no `user_id`; `min_score`, `tag`, `source` filters are all client-side/query-param only and reset every page load (`static/index.html:260-264`, persisted only via `localStorage` for read-state and theme — device-local, not account-level). | 3-5 days once accounts + a DB exist |
| **Payments/subscription state** | NOT PRESENT. No Stripe/Paddle/etc. reference anywhere. | 2-3 days for a basic Stripe Checkout + webhook flow |
| **Rate limiting / abuse protection** | NOT PRESENT. `POST /api/refresh` (`app.py:264-267`) is unauthenticated and unthrottled — anyone can hit it repeatedly to force full re-fetch of all 40 upstream feeds, which is both a self-inflicted-DoS risk and a way to get your server's IP flagged/blocked by publishers. | 1-2 days for basic per-IP/per-key rate limiting |
| **Secrets management** | NOT PRESENT — and currently there are no secrets to manage (no API keys used anywhere). This becomes a real gap the moment you add Stripe keys, an email API key, or an LLM API key. | <1 day (env vars + a secrets store) once secrets exist |
| **Observability (logging/error tracking/uptime alerting)** | Partial. Logging exists (`logging.basicConfig`, `app.py:35`, INFO-level, written to `uvicorn.log`) and per-feed health is tracked in-memory (`HEALTH` dict, exposed at `/api/health`, `app.py:275-282`). No error tracking service (Sentry etc.), no uptime alerting, no log rotation/shipping — `uvicorn.log` is a flat, ever-growing local file. | 2-3 days for basic Sentry + uptime pings + log rotation |
| **Onboarding / password reset / account deletion / data export** | NOT PRESENT (no accounts exist at all). | Bundled into the accounts work above; add 2-3 days for reset/deletion/export flows specifically |
| **Single-user/single-config assumptions in the code** | The `STORE` dict has no tenant dimension (`app.py:65`); the fetch loop is a single `asyncio.create_task` per process with no cross-process coordination (`app.py:220-226`), so running >1 worker process multiplies outbound fetch traffic instead of sharing it; `/api/sources` and `/api/health` are globally readable with no scoping (`app.py:270-282`). | Rearchitecting to a shared-fetch/multi-reader model (one fetcher, many authenticated readers) is the core work — 5-8 days, and it's a prerequisite for most of the above rather than a separate line item |
| **CORS** | NOT PRESENT (no `CORSMiddleware`). Fine today because the frontend is served from the same FastAPI app (`app.py:285-290`); would block any separate frontend origin from calling the API. | <1 day if/when you split frontend and backend origins |

**Rough total for a bare-bones paid multi-tenant v1** (accounts, payments, basic rate limiting, persistence, minimal observability): **~20-30 developer-days**, mostly because almost none of this exists yet, not because any single piece is hard.

---

## 5. Legal and licensing exposure — bluntly

**Source classification:** All 40 sources are consumed as **RSS/Atom feeds via `feedparser`** (`app.py:25,121`) — there is no HTML scraping anywhere in the codebase (no BeautifulSoup/lxml/scrapy, confirmed by `requirements.txt` and by reading every `.py` file). This matters: RSS is a format publishers expose specifically for third-party syndication, which is a materially different posture than scraping rendered pages. 25 of the 40 are the publisher's own feed; 15 are Google News search-RSS (`gnews()`, `feeds.py:25-31`) — an *undocumented*, unofficial endpoint (the same one browsers/RSS readers hit, but not a published, licensed, or SLA-backed API). Google can change or block this endpoint at any time with no notice and no recourse; 37.5% of the source list depends on it.

**robots.txt / rate limits:** **NOT PRESENT.** No code anywhere checks `robots.txt` (confirmed by grep — no "robots" string in the codebase). The only self-imposed courtesy measures are an honest `User-Agent` string (`UA = "newsdesk/1.0 (feed check)"`, `app.py:42`), a 15-second timeout, an 8-way concurrency cap (`app.py:40-41`), and the 4-minute default refresh interval (`app.py:37`) — these are load-politeness defaults, not robots.txt compliance or a legal safeguard.

**Does it store/redisplay full article text?** **No — this is the strongest fact in the product's favor.** The exact code path that decides this: `strip_html(getattr(entry, "summary", ""), limit=260)` (`app.py:92-95`, called at `app.py:143`) truncates every summary to 260 characters, taken directly from the publisher's own RSS `<description>` field — never the full article body (which isn't fetched at all; only the RSS document itself is retrieved). For Google News items specifically, the summary is discarded entirely and replaced with an empty string (`app.py:144-145`), because "Google's summary is a list of link markup, not prose." What's stored and rendered, per item, is: headline, ≤260-char publisher-provided snippet, source name, and an outbound link to the original article opened in a new tab (`static/index.html:449`, `target="_blank" rel="noopener"`). **Nowhere in the codebase is a full article body fetched, stored, or rendered.**

**Copyrighted content copied/stored/re-rendered:** The only copied material is: (a) headlines verbatim, and (b) ≤260-character snippets verbatim from each publisher's own syndication feed. This is the same pattern used by mainstream RSS readers and news aggregators (Feedly, Google News, Apple News-style aggregation), which is broadly practiced — but "broadly practiced by others" is not the same as "cleared for a paid commercial product," and that gap has **not** been reviewed here.

**Sources with likely commercial-redistribution friction:** **[INFERRED / general industry knowledge, not verified against any specific publisher's current Terms of Use — this needs a lawyer before charging money, not this audit].** Government press-release feeds (PIB, RBI) are comparatively lower risk — Indian government press material is typically distributed under open/public-domain-leaning terms. Private commercial publishers in this list — The Hindu, Indian Express, Moneycontrol, Economic Times, Business Standard, Mint, CNBC, Dow Jones/MarketWatch, Yahoo Finance, CoinDesk, Cointelegraph, Decrypt, OilPrice — commonly reserve rights against "systematic," "commercial," or "aggregation for redistribution" use of their content/feeds in their Terms of Use, even when the feed itself is technically public. None of these Terms of Use were fetched or reviewed as part of this audit (out of scope — this is a code-only review); flagged as the single highest-priority item for outside legal review before this becomes a paid product (see "Open questions").

---

## 6. What's genuinely hard to copy — skeptical take

Be unflattering: **there is very little defensible technology here.** A competent developer, handed nothing but "aggregate RSS into a scored, tabbed reader," could rebuild the *mechanics* of this entire backend in **2-4 days**: the fetch loop is `httpx` + `asyncio.gather` behind a semaphore (`app.py:169-181`, standard pattern), the dedupe is a 5-line SHA1-of-first-9-words hash (`app.py:98-102`), and the scoring is a ~15-line linear substring-count formula (`relevance.py:100-114`). None of it uses ML, embeddings, or an LLM despite the README gesturing at that direction (`README.md:61-64`) — that's aspirational, not built (`llm_hook.py` doesn't exist).

What has *some* real value, with honest caveats:
- **The UPSC syllabus-mapped keyword taxonomy** (`relevance.py:16-61`, ~180 terms across 8 categories) encodes non-obvious domain knowledge about what the UPSC exam actually tests. It would take someone unfamiliar with the exam real research time (**[INFERRED] 1-3 days**) to reconstruct a comparably useful taxonomy — this is the closest thing to actual IP in the repo.
- **The 40-feed registry** (`feeds.py:37-90`), curated across 4 verticals with hand-tuned trust weights, required real work to find *which specific RSS paths currently still resolve* — the README itself notes publishers quietly retire feed paths and "PIB in particular has moved its feed more than once" (`README.md:45-47`), which is directly corroborated by the checked-in log showing PIB's original URL now 302-redirecting to a different path (`uvicorn.log`, 2026-08-14 18:01:42). But this is a *maintenance* moat, not a durable one — it decays without upkeep and is fully exposed to anyone who asks: **`GET /api/sources` returns the entire feed registry (all 40 names + tabs) to any unauthenticated caller** (`app.py:270-272`). Whatever research went into finding these feeds is handed away for free by the product's own API today.
- **The frontend** (`static/index.html`, 536 lines) is the most polished artifact in the repo — dual light/dark theming via CSS custom properties, a distinct "1800s gazette" alternate skin (`static/index.html:21-31,178-219`), full keyboard navigation (`j`/`k`/`o`/`/`, `static/index.html:519-531`), and a deliberately `setInterval`-based (not `requestAnimationFrame`) auto-scroll ticker with a documented rationale about background-tab throttling (`static/index.html:492-496`). This reflects real product taste and iteration. It is still, mechanically, "just CSS and vanilla JS" — a competent frontend developer could rebuild the *mechanics* in a few days; matching the *taste* is the part that doesn't timebox cleanly.

**Bottom line:** if forced to be blunt, the honest answer is close to "nothing here is strongly defensible as software." There's no proprietary dataset, no ML model, no accumulated user data, no network effect, no exclusive licensing — just well-organized glue around public RSS feeds, a decent keyword list, and a nicely designed page. Any durable moat for a paid product will have to come from something not yet in this repo: accumulated proprietary data (e.g., a growing labeled dataset from real usage), brand/audience, exclusive source licensing, or speed of execution — not from the current code.

---

## 7. Current deployment state

**Deployed:** No. `NOT PRESENT` — no Dockerfile, no cloud config, no deploy script. The checked-in `NewsDesk/uvicorn.log` shows it has only ever been run locally via `uvicorn app:app --reload` (the `--reload` flag is a *development* flag — single process, file-watcher overhead, not meant for production) on what is evidently a personal laptop: the log shows a burst of `[Errno 11004]`/`[Errno 11001] getaddrinfo failed` warnings across every single feed simultaneously around 2026-08-12 22:04 (`uvicorn.log:243-282`), consistent with the machine losing network connectivity or sleeping — exactly the kind of interruption a real deployment target wouldn't have. The log spans 2026-08-12 20:30 through 2026-08-14 18:01 (~45 hours) and then simply stops — the process was presumably killed manually, not crashed (no traceback in the log at all — `grep -c Traceback` returns 0).

**What breaks running unattended for 30 days:**
- **Total data loss on any restart** — the store is pure in-memory (`app.py:65`); a crash, redeploy, or the host machine sleeping/rebooting (as already observed in the log) wipes everything, including all read-state that isn't `localStorage`-backed client-side.
- **Single-process assumption** — no supervisor/systemd/container restart policy exists in the repo, so an unhandled crash (the `refresh_loop` does catch and log exceptions per-cycle, `app.py:213-216`, so a single bad feed can't kill it — but nothing protects the FastAPI process itself) would simply stop the service with nothing to bring it back.
- **Unbounded feed churn possibly stressing dedupe** — the log shows refresh cycles reporting **754-794 "new" items added in a single 4-minute window** (`uvicorn.log`, final lines) across only 40 feeds. That's a surprisingly high novelty rate and suggests the 9-word-prefix fingerprint (`app.py:98-102`) may not be collapsing near-duplicate reposts/feed-churn as well as the README's dedupe claim implies — worth investigating before relying on it for a paying customer, since the only backstop is silently dropping older items once `MAX_PER_TAB` (400) is exceeded (`app.py:200-204`), which for a paying user means content quietly disappearing with no warning.
- **No monitoring/alerting** — if it silently stops fetching (e.g., all feeds start failing), the only signal is the passive `/api/health` endpoint (`app.py:275-282`); nothing pushes a notification.

**Known bugs/TODOs/failure modes visible in the code:**
- `relevance.py:9` docstring points to `llm_hook.py` for a "better" scoring path — the file doesn't exist. Dead reference / aspirational note left in a docstring.
- `python-dotenv` is installed in the local `.venv` but unused and not in `requirements.txt` — harmless but indicates an untracked local environment drift.
- No `.gitignore`/version control at all — the repo isn't a git repository, so there's no history, no way to see what changed when, and the checked-in `uvicorn.log` (a runtime artifact, not source) is sitting in the source tree next to the actual code.
- The apparent dedupe/novelty-rate anomaly noted above.

---

## 8. Fastest path to a chargeable v1

Ranked by effort-to-value, smallest changes to the *existing* code (not a rewrite):

1. **Add SQLite persistence** (the README already scopes this, `README.md:67-69`) — replace the in-memory `STORE` dict with a SQLite table keyed on the existing `fingerprint`. This is the foundation the other two below need (read-state that survives restarts, multi-day archive/search), and it directly fixes the "total data loss on restart" failure mode from §7.
   *Files touched:* new `db.py`; `app.py` (swap `STORE` reads/writes for DB calls in `refresh_all`, `app.py:169-208`, and `items()`, `app.py:240-261`).
   *Effort estimate: 2-3 days.*

2. **Ship the daily digest email** (also already scoped in the README as "~40 lines," `README.md:65-66`) — a scheduled job that renders the top-N scored items into an email. This is the difference between "a page you have to remember to open" and a habit-forming push product, which is usually what turns a personal tool into something worth paying for. Requires picking a transactional email provider (new paid dependency) and a minimal recipient table (email + tab preference) — doesn't need full accounts yet, just a mailing list.
   *Files touched:* new `digest.py`; `app.py` (register a second scheduled task alongside `refresh_loop`, `app.py:220-226`); `requirements.txt` (email SDK).
   *Effort estimate: 2-4 days*, including an unsubscribe link (a legal requirement for commercial email, not optional).

3. **Put a paywall in front of the existing single-tenant app** — the smallest possible way to charge money at all: add one auth dependency (even a single shared password/API-key check) in front of the existing routes, wire up a Stripe Payment Link + webhook that flips an "active" flag, and deploy one instance. This does *not* require multi-tenancy — it monetizes the app exactly as it is today, as "premium access to one curated feed."
   *Files touched:* `app.py` (auth dependency on the existing routes, `app.py:235-282`; new `/webhook` route); `requirements.txt` (Stripe SDK); a new (currently nonexistent) `Dockerfile`/deploy config.
   *Effort estimate: 2-3 days*, but note this alone yields the weakest product — one shared feed for every payer, no personalization, no push — likely low willingness-to-pay on its own without #2.

*Recommended order: 1 → 2 → 3 (persistence is a prerequisite for a good digest; the paywall is trivial to bolt on last). Total for all three: roughly 6-10 developer-days to a chargeable v1, assuming the legal question in §5 is resolved first.*

---

## Open questions for the human

- **Legal review of each publisher's Terms of Use for commercial RSS redistribution** — this audit only establishes *what the code does* (headline + ≤260-char snippet + link, never full text); it does not establish that this is *cleared* for a paid product for each of the 25 direct publisher feeds. This is the single biggest open risk and needs a lawyer, not a code review.
- **How reliant can the product be on the 15 Google News search-RSS feeds** given they're an unofficial, unlicensed endpoint (37.5% of all sources) — is there an acceptable fallback if Google blocks or changes it?
- **What is the actual daily volume of genuinely new (non-duplicate) stories** across the 40 feeds? The log's 754-794 "new items per 4-minute cycle" figure looks too high to be true novelty and needs investigation — it materially changes the cost/scale math in §3 either way.
- **Is any personalization/premium differentiation planned**, or is the intended product "one curated feed, sold to many people"? This determines whether the near-zero marginal LLM/hosting cost per user in §3 holds, or whether costs become linear with users once personalization is added.
- **Was this ever intended to be more than a personal tool** — e.g., is there a target audience size, price point, or geography already in mind? Nothing in the repo indicates market sizing, target price, or competitive positioning; that's entirely outside what a code audit can answer.
- **Git history** doesn't exist (not a git repo), so there's no way to know from the code alone how this evolved, who else may have touched it, or whether any earlier version had different (perhaps riskier) scraping behavior.
