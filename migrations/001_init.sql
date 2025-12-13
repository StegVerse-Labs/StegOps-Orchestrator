-- Minimal CRM-Lite schema (expand as needed)
CREATE TABLE IF NOT EXISTS leads (
  id SERIAL PRIMARY KEY,
  name VARCHAR(200),
  email VARCHAR(320) UNIQUE NOT NULL,
  company VARCHAR(200),
  source VARCHAR(100),
  status VARCHAR(50) NOT NULL DEFAULT 'new',
  created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
);
