CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE emails (
    id                BIGSERIAL PRIMARY KEY,
    account_id        TEXT NOT NULL,
    graph_message_id  TEXT NOT NULL,
    subject           TEXT,
    sender            TEXT,
    received_at       TIMESTAMPTZ,
    raw_body          TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (account_id, graph_message_id)
);

CREATE INDEX emails_account_id_idx ON emails (account_id);

-- vector dimension must match OPENAI_EMBEDDING_MODEL's output (text-embedding-3-small = 1536)
CREATE TABLE email_chunks (
    id          BIGSERIAL PRIMARY KEY,
    account_id  TEXT NOT NULL,
    email_id    BIGINT NOT NULL REFERENCES emails(id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    content     TEXT NOT NULL,
    embedding   VECTOR(1536) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (email_id, chunk_index)
);

CREATE INDEX email_chunks_account_id_idx ON email_chunks (account_id);

CREATE TABLE email_summaries (
    id           BIGSERIAL PRIMARY KEY,
    account_id   TEXT NOT NULL,
    email_id     BIGINT NOT NULL UNIQUE REFERENCES emails(id) ON DELETE CASCADE,
    summary      TEXT NOT NULL,
    urgency      TEXT NOT NULL CHECK (urgency IN ('low', 'medium', 'high', 'urgent')),
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX email_summaries_account_id_idx ON email_summaries (account_id);

CREATE TABLE digest_log (
    id           BIGSERIAL PRIMARY KEY,
    account_id   TEXT NOT NULL,
    digest_date  DATE NOT NULL,
    sent_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (account_id, digest_date)
);

CREATE TABLE approved_users (
    email      TEXT PRIMARY KEY,
    added_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE accounts (
    account_id              TEXT PRIMARY KEY,
    encrypted_refresh_token TEXT NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    priority_context         TEXT
);

CREATE TABLE triage_runs (
    id             BIGSERIAL PRIMARY KEY,
    account_id     TEXT NOT NULL,
    digest_date    DATE NOT NULL,
    expected_count INT NOT NULL,
    actual_count   INT NOT NULL DEFAULT 0,
    completed_at   TIMESTAMPTZ,
    UNIQUE (account_id, digest_date)
);
