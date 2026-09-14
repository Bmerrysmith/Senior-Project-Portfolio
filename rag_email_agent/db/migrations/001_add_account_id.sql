ALTER TABLE emails ADD COLUMN account_id TEXT;
ALTER TABLE email_chunks ADD COLUMN account_id TEXT;

-- backfill: your existing 50 rows all came from one account (whichever
-- ACCOUNT_ID you're about to set), so:
UPDATE emails SET account_id = 'stusick@outlook.com';
UPDATE email_chunks SET account_id = 'stusick@outlook.com';

ALTER TABLE emails ALTER COLUMN account_id SET NOT NULL;
ALTER TABLE email_chunks ALTER COLUMN account_id SET NOT NULL;

-- then add the composite unique constraint replacing the old one on
-- graph_message_id alone
ALTER TABLE emails DROP CONSTRAINT emails_graph_message_id_key;
ALTER TABLE emails ADD CONSTRAINT emails_account_message_key UNIQUE (account_id, graph_message_id);

CREATE INDEX IF NOT EXISTS emails_account_id_idx ON emails (account_id);
CREATE INDEX IF NOT EXISTS email_chunks_account_id_idx ON email_chunks (account_id);