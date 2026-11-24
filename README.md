# Clinical Research Follow-up Portal
 
AI-Powered Clinical Research and Patient Follow-up Management — EY AI & Data Capstone, Project 03.
 
A study coordination portal for **fictional** participants. Coordinators register participants, schedule
visits and record visit notes. A hosted AI model **only drafts** visit summaries; a qualified reviewer
approves or rejects every draft before it becomes a record.
 
> **Synthetic data only.** No real participants, names, contact details or medical information are used
> anywhere in this project. AI output is a draft and never a clinical decision.
 
---
 
## Contents
 
1. [Features](#features)
2. [Tech stack](#tech-stack)
3. [AI model](#ai-model)
4. [Architecture](#architecture)
5. [Repository structure](#repository-structure)
6. [Prerequisites](#prerequisites)
7. [Setup](#setup) — database, backend, frontend
8. [Demo accounts](#demo-accounts)
9. [Configuration](#configuration)
10. [Running the tests](#running-the-tests)
11. [API overview](#api-overview)
12. [Security and data protection](#security-and-data-protection)
13. [AI guardrails and failure handling](#ai-guardrails-and-failure-handling)
14. [Demo scenarios](#demo-scenarios)
15. [Evidence](#evidence)
16. [Known limitations](#known-limitations)
17. [Troubleshooting](#troubleshooting)
18. [Team](#team)
---
 
## Features
 
**Coordinator**
- Dashboard with active participants, due, overdue, completed and missed visits, and drafts awaiting review (counts calculated in SQL).
- Studies: list and create fictional studies.
- Participants: register with a backend-generated code (`P-0001`…) and an assigned reviewer; withdraw or re-activate consent. There is no delete: participants are only ever set to `WITHDRAWN`.
- Visit schedule: book, reschedule, complete, mark missed or cancel; double-booking and past dates are rejected.
- Visit notes: append-only source notes with documented follow-up actions.
- AI draft: generate a draft summary from the saved notes of a completed visit.
- Follow-ups: missed and overdue visits, open actions and reviewer-flagged summaries, ordered by date only.
- History: audit trail for every participant and visit.
**Reviewer**
- Review queue: drafts waiting for the logged-in reviewer only.
- Three-panel review: source notes (grey) · original AI draft (amber, never edited) · reviewer final (green).
- Approve with edited final text, or reject with a comment; optional follow-up flag. One decision per draft.
**Everyone**
- One login page (email and password); the backend decides the home page by role.
- Each user sees **only their own** participants and records; anything else returns *not found*.
---
 
## Tech stack
 
| Layer | Technology |
|---|---|
| Frontend | React 19, Vite, React Router, TanStack Query, lucide-react, plain CSS |
| Backend | Python 3.12+, FastAPI, SQLAlchemy 2, Pydantic 2, PyJWT, bcrypt |
| Database | PostgreSQL 16 |
| AI | Microsoft Foundry (Azure OpenAI) via the `openai` Python SDK |
| Tests | pytest against a real PostgreSQL test database |
 
---
 
## AI model
 
| Item | Value |
|---|---|
| Option | **B — existing Azure deployment (Microsoft Foundry)** |
| Deployment name | `gpt-5.4-mini` |
| Model | `gpt-5.4-mini-2026-03-17` |
| API | Azure OpenAI v1 endpoint, structured JSON output |
 
**Why this model:** a general-purpose chat model was chosen over a medical one because the task is a
tightly constrained summary of the note it is given (no medical reasoning), and it follows instructions and
produces reliable JSON while working with Foundry's content filters and Prompt Shields.
 
---
 
## Architecture
 
```text
 Browser (React, :5173)
        │  HTTPS/JSON + Bearer token
        ▼
 FastAPI backend (:8000)
   routers → services → repositories
   │   auth: JWT, role checks, ownership filter on every query
   │   audit: every change recorded (codes and statuses only)
   │
   ├──► PostgreSQL (clinical_followup)
   │      studies · staff_members · users · participants · visits
   │      visit_notes · ai_summaries · summary_reviews · audit_events
   │
   └──► Microsoft Foundry (gpt-5.4-mini)
          only called to DRAFT a summary from saved notes;
          every reply is validated before it is stored
```
 
Source facts (`visit_notes`), the AI proposal (`ai_summaries`) and the human decision
(`summary_reviews`) are stored in separate tables and never overwritten, so they can always be compared.
 
---
 
## Repository structure
 
```text
AI-Clinical-Research-Followup/
├── README.md
├── database/
│   ├── schema.sql          # creates the 9 tables, triggers and indexes
│   ├── seed.sql            # synthetic demo data and login accounts
│   └── queries.sql         # required SQL demonstrations + dashboard and audit checks
├── backend/
│   ├── .env.example        # configuration template (copy to .env)
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── app/
│   │   ├── main.py
│   │   ├── core/           # config, logging, errors, auth
│   │   ├── db/             # session, models
│   │   ├── ai/             # prompt, Azure client, validator
│   │   ├── routers/        # auth, staff, studies, participants, audit,
│   │   │                   # visits, notes, reports, summaries
│   │   ├── schemas/
│   │   ├── services/
│   │   └── repositories/
│   ├── scripts/
│   │   └── test_azure.py   # checks the Foundry connection
│   └── tests/
├── frontend/
│   ├── .env                # VITE_API_BASE_URL (not committed)
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── api/client.js   # every call to the backend
│       ├── components/     # common (auth, layout, ui) and review panels
│       └── pages/          # login, coordinator and reviewer screens
└── docs/
    ├── screenshots/
    ├── test-results-all.txt
    └── query-results.txt
```
 
---
 
## Prerequisites
 
| Tool | Version | Check |
|---|---|---|
| PostgreSQL | 16 | `psql --version` |
| Python | 3.12 or newer | `python --version` |
| Node.js | 20.19 or newer (22 recommended) | `node -v` |
| Git | any recent | `git --version` |
 
Run all commands in **PowerShell** from the **repository root** unless a step says otherwise.
 
---
 
## Setup
 
### 1. Database
 
**1.1 Make `psql` available**
 
```powershell
psql --version
```
 
If it says *psql is not recognized*, add PostgreSQL to the path (change `16` to your version):
 
```powershell
$env:Path += ";C:\Program Files\PostgreSQL\16\bin"
```
 
**1.2 (Optional) Save the password for this terminal session**
 
```powershell
$env:PGPASSWORD = "your_postgres_password"
```
 
Without this, each command asks for the password (nothing is shown while typing — that is normal).
 
**1.3 Create the app database and the test database (first time only)**
 
```powershell
psql -U postgres -c "CREATE DATABASE clinical_followup;"
psql -U postgres -c "CREATE DATABASE clinical_followup_test;"
```
 
If a database already exists, continue.
 
**1.4 Create the tables and load the demo data**
 
```powershell
psql -U postgres -d clinical_followup -f database/schema.sql
psql -U postgres -d clinical_followup -f database/seed.sql
```
 
`NOTICE ... does not exist, skipping` on the first run is expected. `seed.sql` ends with `COMMIT`.
**Warning:** `schema.sql` deletes all existing data in these tables.
 
**1.5 Check it worked**
 
```powershell
psql -U postgres -d clinical_followup -c "\dt"
psql -U postgres -d clinical_followup -c "SELECT (SELECT COUNT(*) FROM participants) AS participants, (SELECT COUNT(*) FROM visits) AS visits, (SELECT COUNT(*) FROM visit_notes) AS notes, (SELECT COUNT(*) FROM users) AS logins;"
```
 
Expected: 9 tables, and `12 | 20 | 12 | 4`.
 
**1.6 Run the demo queries and save the results**
 
```powershell
psql -U postgres -d clinical_followup -f database/queries.sql -o docs/query-results.txt
```
 
The test database needs no tables: the tests rebuild it from `schema.sql` and `seed.sql` before every test.
 
### 2. Backend
 
```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```
 
Edit `backend\.env` (see [Configuration](#configuration)). At minimum set `DATABASE_URL` and `JWT_SECRET`.
Generate a secret with:
 
```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```
 
Start the API:
 
```powershell
uvicorn app.main:app --reload
```
 
- Health check: http://localhost:8000/api/health → `"database": "up"`
- Interactive API docs (Swagger): http://localhost:8000/docs
Optional — check the Foundry connection:
 
```powershell
python -m scripts.test_azure
```
 
If PowerShell blocks `Activate.ps1`, run once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
 
### 3. Frontend
 
In a **second** terminal:
 
```powershell
cd frontend
npm install
Set-Content -Path .env -Value "VITE_API_BASE_URL=http://localhost:8000"
npm run dev
```
 
Open http://localhost:5173. Keep both terminals running.
 
### Reset to a clean demo state
 
```powershell
psql -U postgres -d clinical_followup -f database/schema.sql
psql -U postgres -d clinical_followup -f database/seed.sql
```
 
---
 
## Demo accounts
 
All accounts are fictional. Demo password: `Demo@2026` (stored only as a bcrypt hash).
 
| Email | Role | Owns / reviews | Lands on |
|---|---|---|---|
| coord.01@example.org | Coordinator | Participants 1–6 (STD-SLEEP-01) | Dashboard |
| coord.02@example.org | Coordinator | Participants 7–12 (STD-MOB-REG) | Dashboard |
| rev.01@example.org | Reviewer | Participants 1–6 | Review queue |
| rev.02@example.org | Reviewer | Participants 7–12 | Review queue |
 
Change the demo passwords before any use outside a local demo.
 
---
 
## Configuration
 
All settings come from environment variables in `backend\.env` (see `backend\.env.example`).
**Never commit `.env`** — it is listed in `.gitignore`.
 
| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | yes | — | `postgresql+psycopg://postgres:<password>@localhost:5432/clinical_followup` (write `@` in a password as `%40`) |
| `JWT_SECRET` | yes | — | Signs login tokens; at least 32 random characters |
| `JWT_EXPIRE_MINUTES` | no | `480` | Login lifetime (8 hours) |
| `CORS_ORIGINS` | no | `http://localhost:5173` | Frontend address(es) allowed to call the API |
| `LOG_LEVEL` | no | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR` |
| `DUE_WINDOW_DAYS` | no | `7` | A scheduled visit within this many days is *Due* |
| `AI_ENABLED` | no | `true` | `false` switches drafting off (returns *Draft unavailable*) |
| `AZURE_OPENAI_ENDPOINT` | for AI | — | e.g. `https://<resource>.openai.azure.com/openai/v1` |
| `AZURE_OPENAI_DEPLOYMENT` | for AI | — | Deployment name in Foundry (`gpt-5.4-mini`) |
| `AZURE_OPENAI_API_KEY` | for AI | — | Key from the Foundry resource — keep private |
| `AZURE_OPENAI_API_VERSION` | no | empty | Not needed for the v1 endpoint |
| `AI_TIMEOUT_SECONDS` | no | `45` | Wait before giving up on the model |
| `AI_MAX_RETRIES` | no | `1` | Retries after a temporary AI error |
| `AI_MAX_COMPLETION_TOKENS` | no | `4000` | Upper limit for the model reply |
| `TEST_DATABASE_URL` | tests only | — | Throwaway database for pytest (wiped on every test) |
 
Frontend: `frontend\.env` contains only `VITE_API_BASE_URL=http://localhost:8000`.
 
---
 
## Running the tests
 
The tests run against a real PostgreSQL database (`clinical_followup_test`), rebuilt from
`database/schema.sql` and `database/seed.sql` before every test. The AI model is replaced by a test
double, so no Azure key is needed.
 
```powershell
cd backend
.venv\Scripts\Activate.ps1
$env:TEST_DATABASE_URL = "postgresql+psycopg://postgres:<password>@localhost:5432/clinical_followup_test"
python -m pytest
```
 
Save evidence:
 
```powershell
python -m pytest -v > ..\docs\test-results-all.txt
```
 
| Test file | Covers |
|---|---|
| `test_auth.py` | Login, role redirect, generic errors, inactive staff, 401 / 403 |
| `test_participants.py` | Studies, participant registration and codes, ownership segregation, audit |
| `test_consent.py` | Consent withdrawal and re-activation rules |
| `test_visits.py` | Scheduling rules, status transitions, notes, Due/Overdue, dashboard counts |
| `test_ai.py`, `test_review.py` | Draft generation, validation guardrails, failures, review decisions |
 
**Never** point `TEST_DATABASE_URL` at `clinical_followup` — the tests delete its data.
 
---
 
## API overview
 
Full, interactive documentation: http://localhost:8000/docs. Every endpoint except login and health
needs `Authorization: Bearer <token>`. Records outside the caller's scope return `404`.
 
| Method | Path | Role | Purpose |
|---|---|---|---|
| POST | `/api/auth/login` | public | Email + password → token, role, home page |
| GET | `/api/auth/me` | any | Current user |
| GET | `/api/health` | public | API and database status |
| GET | `/api/staff` | coordinator | Active reviewers (for the reviewer dropdown) |
| GET / POST | `/api/studies` | any / coordinator | List / create studies |
| GET / POST | `/api/participants` | any / coordinator | Own participants / register one |
| GET | `/api/participants/{id}` | any | Profile with visits |
| PATCH | `/api/participants/{id}/consent` | coordinator | Change consent |
| GET | `/api/audit-events` | any | History of one record |
| GET / POST | `/api/visits` | any / coordinator | List (filters in SQL) / schedule |
| GET / PATCH | `/api/visits/{id}` | any / coordinator | Detail / reschedule or change status |
| GET / POST | `/api/visits/{id}/notes` | any / coordinator | Source notes (append-only) |
| GET | `/api/reports/follow-ups` | any | Dashboard counts |
| GET | `/api/reports/follow-up-items` | any | Missed/overdue visits, open actions, flagged summaries |
| POST | `/api/visits/{id}/draft-summary` | coordinator | Generate an AI draft |
| GET | `/api/visits/{id}/summaries` | any | Drafts for a visit |
| GET | `/api/review-queue` | reviewer | Drafts awaiting the reviewer |
| GET | `/api/summaries/{id}` | any | Draft, source notes and decision |
| PATCH | `/api/summaries/{id}/review` | reviewer | Approve or reject |
 
---
 
## Security and data protection
 
- **Authentication:** email + password checked with bcrypt; a signed JWT holds only the staff code. The role is re-read from the database on every request, so a deactivated account loses access immediately.
- **Authorisation:** role checks on every route (403) and an ownership filter on every query — coordinators see only participants they own, reviewers only those assigned to them (404 otherwise).
- **Minimal data:** participants are identified by study codes only; no names, dates of birth or contact details exist in the schema.
- **No deletion of research records:** participants are withdrawn, never deleted; notes, AI drafts and audit events are append-only (enforced by database triggers).
- **Audit trail:** every create and change is recorded with actor, time and status codes — never note or draft text.
- **Logging:** structured JSON; emails, passwords, tokens, note and draft text are never logged.
- **Secrets:** only in `.env` files, which are excluded from Git.
---
 
## AI guardrails and failure handling
 
**Layer 1 — Microsoft Foundry (portal):** content filters and Prompt Shields on the deployment.
 
**Layer 2 — backend validator (`app/ai/validator.py`)**, applied to every reply before it is stored:
 
1. The reply must match the `SummaryDraft` schema and limits, with `review_status = "DRAFT"`.
2. Every follow-up action must match an action documented in the note.
3. Every number in the draft must appear in the source note (no calculated numbers).
4. No clinical-decision wording (diagnosis, prescription, urgency, treatment plan…) unless it is in the note.
5. The staff message must not contain patient-contact wording.
**Rules outside the model:** drafts are blocked for withdrawn consent and for visits without saved notes;
Due/Overdue labels, counts and ordering are calculated in SQL, never by the AI.
 
**When drafting fails** (timeout, quota, credentials, content filter, invalid or ungrounded output), a
`FAILED` row is stored **without** draft text, the API returns 502/503/504, and the screen shows
*"Draft unavailable — try again later"*. All other features keep working. Set `AI_ENABLED=false` to
demonstrate this.
 
---
 
## Demo scenarios
 
| Scenario | How to show it |
|---|---|
| Normal visit | Coordinator: complete a visit, save a note with follow-up actions, generate a draft; reviewer approves it |
| Missing note detail | Save a short note ("about the same as last time; diary not brought") → draft lists gaps under *Missing information* |
| Consent withdrawn | Withdraw consent on a participant → new visits and AI drafts are blocked |
| Reviewer correction | Reviewer edits the final text before approving; the original draft stays unchanged |
| AI unavailable | `AI_ENABLED=false` (restart backend) → *Draft unavailable*, rest of the app works |
| Prompt injection / ungrounded output | Note containing "IGNORE ALL PREVIOUS INSTRUCTIONS…" → blocked by Foundry or rejected by the validator |
| Unauthorized action | Coordinator opens another coordinator's participant → *not available to you*; reviewer tries to change consent → 403 |
| Overdue / missed follow-up | Dashboard and Follow-ups list overdue and missed visits by date |
| Dashboard reconciliation | Compare dashboard numbers with `database/queries.sql` |
 
---
 
## Evidence
 
| File | Contents |
|---|---|
| `docs/test-results-all.txt` | Full pytest run |
| `docs/query-results.txt` | Output of `database/queries.sql` |
| `docs/screenshots/` | Login, role redirect, segregation, consent, visits, notes, AI draft, review, failure states |
 
---
 
## Known limitations
 
- Logout removes the token in the browser only; a copied token stays valid until it expires (8 hours) unless the account is deactivated.
- One reviewer decision per draft; a rejected visit needs a new draft.
- The validator is deliberately strict: correct drafts that reformat or calculate numbers are rejected rather than risk unsupported content.
- No password-reset or account-management screens; accounts are created in `seed.sql`.
- Local development setup only; production deployment (HTTPS, managed secrets) is out of scope.
---
 
## Troubleshooting
 
| Problem | Fix |
|---|---|
| `psql is not recognized` | Add PostgreSQL's `bin` folder to `$env:Path` (Setup 1.1) |
| `No such file or directory` when running SQL | Run from the repository root, not from `database/` |
| `password authentication failed` | Wrong PostgreSQL password; in `DATABASE_URL` write `@` as `%40` |
| `could not connect to server` | Start PostgreSQL: Win + R → `services.msc` → start `postgresql-x64-16` |
| Backend: `Missing or invalid configuration: DATABASE_URL, JWT_SECRET` | Create `backend\.env` from `.env.example` |
| `ModuleNotFoundError` (e.g. `openai`) | Activate `.venv`, then `python -m pip install -r requirements.txt` |
| pytest: `Set TEST_DATABASE_URL…` | Set `$env:TEST_DATABASE_URL` in the same terminal |
| Login says *Email or password is incorrect* with `Demo@2026` | Re-run `seed.sql`; check `DATABASE_URL` points to `clinical_followup`, not the test database |
| Browser shows *Unable to reach the server* | Backend not running on port 8000 |
| CORS error in the browser console | Set `CORS_ORIGINS=http://localhost:5173` and restart the backend |
| *Draft unavailable* every time | Check `AI_ENABLED=true` and the Azure settings, restart the backend, run `python -m scripts.test_azure` |
| `Port 5173 is already in use` | Close the old `npm run dev` terminal |
 
---
 
## Team
 
| Member | Area |
|---|---|
| Person 1 — Rajnish Maurya | Platform, authentication, participant registry, consent, audit, frontend |
| Person 2 — Deepika Kanchi | Visits, notes, dashboard and follow-up reports, SQL queries, workflow |
| Person 3 — Jahnavi Krishnan | AI drafting, Foundry deployment and guardrails, architectural diagram |
 
EY AI & Data Training — Capstone Project 03.
 