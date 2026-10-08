# Putting EduVerse on Railway

Three files do the work: `Dockerfile`, `railway.json`, `.dockerignore`. They are
in the root of this folder.

One service, one address. The Node stage builds the web app, the Python stage
runs the backend and serves that build — so there is no separate frontend
service to keep in step.

---

## Before you start

Two things about this app decide the whole setup.

**It writes files.** Uploaded PDFs, converted books, figure images. Railway
gives a container a fresh disk on every deploy, so without a volume every book
you have ever processed disappears the next time you push.

**It uses SQLite by default.** That is one file on that same disappearing disk.
Postgres instead.

---

## Step 1 · Push to GitHub

Railway deploys from a repository.

```bash
cd eduverse
git init
git add .
git commit -m "EduVerse"
git remote add origin https://github.com/YOU/eduverse.git
git push -u origin main
```

Check that `Dockerfile` is at the top level of the repo, beside `backend` and
`frontend`. Railway looks for it there.

---

## Step 2 · Create the project

On railway.app: **New Project → Deploy from GitHub repo → your repo.**

It will find the Dockerfile and start building. Let it fail the first time —
there are no environment variables yet.

---

## Step 3 · Add Postgres

In the same project: **New → Database → Add PostgreSQL.**

Railway creates it and exposes `DATABASE_URL` to the other services
automatically. You do not type a connection string.

---

## Step 4 · Add a volume for the files

Open your app service → **Settings → Volumes → New Volume.**

```
Mount path:  /data
```

This is the step people miss. Without it, every converted book vanishes on the
next deploy and the reviewer screen fills with books that have no pages.

---

## Step 5 · Environment variables

Service → **Variables** → paste this in the raw editor:

```
DATABASE_URL=${{Postgres.DATABASE_URL}}
JWT_SECRET=<a long random string>
STORAGE_DIR=/data/storage
SUPERADMIN_EMAIL=you@yourschool.com
SUPERADMIN_PASSWORD=<a real password>
JWT_HOURS=12
```

| | |
|---|---|
| `DATABASE_URL` | that exact `${{Postgres.DATABASE_URL}}` text — Railway fills it in |
| `JWT_SECRET` | signs the login tokens. **Changing it signs everyone out** |
| `STORAGE_DIR` | must match the volume mount path |
| `SUPERADMIN_*` | only read the first time, when the account is created |

Generate a secret with `python -c "import secrets;print(secrets.token_urlsafe(48))"`.

**Do not set `PORT`.** Railway sets it and the Dockerfile reads it.

---

## Step 6 · Deploy

Railway redeploys when you save variables. The first build takes 5–10 minutes —
it installs PyMuPDF, numpy and opencv, which are large.

When it finishes, **Settings → Networking → Generate Domain.**

Open `https://your-app.up.railway.app/api/health`. A reply means the backend is
alive. Then the root address for the sign-in page.

---

## Step 7 · Sign in

```
https://your-app.up.railway.app/login/superadmin
```

with the email and password you set. The account is created on first start.

Demo data is **not** loaded, because the Dockerfile runs `python -m app.seed`
without `--demo`. That is deliberate: a real deployment should start with your
schools, not five invented ones.

If you do want the demo data once, add `--demo` to the CMD, deploy, then take
it out again.

---

## What to do next

**Set up the three model keys** — Book extraction (M1), Figure redraw (M2) and
AI settings each have their own screen and their own key. A key pasted into one
does nothing for the others.

**Add your first school**, then its admin, then classes and books.

**Upload a book and watch the logs.** Railway's Deployments tab shows the
uvicorn output live, which is where a conversion problem appears first.

---

## Things that will catch you out

**The build is slow.** PyMuPDF, numpy and opencv take most of it. Later deploys
are faster because Docker caches the layers — unless you change
`requirements.txt`, which invalidates them.

**One worker, on purpose.** M1 holds a lock so only one book converts at a time.
Two workers would each have their own lock and both would run, which is slower
and uses twice the memory.

**Converting a big book takes minutes.** It runs in the background, so the web
request returns straight away — but the container must stay awake. Do not put
this service to sleep.

**Memory.** Processing a 288-page scanned book with opencv and PyMuPDF wants
more than the smallest plan gives. If a job dies with no error in the log, that
is almost always memory.

**No model runs on Railway.** Ollama is not installed and should not be — point
M1 at OpenAI in the Book extraction settings.

---

## If something goes wrong

| What you see | Usually means |
|---|---|
| `{"detail":"Not Found"}` at the root | the frontend build did not land — check the Node stage in the build log |
| Health check fails | the app did not start; look for a traceback at the top of the deploy log |
| Books lose their pages after a deploy | no volume, or `STORAGE_DIR` does not match the mount path |
| Everyone signed out after a deploy | `JWT_SECRET` changed |
| Conversion dies silently | memory — try a smaller book to confirm |
