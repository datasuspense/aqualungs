CREATE TABLE IF NOT EXISTS articles (
    arxiv_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    authors TEXT NOT NULL,
    created_at TEXT NOT NULL,
    annotation TEXT,
    subjects TEXT,
    url TEXT NOT NULL,
    github_urls TEXT,
    other_urls TEXT,
    is_updated INTEGER
)
