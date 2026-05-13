-- Run once against existing Postgres DBs (new columns are not added by SQLAlchemy create_all).
ALTER TABLE kyc_submissions
  ADD COLUMN IF NOT EXISTS reference_urls JSONB;
