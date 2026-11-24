# EduVerse security trunk (v44)

This build is the **trunk**. Every feature build starts from it, so security fixes are never left behind on a side branch
(the AnAi lesson). Everything below lives in `backend/app/hardening.py` unless noted.

## Rules the code enforces

| Area | Rule |
|---|---|
| Start up | Production (`APP_ENV=production` or Railway's production environment) refuses to start with a weak `JWT_SECRET` (< 32 chars), SQLite, or the default Super Admin password. |
| Sign in | 30 tries per IP per 10 min, 12 per email per 15 min; 8 wrong passwords lock the account for 15 min. Unknown email and wrong password give the same answer in the same time. |
| Sessions | Tokens carry a version. Password reset (admin, reviewer, student) ends every open session. A paused organisation ends its users' sessions on the next request. |
| Book images | `/api/content/...` is paid content: signed in **and** allowed to see that book (owner, the organisation it is assigned to, or staff). The browser sends an HttpOnly, SameSite=Strict cookie limited to `/api/content`. On S3, the API answers with a 10 to 15 minute signed link. |
| Shared answers | A reply written for one student reaches others only after a reviewer approves it, or three different students asked the same. Text with instructions for the AI, links, phone numbers or abuse is never sent to the model and never saved. |
| AI cost | 40 explanations and 15 Eddie questions per student per minute; at most `AI_CONCURRENCY` model calls at once per API copy, then a quick "busy"; model timeout `AI_TIMEOUT`. |
| Secrets | API keys in settings are encrypted at rest (`SETTINGS_KEY`, or derived from `JWT_SECRET`). Existing plain keys are encrypted on the first start. |
| Uploads | Checked by content, not name; size cap `MAX_UPLOAD_MB`; PDFs with JavaScript, launch actions or embedded files are refused. |
| Responses | CSP, HSTS (on HTTPS), X-Frame-Options DENY, nosniff, referrer and permissions policy; API responses are not cached; JSON bodies over 2 MB refused; API docs hidden in production. |
| Audit log | Hash chained. `GET /api/audit/verify` reports the first edited or deleted entry. |
| Children's data | Sign up asks for age; under 18 needs a parent or guardian's name, email and consent, stored with time and IP. Learners can download their data and ask for deletion (Home, You and your goals). Have a lawyer confirm the wording against India's DPDP Act. |
| Container | Runs as an unprivileged user; root is used only to hand the storage volume over. |

## Scale

- **Background work** goes through the `tasks` table (`app/tasks.py`), not threads. A redeploy no longer loses a book halfway: the task is retried (up to 3 times) once its claim expires.
- **One box:** the API runs the worker itself (`EMBEDDED_WORKER=1`, default).
- **More boxes:** `docker-compose.yml` runs Postgres, Redis, the API (`ROLE=api`, `EMBEDDED_WORKER=0`) and a worker (`ROLE=worker`). Add API copies behind a load balancer; add worker copies for more books at once.
- **Redis** (`REDIS_URL`) shares rate limits across API copies.
- **Files:** set `STORAGE_BACKEND=s3`; images then go straight from S3.

## Still to do

- Proper schema migrations (Alembic) instead of adding columns on start.
- Move the access token from browser storage to a cookie with CSRF protection.
- Completing deletion requests from a Super Admin screen (requests are recorded in the audit log today).
- Payment gateway and its webhook signature checks.
