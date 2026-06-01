# Summer 2026 Events Calendar — self-rebuilding site

A static webpage that lists Chicago (+ NYC) events June–September 2026. It
**rebuilds itself every Thursday at noon Chicago time** via a GitHub Action:
curated events come from `data/events.json`, and live concert listings are
pulled from the Ticketmaster API.

---

## What's in here

```
index.html                      ← the live page (auto-generated — don't hand-edit)
data/events.json                ← YOUR curated events. Edit this to add/change things.
scripts/build.py                ← builds index.html from the data + Ticketmaster
.github/workflows/rebuild.yml   ← the Thursday-noon scheduler
```

You edit `data/events.json`. Everything else runs itself.

---

## One-time setup (≈15 min, no coding needed)

### 1. Make a GitHub account
Go to https://github.com and sign up (free). Verify your email.

### 2. Create a repository
- Click the **+** (top right) → **New repository**.
- Name it e.g. `summer-calendar`.
- Set it to **Public** (required for free GitHub Pages).
- Check **Add a README** is *unchecked* (we have one).
- Click **Create repository**.

### 3. Upload these files
On the empty repo page, click **uploading an existing file**. Drag in the whole
folder contents, keeping the structure (`data/`, `scripts/`, `.github/`). GitHub
preserves folders when you drag them from your file manager. Commit.

> If drag-and-drop flattens the folders, create them manually: **Add file →
> Create new file**, type `data/events.json` (the `/` makes the folder), paste,
> commit. Repeat for `scripts/build.py` and `.github/workflows/rebuild.yml`.

### 4. Turn on GitHub Pages
- Repo → **Settings** → **Pages**.
- Under **Source**, pick **Deploy from a branch**.
- Branch: **main**, folder: **/ (root)**. Save.
- After a minute your site is live at:
  `https://YOUR-USERNAME.github.io/summer-calendar/`

### 5. (Recommended) Add the Ticketmaster key for live concerts
- Get a free key: https://developer.ticketmaster.com → register → create an app
  → copy the **Consumer Key**.
- Repo → **Settings** → **Secrets and variables** → **Actions** → **New
  repository secret**.
- Name: `TICKETMASTER_API_KEY` — Value: your key. Save.

Without the key the site still builds fine; it just won't auto-refresh concerts.

### 6. Confirm the scheduler is on
- Repo → **Actions** tab. If prompted, click **I understand my workflows,
  enable them**.
- Click **Rebuild calendar** → **Run workflow** to test it once now. Watch it go
  green, then refresh your Pages URL.

That's it. From here it rebuilds every Thursday at noon CT on its own. You can
also hit **Run workflow** anytime for an instant refresh.

---

## How to change events

Open `data/events.json` on GitHub (click the file → pencil icon). Each event:

```json
{"date":"2026-07-15","title":"Some show","cat":"music","loc":"The Vic",
 "when":"Eve","desc":"Why it's worth it.","tags":["Indie"],"star":true}
```

- `date` — `YYYY-MM-DD` (first day for multi-day events)
- `end` — optional `YYYY-MM-DD` for multi-day spans
- `cat` — one of: `hood`, `festival`, `art`, `music`, `soho`, `adventure`,
  `stage`, `film`
- `star` — `true` for a standout (optional)

Commit the edit. The next Thursday build (or a manual run) picks it up.

To change which artists get auto-pulled from Ticketmaster, edit the
`ticketmaster_queries` list at the bottom of the same file.

---

## Caveats (so nothing surprises you)

- **Soho House and Sat Nam have no public feeds** — those stay curated (edit them
  in `events.json` when you see something in their apps).
- **Ticketmaster only covers ticketed shows it sells.** Niche diaspora acts
  booked through other platforms won't appear automatically; add them by hand.
- **The schedule fires in UTC.** Two cron lines cover CDT and CST so it lands on
  local noon year-round. A no-change week simply makes no commit.
- **Free GitHub Actions** comfortably covers a weekly job.
