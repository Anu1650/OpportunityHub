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
| 🔎 Search & Filtering | Full-text search, category, mode, closing-soon, min-match, show-closed |
| 🏆 Hackathons & Competitions | 7 category types with per-category icons and colour coding |
| 💼 Internships | Filterable, deadline-tracked, external apply links |
| 📚 Courses & Certifications | 60+ real programmes, eligibility shown per listing |
| 🎯 Skill/Interest Recommendations | Weighted scoring with visible reason breakdown |
| 🔖 Save/Bookmark | Toggle save, dedicated Saved view sorted by deadline |
| 📊 Student Dashboard | Open count, strong matches, closing this week, category breakdown |
| 🔗 Details & External Links | Modal with full description, eligibility, tags, direct apply link |
| ⭐ **Skill-gap analysis** | "Learn C++ → unlocks 11 open opportunities" |

Extras beyond the brief: **demo mode** (one-click sample profile), **match
explanations**, **deadline countdowns**, and a browsable **OpenAPI docs** at `/docs`.

## How the matching works

Deliberately explainable rather than ML — a judge can verify the arithmetic.

```
points = 3 × (matched skills)
       + 2 × (matched interests in tags)
       + 1 × (interest phrase found in the description, max 3)
       + 2 × (listing is in a category you follow)

score  = min(100, points / 15 × 100)      # 15 points = 100% match
```

Every score ships with the terms that produced it, e.g.
*"87% — Matches your skills: JavaScript, Python, React · In a category you follow (hackathon)"*.

**Skill-gap analysis** inverts the same data: it counts which unlisted skills
appear across the most open listings, so it can tell you what to learn next.

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Backend | Python 3.12 + FastAPI | Auto-generated OpenAPI docs at `/docs` |
| Database | Firestore (Google Cloud) | No DB server, no connection string, survives Cloud Run restarts |
| Frontend | Vanilla JS SPA + Tailwind CDN | **No build step, no bundler, no `npm install`** |
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
                      └── FirestoreStore  (production, Application Default Credentials)
```

The **repository pattern** is the key design decision: the same API code runs
locally with no cloud setup and in production against Firestore, with zero code
changes — selected purely by whether `GCP_PROJECT` is set.

### Two engineering notes worth knowing

1. **Why not SQLite?** Cloud Run containers have an *ephemeral* filesystem. A
   SQLite file or JSON store would be wiped on every instance restart and scale
   event — a judge opening the link hours later would see an empty app. Firestore
   is external and always there.
2. **Why the 60-second cache?** Firestore's free tier is 50,000 reads/day. Each
   search reads ~66 documents, so 60 judges browsing would approach the ceiling
   and the app would throttle *late in the day*, when the most eyes are on it.
   Listings are read-only reference data, so caching them drops read volume to
   near zero.

## Running locally

```bash
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

Open http://localhost:8080 — click **Load demo profile**.

No cloud account or credentials needed: with `GCP_PROJECT` unset the app uses
the in-memory store and re-seeds on every boot.

> Run **one** uvicorn worker locally. The in-memory store is per-process, so
> multiple workers would each hold a separate copy and lose bookmarks between
> requests. The app refuses to start if you try — set `--workers 1`.

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
| GET | `/api/meta` | Categories, modes, all tags |
| POST | `/api/students` | Create/update profile (keyed by email) |
| GET | `/api/students/{id}` | Fetch profile |
| POST | `/api/demo-profile` | One-click sample profile |
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
│   ├── api.py            # HTTP routes
│   ├── config.py         # env-driven config
│   ├── models.py         # pydantic schemas
│   ├── recommend.py      # scoring + skill-gap engine
│   ├── seed_data.py      # 66 listings + rolling deadlines
│   └── store.py          # MemoryStore / FirestoreStore + cache
├── static/
│   ├── index.html
│   ├── app.js            # SPA: router, views, rendering
│   └── styles.css
├── requirements.txt
├── Dockerfile
├── run-local.ps1
├── run-tunnel.ps1
└── README.md
```

## Scope & limitations

Honest about what an MVP does not do:

- **No password authentication.** Identity is the email you type; the profile
  ID is kept in `localStorage`. Real auth was out of scope for a 4-hour solo build.
- **Listings are seeded, not admin-managed.** 66 real programmes with genuine
  apply links ship as seed data. There is no admin panel to post new listings.
- **No application tracking.** Saving an opportunity does not track where you
  got to with the application.
- **Tailwind is loaded from a CDN**, so the Play CDN shows a console warning.
  Accepted deliberately: it buys a polished UI with no build step.
- Recommendations are rule-based, not learned from behaviour.

## Social

Tag **@gdg.fit.pune** and **@the_flora_institutes**.

`#FITFEST2026 #FITFESTHACKATHON #GDGFITPUNE #GDGPUNE #FLORAINSTITUTES #FLORAINSTITUTEOFTECHNOLOGY #HACKATHON2026 #PUNEHACKATHON #STUDENTHACKATHON #SOLOHACKATHON #TECHHACKATHON`
