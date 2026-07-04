# Frame Extractor

Extract frames from a video (e.g. a YouTube URL) at a fixed interval and/or specific timestamps, via a web app. See the [Legal & disclaimer](#legal--disclaimer) section before using.

## Architecture

- `backend/` — FastAPI + Celery + PostgreSQL + Redis (see `docker-compose.yml`)
- `frontend/` — Next.js app, deployable to Vercel

## Local development

1. Copy env files: `cp .env.example .env` and `cp frontend/.env.local.example frontend/.env.local`
2. Start the backend stack: `docker compose up --build`
3. Run migrations: `docker compose exec api alembic upgrade head`
4. Start the frontend: `cd frontend && npm install && npm run dev`
5. Open `http://localhost:3000`, sign up, and submit a YouTube URL with an interval (seconds) and/or comma-separated manual timestamps.

## Backend tests

```bash
cd backend
pip install -r requirements.txt
pytest -v
```

## Notes

- Extracted frames and source videos are kept on disk (`videodata` Docker volume) until manually cleared.
- Failed jobs are not automatically retried — resubmit from the UI.
- When deploying, set `YTF_CORS_ORIGINS` to the frontend's exact production origin (e.g. the Vercel deployment URL) instead of leaving it at the localhost default.

## Legal & disclaimer

This project is provided as-is, for extracting frames from videos you own or are
otherwise authorized to use.

- **No affiliation.** This tool is independent and is **not** affiliated with, endorsed
  by, or sponsored by YouTube or Google LLC. "YouTube" is a trademark of Google LLC; it
  is referenced only to describe compatibility.
- **Your responsibility.** Downloading videos may violate the source platform's Terms of
  Service, and videos and their individual frames are typically protected by copyright.
  You are solely responsible for ensuring you have the rights to process any content you
  submit and for complying with applicable law and platform terms. Do not use this tool to
  download or redistribute content you do not own or are not licensed to use.
- **Not legal advice.** If you intend to operate this as a public or commercial service,
  consult a qualified lawyer first — facilitating third-party downloads of copyrighted
  content carries real legal risk.
