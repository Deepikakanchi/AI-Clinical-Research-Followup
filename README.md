# Database Setup — Step by Step

PostgreSQL database for the Clinical Research Follow-up Portal (synthetic data only).
Run every command in **PowerShell** from the **repository root** (the folder that contains `database/`).

---

## Step 1 — Go to the project folder

```powershell
cd C:\Users\<your-user>\AI-Clinical-Research-Followup
```

## Step 2 — Make `psql` available

```powershell
psql --version
```

If it says *psql is not recognized*, run this (change `16` to your PostgreSQL version), then check again:

```powershell
$env:Path += ";C:\Program Files\PostgreSQL\16\bin"
psql --version
```

## Step 3 — (Optional) Save your password for this terminal session

```powershell
$env:PGPASSWORD = "your_postgres_password"
```

Without this, each command asks for the password (nothing shows while you type — that is normal).

## Step 4 — Create the database (first time only)

```powershell
psql -U postgres -c "CREATE DATABASE clinical_followup;"
```

If it says the database already exists, continue to Step 5.

## Step 5 — Create the 8 tables

```powershell
psql -U postgres -d clinical_followup -f database/schema.sql
```

`NOTICE ... does not exist, skipping` lines on the first run are expected.
**Warning:** this deletes all existing data in these tables.

## Step 6 — Load the demo data

```powershell
psql -U postgres -d clinical_followup -f database/seed.sql
```

Ends with `COMMIT`. Safe to run more than once.

## Step 7 — Check it worked

```powershell
psql -U postgres -d clinical_followup -c "\dt"
```

Shows 8 tables. Then:

```powershell
psql -U postgres -d clinical_followup -c "SELECT (SELECT COUNT(*) FROM participants) AS participants, (SELECT COUNT(*) FROM visits) AS visits, (SELECT COUNT(*) FROM visit_notes) AS notes;"
```

Expected: `12 | 20 | 12`

## Step 8 — Run the demo queries and save the results

```powershell
psql -U postgres -d clinical_followup -f database/queries.sql -o docs/query-results.txt
```

## Step 9 — Connect the backend

Add this line to the root `.env` file (never commit `.env`):

```
DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/clinical_followup
```

---

## Reset to a clean demo state

```powershell
psql -U postgres -d clinical_followup -f database/schema.sql
psql -U postgres -d clinical_followup -f database/seed.sql
```

---

## If something goes wrong

| Error | Fix |
|---|---|
| `psql is not recognized` | Run the `$env:Path` command in Step 2 |
| `No such file or directory` | You are inside `database/` — run `cd ..` and try again |
| `password authentication failed` | Wrong password — use the one set when PostgreSQL was installed |
| `fe_sendauth: no password supplied` | Run the command again and type the password, or use Step 3 |
| `could not connect to server` | Start PostgreSQL: Win + R → `services.msc` → start `postgresql-x64-16` |
| `database "clinical_followup" does not exist` | Run Step 4 first |

---

## Files

| File | Purpose |
|---|---|
| `schema.sql` | Creates the 8 tables |
| `seed.sql` | Loads synthetic demo data (2 studies, 12 participants, 20 visits, 12 notes, 7 AI drafts) |
| `queries.sql` | The 3 required SQL demonstrations plus dashboard and audit checks |
