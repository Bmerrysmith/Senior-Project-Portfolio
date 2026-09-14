CREATE TABLE approved_users (
    email      TEXT PRIMARY KEY,
    added_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE accounts (
    account_id              TEXT PRIMARY KEY,
    encrypted_refresh_token TEXT NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
