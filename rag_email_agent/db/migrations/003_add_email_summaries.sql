CREATE TABLE email_summaries (
    id           BIGSERIAL PRIMARY KEY,
    account_id   TEXT NOT NULL,
    email_id     BIGINT NOT NULL UNIQUE REFERENCES emails(id) ON DELETE CASCADE,
    summary      TEXT NOT NULL,
    urgency      TEXT NOT NULL CHECK (urgency IN ('low', 'medium', 'high', 'urgent')),
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX email_summaries_account_id_idx ON email_summaries (account_id);
