# Updating Charcha

How to change code and get it live once the Render service is deployed.

## The short version

```bash
# 1. edit code
# 2. test locally
cd NewsDesk && ./startup.sh
# 3. ship it
git add -A
git commit -m "..."
git push
# 4. watch Render's dashboard — it builds and deploys automatically
```

That's the whole loop. No manual deploy step, no SSH, no Dockerfile to
rebuild by hand — push to `master` and Render does the rest.

## 1. Local development loop

```bash
git pull
cd NewsDesk
source .venv/bin/activate        # .venv\Scripts\activate on Windows
uvicorn app:app --reload --port 8000
```

Use `--reload` (not `startup.sh`) while actively editing — it restarts the
process on every file save instead of requiring a manual re-run.
`startup.sh` is for a clean first run, not the edit-save-check loop.

## 2. Test before you push

- Touched `feeds.py`? Run `python check_feeds.py` — it flags DEAD/EMPTY
  URLs before they cost you a production deploy.
- Touched `relevance.py`? Reload the page, check the affected tab's tags
  and the syllabus-filter cutoff still look right.
- Touched `app.py`? At minimum hit:
  ```bash
  curl localhost:8000/api/health
  curl localhost:8000/api/items?tab=upsc
  ```
- Touched `static/index.html`? Actually open it in a browser — it's a
  536-line hand-written file with no build step, so nothing else will
  catch a broken `<script>` tag for you.

## 3. Commit and push

```bash
git add -A
git commit -m "short description of the change"
git push
```

This repo pushes straight to `master`, which is the branch Render watches.
For a solo project that's fine. If a change feels risky (e.g. touching the
fetch loop or dedupe logic), consider a branch + PR first so you can review
the diff before it's live — `git checkout -b my-change`, push that, open a
PR, merge to `master` when happy.

## 4. What happens on Render

Auto-Deploy is on for `master` by default (set during service creation) —
every push triggers a new build with no action needed on your end.

- **Dashboard → your service → Logs**: live build + startup output,
  including the same `refresh complete: N new items` lines you see
  locally.
- **Dashboard → your service → Events**: a timeline of each deploy
  (queued → building → live), useful to confirm a push actually landed.
- Build takes a few minutes — `fastembed`'s ONNX runtime is the slow part.
- Render only cuts traffic over to the new instance once `/api/health`
  responds successfully, so a build that starts but immediately crashes
  won't take the live site down — the previous instance keeps serving
  until the new one is confirmed healthy.

## 5. Changing environment variables

Env vars (`GROQ_API_KEY`, `REFRESH_SECONDS`, etc.) are **never** committed —
`.env` stays local and git-ignored. To change one in production:

Dashboard → your service → **Environment** tab → edit or add the variable
→ **Save Changes**. Saving triggers an automatic redeploy with the new
value.

## 6. Rolling back a bad deploy

Two options, in order of speed:

1. **Dashboard → your service → Deploys** → find the last good deploy →
   **Redeploy**. Fastest — no git changes needed, just re-runs an old
   build.
2. **Revert in git** (better if the bad code needs to actually leave
   `master`, not just stop being served):
   ```bash
   git revert <bad-commit-sha>
   git push
   ```
   This auto-deploys the revert like any other push.

## 7. Where things live (for "I want to change X")

| Want to... | Edit |
|---|---|
| Add/remove/fix an RSS source | `NewsDesk/feeds.py` |
| Change what counts as relevant, or the syllabus/sector tags | `NewsDesk/relevance.py` |
| Change fetch/dedupe/retention behavior, add an API route | `NewsDesk/app.py` |
| Change the reader UI, keyboard shortcuts, the `min = 1.5` score cutoff | `NewsDesk/static/index.html` |
| Change chat behavior/prompt | `NewsDesk/chat.py` |

## 8. One thing to expect, not a bug

Render's free tier sleeps the instance after 15 minutes with no traffic
(see [DEPLOY.md](DEPLOY.md)). So: if the first request after a deploy, or
after being away for a while, takes 30–50 seconds and shows "first fetch
running" — that's cold start + a full refetch, not a broken deploy.
