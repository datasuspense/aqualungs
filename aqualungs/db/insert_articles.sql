INSERT OR IGNORE INTO articles (
       arxiv_id,
       title,
       authors,
       created_at,
       annotation,
       subjects,
       url,
       github_urls,
       other_urls,
       is_updated
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)