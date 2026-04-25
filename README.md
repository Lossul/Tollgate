# Tollgate

Scans your Gmail for subscription charges and free trials so you never get surprised by a recurring bill. Connect once, see everything you're paying for.

## What it does

- Connects to Gmail with read-only access via Google OAuth
- Scans up to 200 emails for subscription renewals, billing receipts, and free trial notices
- Extracts service name, billing amount, frequency, and renewal/trial end date
- Shows a dashboard sorted by what's expiring or renewing soonest
- Uses Claude AI for parsing when available, falls back to regex heuristics

## Stack

| Layer | Tech |
|---|---|
| API | Python, FastAPI, uvicorn |
| Web | Next.js 14, TypeScript, App Router |
| Auth | Google OAuth2, JWT session cookies |
| Storage | Local JSON files (dev) or Supabase (prod) |
| Parsing | Claude API (`claude-3-5-sonnet`) + regex fallback |

## Getting started

### 1. Google OAuth credentials

Create a project in [Google Cloud Console](https://console.cloud.google.com), enable the **Gmail API**, and create an OAuth 2.0 client ID. Set the authorized redirect URI to `http://localhost:8000/auth/google/callback`.

### 2. API (`apps/api`)

```bash
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill in .env (see below)
uvicorn app.main:app --reload
```

**Required env vars:**

```env
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback
WEB_ORIGIN=http://localhost:3000
APP_JWT_SECRET=change-me
```

**Optional:**

```env
CLAUDE_API_KEY=        # enables AI-powered parsing
SUPABASE_URL=          # use Supabase instead of local JSON
SUPABASE_SERVICE_ROLE_KEY=
```

### 3. Web (`apps/web`)

```bash
cd apps/web
npm install
cp .env.example .env.local
# set NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm run dev
```

Open [http://localhost:3000](http://localhost:3000), sign in with Google, and run a scan.

## Project structure

```
apps/
  api/
    app/
      main.py          # FastAPI routes
      auth.py          # JWT session + OAuth state tokens
      gmail.py         # Gmail REST API client
      google_oauth.py  # Google OAuth2 helpers
      trial_parser.py  # Email parser (Claude + heuristic fallback)
      trial_utils.py   # Days remaining, status helpers
      storage.py       # Local JSON / Supabase adapter
      config.py        # Settings from env vars
    data/              # Local JSON storage (gitignored in prod)
  web/
    app/
      page.tsx         # Landing page
      dashboard/       # Subscription dashboard
      scan/            # Trigger inbox scan
```

## Supabase setup (optional)

Create two tables:

```sql
create table users (
  id text primary key,
  email text,
  google_tokens jsonb
);

create table trials (
  id uuid primary key,
  user_id text references users(id),
  service_name text,
  subscription_type text,
  billing_amount text,
  billing_frequency text,
  start_date text,
  end_date text,
  cancel_url text,
  status text,
  source text,
  email_message_id text,
  created_at text
);
```
