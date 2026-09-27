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
| Database | Firestore **or** MongoDB (pluggable) | One repository interface, three backends |
| Frontend | Vanilla JS SPA + Tailwind CDN | **No build step, no bundler, no `npm install`** |
| Auth | Email OTP + password reset | PBKDF2 hashing, server-side sessions |
| Hosting | Docker → Google Cloud Run | Single container, single service |

### Architecture

```
Browser (SPA)
   │  same-origin fetch() — no CORS anywhere
   ▼
Cloud Run ── FastAPI (uvicorn, 0.0.0.0:$PORT)
               │
               └── BaseStore  ← caching layer (60s TTL)
                      ├── MemoryStore     (local dev, zero credentials)
                      ├── MongoStore      (MONGODB_URI set)
                      └── FirestoreStore  (GCP_PROJECT set, ADC)
```

The **repository pattern** is the key design decision: the same API code runs
locally with no cloud setup and in production against either database, with
zero code changes — selected purely by environment variables.

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
- **Password reset**: single-use, expiring token. Resetting revokes every
  active session for that account, since old tokens were issued against the
  previous password.
- **Anti-enumeration**: `/auth/login` and `/auth/forgot` return identical
  responses whether or not an email is registered, so neither endpoint can be
  used to discover which addresses have accounts.
- If `EMAIL_USER`/`EMAIL_PASS` are unset, the OTP is returned in the response
  as `devCode` and shown in the UI, so the signup flow still completes on a
  machine with no mail credentials.

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

```bash
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

Open http://localhost:8080 — the landing page loads first. Create an account and
enter the OTP shown on screen (it is emailed only once SMTP is configured).

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
│   └── store.py          # Memory / Mongo / Firestore + cache
├── tests/
│   └── test_eligibility.py   # parser unit tests
├── static/
│   ├── index.html
│   ├── app.js            # SPA: router, views, rendering
│   ├── auth.js           # landing, signup, OTP, login, reset
│   └── styles.css
├── requirements.txt
├── Dockerfile
├── .env.example          # copy to .env — .env itself is gitignored
├── run-local.ps1
├── run-tunnel.ps1
└── README.md
```

## Tests

```bash
.\.venv\Scripts\python.exe tests\test_eligibility.py   # parser unit tests
.\.venv\Scripts\python.exe tests\test_frontend.py      # static JS/HTML checks
.\.venv\Scripts\python.exe tests\verify_served.py      # asserts on served assets (server must be up)
```

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

### ⚠️ Risk introduced by removing guest access

Because there is no guest mode, **a visitor can only get in if they can read the
email the OTP was sent to.** Two failure cases to test before you submit:

1. **SMTP not configured** — the code appears in the UI instead. Verified working.
2. **SMTP configured but sending fails** (rate limit, wrong app password,
   account flagged) — the code still appears in the UI, because `send_otp_email`
   returns a status instead of raising. Verified working.
3. **SMTP working, but the visitor types an address they cannot read** (or the
   mail is filtered) — they are stuck. Nothing in the app can recover from this
   except "Resend code". Test the real flow end-to-end with a genuine address
   before demoing.

The cheapest insurance: keep `EMAIL_USER` blank on the deployed instance, so
verification always falls back to the on-screen code.

## Social

Tag **@gdg.fit.pune** and **@the_flora_institutes**.

`#FITFEST2026 #FITFESTHACKATHON #GDGFITPUNE #GDGPUNE #FLORAINSTITUTES #FLORAINSTITUTEOFTECHNOLOGY #HACKATHON2026 #PUNEHACKATHON #STUDENTHACKATHON #SOLOHACKATHON #TECHHACKATHON`
