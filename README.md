# 🎓 OpportunityHub

**Student Opportunity Discovery Platform** — a single place to discover internships, hackathons, scholarships, courses, certifications, competitions and workshops, ranked by how well they match *your* profile.

Built solo for **FITFEST 2026** · Flora Institute of Technology, Pune · GDG FIT Pune

---

## The problem

Students miss high-value opportunities because listings are scattered across
official websites, Instagram pages, college groups and WhatsApp forwards. By the
time you find a hackathon, registration closed. Scholarships go unclaimed
because nobody told you they existed.

Existing aggregators solve discovery but not **relevance** — you still scroll
past 400 listings to find the four that fit you.

## The solution

A skill-aware discovery platform where every listing carries a **match
percentage and an explanation of why it matched**, plus a **skill-gap analysis**
that tells you which skills you are missing that would unlock the most
opportunities.

## Key features

| Brief's suggested feature | Implementation |
|---|---|
| 🎓 Student Profile | Education, degree, year, skills, interests, preferred categories |
| 🔐 Accounts | Email OTP verification, login/logout, forgot + reset password |
| 🔎 Search & Filtering | Full-text search, category, mode, closing-soon, min-match, eligible-only, show-closed |
| 🏆 Hackathons & Competitions | 7 category types with per-category icons and colour coding |
| 💼 Internships | Filterable, deadline-tracked, external apply links |
| 📚 Courses & Certifications | 60+ real programmes, eligibility shown per listing |
| 🎯 Skill/Interest Recommendations | Weighted scoring with visible reason breakdown |
| 🔖 Save/Bookmark | Toggle save, dedicated Saved view sorted by deadline |
| 📊 Student Dashboard | Open count, strong matches, closing this week, category breakdown |
| 🔗 Details & External Links | Modal with full description, eligibility, tags, direct apply link |
| ⭐ **Skill-gap analysis** | Proportional bars: "C++ ████████░░ — unlocks 11 open opportunities" |
| ⭐ **Eligibility matching** | Year-of-study check per listing, with an **Eligible only** filter |

Extras beyond the brief: **a public landing page**, **email-OTP accounts with
password reset**, **match explanations**, **deadline countdowns**, and a
browsable **OpenAPI docs** at `/docs`.

## How the matching works

Deliberately explainable rather than ML — a judge can verify the arithmetic.

```
points = 3 × (matched skills)
       + 2 × (matched interests in tags)
       + 1 × (interest phrase found in the description, max 3)
       + 2 × (listing is in a category you follow)
       + 3 × (you meet the listing's year-of-study requirement)

score  = min(100, points / 18 × 100)      # 18 points = 100% match
```

Every score ships with the terms that produced it, e.g.
*"89% — Matches your skills: JavaScript, Python, React · In a category you follow (hackathon) · Open to 3rd year and above — you qualify"*.

**Eligibility matching** derives each listing's minimum year of study by parsing
its human-readable eligibility line, so no extra column is maintained across the
dataset. Ineligible listings lose 3 points, are dimmed in the UI with an explicit
warning, and can be hidden with the **Eligible only** filter. Listings with no
year restriction count as open to all, so they don't distort the ranking.

**Skill-gap analysis** inverts the same data: it counts which unlisted skills
appear across the most open listings, so it can tell you what to learn next.

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Backend | Python 3.12 + FastAPI | Auto-generated OpenAPI docs at `/docs` |
| Database | 4 pluggable backends | One repository interface: file / memory / MongoDB / Firestore |
| Frontend | Vanilla JS SPA + Tailwind CDN | **No build step, no bundler, no `npm install`** |
| Auth | Email OTP + password reset | PBKDF2 hashing, server-side sessions |
| Hosting | Cloud Run, or Cloudflare Tunnel from a laptop | Same image either way |

### Architecture

```
Browser (SPA)
   │  same-origin fetch() — no CORS anywhere
   ▼
Cloud Run ── FastAPI (uvicorn, 0.0.0.0:$PORT)
               │
               └── BaseStore  ← caching layer (60s TTL)
                      ├── FileStore       (JSON on disk; laptop / VM)
                      ├── MemoryStore     (tests only; loses everything)
                      ├── MongoStore      (MONGODB_URI set)
                      └── FirestoreStore  (GCP_PROJECT set, ADC)
```

The **repository pattern** is the key design decision: the same API code runs
against any of four backends with zero code changes, selected by the single
`DB_BACKEND` env var. That switch is explicit rather than inferred — an earlier
version inferred the backend from whichever variable happened to be set, and a
stray `MONGODB_URI` silently shadowed `GCP_PROJECT`, which is close to
undiagnosable from a deployed URL.

| `DB_BACKEND` | Persists? | Use for |
|---|---|---|
| `file` | Yes, to `data/*.json` | laptop, VM, tunnel demos |
| `memory` | **No** | unit tests only |
| `mongo` | Yes | MongoDB / Atlas |
| `firestore` | Yes | Cloud Run (GCP_PROJECT is injected automatically) |

### Authentication

Email OTP verification and password reset, implemented on the standard library
(`hashlib.pbkdf2_hmac` + `secrets`), so there is no bcrypt/passlib dependency
to install or get wrong.

- **Passwords**: PBKDF2-HMAC-SHA256, 200,000 rounds, 16-byte random salt.
  Verified with a constant-time compare. Plaintext is never stored.
- **Sessions**: opaque 32-byte random tokens held server-side in an `httpOnly`
  cookie. Nothing is encoded in the cookie, so it leaks no data and can be
  revoked instantly.
- **OTP**: 6 digits from `SystemRandom`, 10-minute expiry, locked out after 5
  wrong attempts. Codes are cleared on success.
- **The OTP is never sent to the client.** It goes to the mailbox and to the
  server log only — an OTP in an API response is readable from devtools or a
  screen share, which would defeat the point of email verification. There is a
  test asserting no `devCode`/`devToken` field can reappear.
- **Password reset**: single-use, expiring token. Resetting revokes every
  active session for that account, since old tokens were issued against the
  previous password.
- **Anti-enumeration**: `/auth/login` and `/auth/forgot` return identical
  responses whether or not an email is registered, so neither endpoint can be
  used to discover which addresses have accounts.

### Capturing a code while testing

Every code is printed to the server log, so you can complete the flow even
while mail delivery is slow or blocked:

```
INFO fitfest.auth: OTP for you@college.edu: 612840  (email sent: sent)
```

On Cloud Run use `gcloud run logs read -s SERVICE` to read the same lines.

### Three backend notes worth knowing

1. **Why not SQLite?** Cloud Run containers have an *ephemeral* filesystem. A
   SQLite file or JSON store would be wiped on every instance restart and scale
   event — a judge opening the link hours later would see an empty app. Both
   supported databases are external and always there.
2. **Why the 60-second cache?** Firestore's free tier is 50,000 reads/day. Each
   search reads ~66 documents, so 60 judges browsing would approach the ceiling
   and the app would throttle *late in the day*, when the most eyes are on it.
   Listings are read-only reference data, so caching them drops read volume to
   near zero.
3. **MongoDB Atlas free tier pauses when idle.** The first request after a quiet
   period can take a minute or two to wake the cluster, so connection timeouts
   are capped at 8s to surface errors fast rather than hanging. On Cloud Run,
   put the connection string in Secret Manager rather than `--set-env-vars`,
   since a URI embeds a username and password.

## Running locally

```powershell
.\run-local.ps1
```

Or manually:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

Open http://localhost:8080 — the landing page loads first. Create an account and
enter the 6-digit code that arrives by email. Codes are also printed to the
server log if you are testing without working SMTP.

## Hosting from a laptop (public URL, no cloud account)

```powershell
.\fetch-cloudflared.ps1   # once: downloads tools\cloudflared.exe
.\run-tunnel.ps1          # starts the app AND a public Cloudflare tunnel
```

This prints a public `https://<random>.trycloudflare.com` URL that works from
anywhere. Keep the window open or the link dies.

The app uses `DB_BACKEND=file`, so **accounts and bookmarks survive restarts** —
essential when a judge refreshes the page. Writes go to `data/*.json` via a
temp-file-then-rename, so a crash mid-write cannot corrupt the store, and a
corrupt file is quarantined on boot rather than taking the site down.

⚠️ Two limits, both of which apply to this mode only:

- The URL is **random and changes on every restart**.
- It **dies when the laptop closes**, and Cloudflare tunnels are rate-limited —
  an abused tunnel can be shut off.
- **Not suitable for the submission.** The brief asks for a Google Cloud Run URL.
  Also, `data/` lives on your disk, so it cannot serve more than one machine.

No cloud account or credentials needed: with no database env vars set the app
uses the in-memory store and re-seeds on every boot. Signup works too — the OTP
appears in the UI instead of being emailed.

> Run **one** uvicorn worker locally. The in-memory store is per-process, so
> multiple workers would each hold a separate copy and lose bookmarks between
> requests. The app refuses to start if you try — set `--workers 1`.

## Configuration

Copy `.env.example` to `.env` and fill in what you need. `.env` is gitignored;
**never commit it.** Everything is optional locally.

| Variable | Purpose |
|---|---|
| `MONGODB_URI` | Use MongoDB. Takes priority over `GCP_PROJECT` |
| `MONGODB_DB` | Database name (default `fitfest`) |
| `GCP_PROJECT` | Use Firestore via Application Default Credentials |
| `REQUIRE_DB` | Set `1` in production so a missing DB config fails loudly instead of silently using memory |
| `SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `EMAIL_USER` / `EMAIL_PASS` | Gmail SMTP for OTP + reset. Needs 2FA and an **App Password** |
| `EMAIL_FROM` | Sender shown in emails |
| `PUBLIC_BASE_URL` | Deployed URL, used to build reset links |
| `OTP_TTL_MINUTES` | Default `10` |
| `SESSION_TTL_DAYS` | Default `30` |
| `CACHE_TTL_SECONDS` | Listing cache window, default `60` |

### MongoDB

Point `MONGODB_URI` at an Atlas cluster or a local `mongod`. The `MongoStore`
creates unique indexes on `students.email` and `(studentId, opportunityId)`, and
seeds listings on first boot only.

### Email (Gmail)

1. Enable **2-Step Verification** on the Google account.
2. Create an **App Password** at https://myaccount.google.com/apppasswords
   (this is *not* your account password).
3. Put it in `.env` as `EMAIL_PASS` — never in code, never in git.

⚠️ Gmail may flag logins from unfamiliar IPs. Cloud Run egresses from Google
datacenter addresses, so expect a security email on the first send. Sending is
capped at roughly 500 messages/day. If it fails, the app degrades gracefully:
`send_otp_email` returns a status instead of raising, and the code is shown in
the UI.

## Deploying to Google Cloud Run

```bash
gcloud auth login
gcloud projects create YOUR_PROJECT --name=fitfest-hackathon
gcloud config set project YOUR_PROJECT
gcloud services enable run.googleapis.com firestore.googleapis.com cloudbuild.googleapis.com

gcloud firestore databases create --location=asia-south1

gcloud run deploy opportunityhub \
  --source . \
  --region asia-south1 \
  --allow-unauthenticated \
  --set-env-vars GCP_PROJECT=YOUR_PROJECT
```

Notes:

- `--allow-unauthenticated` is **required** — without it the jury gets a 403.
- `--source .` builds the image in Cloud Build, so **Docker is not required locally**.
- Deploy Cloud Run to the **same region** as Firestore (`asia-south1`).
- Firestore region is **permanent** once the database is created.
- Cloud Run requires a billing-enabled project.

### Demo-day backup (optional)

If Cloud Run is unreachable, expose the local app through a Cloudflare tunnel:

```powershell
winget install --id Cloudflare.cloudflared
.\run-local.ps1      # terminal 1
.\run-tunnel.ps1     # terminal 2
```

⚠️ The resulting `*.trycloudflare.com` URL is **ephemeral** — it changes on
restart and dies when the laptop closes. It is a fallback for demos, **not** a
valid submission URL (the brief requires a Cloud Run link).

## API

Interactive docs: **`/docs`** · schema: `/openapi.json`

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/healthz` | Liveness + listing count |
| GET | `/api/meta` | Categories, modes, tags, whether email is configured |
| POST | `/api/auth/signup` | Create account, send OTP |
| POST | `/api/auth/verify-otp` | Verify code, create profile, start session |
| POST | `/api/auth/resend-otp` | Resend the code |
| POST | `/api/auth/login` | Log in |
| POST | `/api/auth/logout` | Revoke the session |
| GET | `/api/auth/me` | Current session's user, or `{authenticated: false}` |
| POST | `/api/auth/forgot` | Email a reset link |
| POST | `/api/auth/reset` | Set a new password, revoking existing sessions |
| POST | `/api/auth/update-profile` | Session-guarded profile write |
| GET | `/api/opportunities` | Search + all filters |
| GET | `/api/opportunities/{id}` | Single listing, scored |
| GET | `/api/recommendations/{id}` | Top ranked matches |
| GET | `/api/skill-gap/{id}` | Missing skills ranked by impact |
| GET | `/api/bookmarks/{id}` | Saved listings |
| POST | `/api/bookmarks` | Toggle save |
| GET | `/api/dashboard/{id}` | Aggregated dashboard payload |

## Project structure

```
.
├── main.py               # FastAPI entrypoint, static mount
├── app/
│   ├── api.py            # HTTP routes (discovery + auth)
│   ├── auth.py           # PBKDF2 hashing, OTP, sessions, SMTP
│   ├── config.py         # env-driven config (.env loaded)
│   ├── models.py         # pydantic schemas
│   ├── recommend.py      # scoring + skill-gap engine
│   ├── seed_data.py      # 66 listings + rolling deadlines
│   └── store.py          # File / Memory / Mongo / Firestore + cache
├── tests/                # 8 suites, see above
├── static/
│   ├── index.html
│   ├── app.js            # SPA: router, views, rendering
│   ├── auth.js           # landing, signup, OTP, login, reset
│   └── styles.css
├── data/                 # runtime data for DB_BACKEND=file (gitignored)
├── requirements.txt
├── Dockerfile
├── .env.example          # copy to .env — .env itself is gitignored
├── fetch-cloudflared.ps1 # download the tunnel binary into tools/
├── run-local.ps1
├── run-tunnel.ps1        # app + public tunnel in one command
└── README.md
```

## Tests

```bash
.\.venv\Scripts\python.exe tests\test_eligibility.py   # parser unit tests
.\.venv\Scripts\python.exe tests\test_frontend.py      # static JS/HTML checks
.\.venv\Scripts\python.exe tests\test_search.py        # search whitespace + typing invariants
.\.venv\Scripts\python.exe tests\test_authz.py         # session guards
.\.venv\Scripts\python.exe tests\verify_served.py      # asserts on served assets
.\.venv\Scripts\python.exe tests\check_backends.py      # preflight config report
.\.venv\Scripts\python.exe tests\test_persistence.py   # restarts the app, checks data survives
.\.venv\Scripts\python.exe tests\test_public.py        # end-to-end over the tunnel URL
```

`test_persistence.py` kills and restarts the server, then asserts the profile,
bookmarks and session are still there. It is the test that would have caught
MemoryStore wiping every user on a tunnel restart.

`test_authz.py` confirms an anonymous write is refused, a bogus cookie is
refused, and a genuine session with one character changed is refused. Note it
uses a *fresh* cookie jar for each case — an earlier version shared one jar
across cases, so the "unauthenticated" write was actually authenticated and the
test wrongly reported a vulnerability.

`test_frontend.py` exists because of a bug that passed every API test: a render
function wrote to a field initialised to `null` and never assigned, so **all**
auth screens threw on load. It is invisible to HTTP testing — it only happens in
a browser. These checks are the cheapest substitute for having one: every id the
JS looks up must exist, no render path may write through an unassigned field,
and the script load order must hold.

`test_eligibility.py` covers year-of-study parsing including the cases that are
easy to get wrong: `"2nd-4th year"` (a range, so the minimum is 2), `"Final-year"`,
and `"Postgraduate students only"`.

## Scope & limitations

Honest about what an MVP does not do:

- **There is no demo or guest mode.** The app is fully auth-gated, so every
  visitor must sign up and verify an OTP to see anything. That makes the first
  impression look like a real product, but it also means a broken SMTP config
  locks everyone out — see the risk note below.
- **Listings are seeded, not admin-managed.** 66 real programmes with genuine
  apply links ship as seed data. There is no admin panel to post new listings.
- **The session cookie is not marked `secure`.** It should be once served over
  HTTPS; it is off so local HTTP testing works.
- **No application tracking.** Saving an opportunity does not track where you
  got to with the application.
- **Tailwind is loaded from a CDN**, so the Play CDN shows a console warning.
  Accepted deliberately: it buys a polished UI with no build step.
- Recommendations are rule-based, not learned from behaviour.
- Password reset iterates the reset collection to match tokens, which is fine
  at hackathon scale but would want a real index in production.

### ⚠️ Risk: email delivery is now a hard dependency

There is **no guest mode and no on-screen code**, so **SMTP must work or nobody
can sign in.** Before submitting, test the real flow end to end with an address
you control:

1. Send yourself a signup and confirm the mail arrives (check spam).
2. Confirm `emailSent: true` in the `POST /api/auth/signup` response.
3. Run `gcloud run logs read -s opportunityhub` — every code is logged there, so
   you can see whether delivery was attempted and what it returned.

If `emailSent` is `false`, the UI shows a clear warning. The usual causes are a
missing App Password, 2-Step Verification not enabled, or Gmail rate-limiting
logins from a new IP.

## Social

Tag **@gdg.fit.pune** and **@the_flora_institutes**.

`#FITFEST2026 #FITFESTHACKATHON #GDGFITPUNE #GDGPUNE #FLORAINSTITUTES #FLORAINSTITUTEOFTECHNOLOGY #HACKATHON2026 #PUNEHACKATHON #STUDENTHACKATHON #SOLOHACKATHON #TECHHACKATHON`
