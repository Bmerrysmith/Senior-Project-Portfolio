# Rag-Email-Agent

A retrieval-augmented email assistant for Outlook. Once a day it reads a
mailbox, summarizes the messages that arrived, and sends back a single
digest with everything grouped by urgency.

Every message from the previous day is pulled through the Microsoft Graph
API, stripped of quoted replies and signatures, split into chunks, embedded,
and stored in Postgres with pgvector. To summarize a message the agent
retrieves related context — earlier mail from the same sender, and
semantically similar messages from the archive — and hands that, together
with the message itself, to an LLM that writes a short summary and assigns
an urgency of low, medium, high, or urgent. The day's summaries are grouped
by urgency into an HTML digest and sent to the account's own inbox. Mail is
only ever sent to the account it came from; the Graph scopes are limited to
`Mail.Read` and `Mail.Send`.

The agent handles more than one mailbox. Accounts are added through a
Microsoft OAuth flow gated by an allowlist, and each account's refresh token
is encrypted before it is stored. A per-account note can be set in the
database to tell the model what that mailbox treats as important — for
instance, that a job-search account should rank recruiter mail highly.

In the deployed setup the whole pipeline runs on AWS Lambda, triggered once
a day by EventBridge Scheduler at 7 a.m. Eastern. A log table records each
send, so a retry after a partial failure does not produce a second digest.

## Running your own instance

The project is built around a particular set of hosted services. Standing up
your own copy means creating your own accounts for each of them; nothing
here depends on my deployment, and once it is configured it runs without any
involvement from me.

### What you need

- **An Azure app registration** for Microsoft Graph. Register an app under
  Microsoft Entra ID → App registrations, allow personal Microsoft accounts,
  add `http://localhost:5000/auth/callback` as a redirect URI, and request
  delegated `Mail.Read` and `Mail.Send` permissions. The application (client)
  ID goes in your `.env`.
- **An OpenAI API key**, used for embeddings (`text-embedding-3-small`) and
  summarization (`gpt-5-mini`). Usage is minor — cents a day for a couple of
  mailboxes.
- **A Postgres database with pgvector.** Production uses a Supabase project
  reached through its session-mode pooler, but the connection string can
  point at any Postgres 15 or later with the `vector` extension, including a
  local one started with `docker compose up`. Apply `db/init/001_schema.sql`
  once to create the tables.
- **An AWS account.** Three values are read from AWS Secrets Manager at
  startup rather than from the environment: the Fernet key that encrypts
  stored refresh tokens, the database connection string, and the OpenAI key.
  The region and secret names are set at the top of `auth/secrets.py`. That
  file is the only place the code touches Secrets Manager, so if you would
  rather not use AWS it is short enough to repoint at environment variables.

### Configuration

Copy `.env.example` to `.env` and set `CLIENT_ID`, a random
`FLASK_SECRET_KEY`, and the authority, redirect, and scope values if they
differ from the defaults. The remaining entries — chunk size, retrieval
limits, model names — have working defaults and only need to be set to
change them.

Create the three secrets in Secrets Manager, each a JSON object with a
single key:

```
rag-email-agent/token-encryption-key        {"TOKEN_ENCRYPTION_KEY": "<fernet key>"}
rag-email-agent/supabase-connection-string  {"SUPABASE_CONNECTION_STRING": "postgresql://..."}
rag-email-agent/openai-api-key              {"OPENAI_API_KEY": "sk-..."}
```

Generate the Fernet key with:

```
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Your local AWS credentials (`aws configure`) need permission to read these
secrets.

### Python environment

```
python -m venv .venv
source .venv/Scripts/activate      # PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Authorizing a mailbox

There is no admin interface. Add each address to the allowlist directly:

```sql
INSERT INTO approved_users (email) VALUES ('you@outlook.com');
```

Then start the Flask app and sign in:

```
python app.py
```

Open `http://localhost:5000/auth/login`, authenticate with the mailbox you
allowlisted, and grant consent. The callback checks the address against
`approved_users` and, on success, stores that account's encrypted refresh
token. An address that is not on the list is rejected and nothing is saved.
Repeat for each mailbox.

### Running the pipeline

The three stages run in order, and each one processes every authorized
account:

```
python -m ingest     # fetch, clean, chunk, embed
python -m triage     # summarize and grade the previous day's mail
python -m digest     # send each account's digest
```

`ingest` is safe to run repeatedly. `triage` works on the previous calendar
day in US Eastern time. `digest` records each send in `digest_log` and will
not send a day's digest twice. A failure on one account, such as a revoked
grant, is logged and skipped without affecting the others.

Running these on a local scheduler — cron, or Task Scheduler on Windows — is
enough to use the agent day to day.

### Deploying to AWS

`deploy/` holds a container build and a runbook for the Lambda and
EventBridge Scheduler setup. `deploy/deploy.md` lists the commands to create
the image repository, the function, its execution role, and the daily
schedule, along with what to run to push later code changes.

## Repository layout

```
app.py                  Flask app, used only for the OAuth sign-in flow
lambda_handler.py       AWS Lambda entry point; runs ingest, triage, digest in order
config.py               configuration, from the environment and Secrets Manager
auth/
  accounts.py           accounts / approved_users tables, token acquisition
  crypto.py             Fernet encryption for stored refresh tokens
  msal_client.py        MSAL application setup
  routes.py             /auth/login and /auth/callback, allowlist-gated
  secrets.py            reads secrets from AWS Secrets Manager
graph/
  client.py             Microsoft Graph calls: list messages, fetch bodies, send mail
ingest/
  cleaning.py           HTML and quoted-reply/signature stripping
  chunking.py           character-based chunking
  embeddings.py         OpenAI embedding requests
  db.py                 database connection and write helpers
  __main__.py           ingestion run (python -m ingest)
triage/
  time_window.py        previous-day Eastern window
  db.py                 retrieval queries and summary writes
  llm.py                summarization and urgency call
  __main__.py           triage run (python -m triage)
digest/
  db.py                 digest queries and send tracking
  formatting.py         HTML digest body
  __main__.py           digest run (python -m digest)
db/init/                schema, applied once to a new database
db/migrations/          later schema changes, applied by hand
deploy/                 container build and AWS deployment runbook
docker-compose.yml      local Postgres/pgvector, an alternative to Supabase in development
```

Design decisions and the reasoning behind them are recorded in PLANNING.md.
