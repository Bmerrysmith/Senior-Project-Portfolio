CREATE TABLE triage_runs (
    id             BIGSERIAL PRIMARY KEY,
    account_id     TEXT NOT NULL,
    digest_date    DATE NOT NULL,
    expected_count INT NOT NULL,
    actual_count   INT NOT NULL DEFAULT 0,
    completed_at   TIMESTAMPTZ,
    UNIQUE (account_id, digest_date)
);
