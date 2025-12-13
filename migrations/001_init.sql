-- StegOps CRM-Lite + Gmail token store (001)
-- Apply: psql "$DATABASE_URL" -f migrations/001_init.sql

CREATE TABLE IF NOT EXISTS leads (
  id SERIAL PRIMARY KEY,
  name VARCHAR(200),
  email VARCHAR(320) UNIQUE NOT NULL,
  company VARCHAR(200),
  source VARCHAR(100),
  status VARCHAR(50) NOT NULL DEFAULT 'new',
  created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
);

CREATE TABLE IF NOT EXISTS deals (
  id SERIAL PRIMARY KEY,
  lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  tier VARCHAR(10) NOT NULL DEFAULT '2',
  stage VARCHAR(50) NOT NULL DEFAULT 'scoping',
  value_usd NUMERIC(12,2),
  probability INTEGER NOT NULL DEFAULT 50,
  created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
);

CREATE TABLE IF NOT EXISTS messages (
  id SERIAL PRIMARY KEY,
  deal_id INTEGER REFERENCES deals(id) ON DELETE SET NULL,
  direction VARCHAR(10) NOT NULL,
  channel VARCHAR(20) NOT NULL DEFAULT 'email',
  thread_id VARCHAR(200),
  message_id VARCHAR(200) UNIQUE,
  subject VARCHAR(500),
  from_email VARCHAR(320),
  to_email VARCHAR(320),
  content TEXT NOT NULL,
  confidence_score NUMERIC(4,3),
  requires_approval BOOLEAN NOT NULL DEFAULT TRUE,
  gmail_draft_id VARCHAR(200),
  created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
);

CREATE INDEX IF NOT EXISTS idx_messages_thread_id ON messages(thread_id);
CREATE INDEX IF NOT EXISTS idx_messages_message_id ON messages(message_id);

CREATE TABLE IF NOT EXISTS audit_log (
  id SERIAL PRIMARY KEY,
  actor VARCHAR(20) NOT NULL,
  action VARCHAR(200) NOT NULL,
  object_type VARCHAR(50) NOT NULL,
  object_id VARCHAR(200),
  detail_json TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
);

CREATE TABLE IF NOT EXISTS google_tokens (
  id SERIAL PRIMARY KEY,
  email VARCHAR(320) UNIQUE NOT NULL,
  token_json TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
  updated_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
);

CREATE TABLE IF NOT EXISTS gmail_state (
  id SERIAL PRIMARY KEY,
  email VARCHAR(320) UNIQUE NOT NULL,
  last_history_id VARCHAR(64),
  updated_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
);


CREATE TABLE IF NOT EXISTS documents (
  id SERIAL PRIMARY KEY,
  deal_id INTEGER REFERENCES deals(id) ON DELETE SET NULL,
  doc_type VARCHAR(50) NOT NULL,
  status VARCHAR(30) NOT NULL DEFAULT 'draft',
  storage_url VARCHAR(500),
  content TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
);


CREATE TABLE IF NOT EXISTS invoices (
  id SERIAL PRIMARY KEY,
  deal_id INTEGER REFERENCES deals(id) ON DELETE SET NULL,
  amount_usd NUMERIC(12,2) NOT NULL,
  status VARCHAR(30) NOT NULL DEFAULT 'draft',
  external_id VARCHAR(200),
  created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
);
