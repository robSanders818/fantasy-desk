# fantasy-desk

Scheduled GitHub Actions job that refreshes my fantasy league data, runs the projection models,
and publishes recommendations (lineups, adds/drops, win% added) to an encrypted GitHub Pages
site. The repo is public; league data is only ever committed encrypted, and the Yahoo session
lives in a GitHub secret.

Status: probing whether a saved Yahoo session works from GitHub's servers (`probe.py`).
