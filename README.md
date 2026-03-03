# aqualungs
Collect and digest arXiv.org computer science articles

Aqualungs fetches arXiv notifications from Gmail, extracts article metadata, optionally downloads PDFs, and stores metadata locally.

## Features
- Gmail OAuth authorization
- Parse arXiv email digests
- Save article metadata into SQLite database
- Download PDFs from arXiv

## Requirements
- Python **3.13+**
- Google OAuth credentials for Gmail API

## Notes
- If you change scopes, delete `data/token.json` and re‑authorize.
- If you see `redirect_uri_mismatch`, ensure your OAuth redirect URI matches exactly including port number.
