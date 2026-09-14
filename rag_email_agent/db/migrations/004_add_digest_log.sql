CREATE TABLE digest_log (
    id           BIGSERIAL PRIMARY KEY,
    account_id   TEXT NOT NULL,
    digest_date  DATE NOT NULL,
    sent_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (account_id, digest_date)
);
