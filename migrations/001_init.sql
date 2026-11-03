CREATE TABLE owners (
  id VARCHAR(32) PRIMARY KEY,
  email VARCHAR(254) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  created_at TIMESTAMP NOT NULL
);

CREATE TABLE api_tokens (
  token_hash VARCHAR(64) PRIMARY KEY,
  owner_id VARCHAR(32) NOT NULL REFERENCES owners(id) ON DELETE CASCADE,
  created_at TIMESTAMP NOT NULL,
  expires_at TIMESTAMP NOT NULL
);

CREATE INDEX ix_api_tokens_owner ON api_tokens (owner_id);

CREATE TABLE widgets (
  id VARCHAR(16) PRIMARY KEY,
  owner_id VARCHAR(32) NOT NULL REFERENCES owners(id) ON DELETE CASCADE,
  type VARCHAR(32) NOT NULL,
  title VARCHAR(200) NOT NULL,
  description VARCHAR(1000) NOT NULL,
  button_text VARCHAR(60) NOT NULL,
  fields_json TEXT NOT NULL,
  display_json TEXT NOT NULL,
  honeypot_field VARCHAR(32) NOT NULL,
  is_active BOOLEAN NOT NULL,
  version INTEGER NOT NULL,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
);

CREATE INDEX ix_widgets_owner ON widgets (owner_id, created_at);

CREATE TABLE submissions (
  id VARCHAR(32) PRIMARY KEY,
  widget_id VARCHAR(16) NOT NULL REFERENCES widgets(id) ON DELETE CASCADE,
  owner_id VARCHAR(32) NOT NULL REFERENCES owners(id) ON DELETE CASCADE,
  data_json TEXT NOT NULL,
  ip_hash VARCHAR(64) NOT NULL,
  country VARCHAR(100),
  city VARCHAR(100),
  geo_provider VARCHAR(32),
  idempotency_key VARCHAR(128),
  created_at TIMESTAMP NOT NULL
);

CREATE INDEX ix_submissions_widget_created ON submissions (widget_id, created_at);

CREATE INDEX ix_submissions_owner_created ON submissions (owner_id, created_at);

CREATE UNIQUE INDEX ux_submissions_idem ON submissions (widget_id, idempotency_key);

CREATE TABLE spam_events (
  id VARCHAR(32) PRIMARY KEY,
  widget_id VARCHAR(16) NOT NULL REFERENCES widgets(id) ON DELETE CASCADE,
  reason VARCHAR(40) NOT NULL,
  created_at TIMESTAMP NOT NULL
);

CREATE INDEX ix_spam_widget_created ON spam_events (widget_id, created_at);

CREATE TABLE jobs (
  id VARCHAR(32) PRIMARY KEY,
  kind VARCHAR(40) NOT NULL,
  payload_json TEXT NOT NULL,
  status VARCHAR(16) NOT NULL,
  attempts INTEGER NOT NULL,
  max_attempts INTEGER NOT NULL,
  run_at TIMESTAMP NOT NULL,
  last_error TEXT,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
);

CREATE INDEX ix_jobs_status_run ON jobs (status, run_at)
