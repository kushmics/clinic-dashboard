# Deployment

The repo is set up for a permanent Render deployment from `main`.

## Render Blueprint

Point a Render Blueprint at `render.yaml`. It defines a Docker web service that:

1. Builds the Vite frontend.
2. Installs `backend/requirements-deploy.txt`.
3. Copies the frontend build into the final Python image.
4. Starts FastAPI with Uvicorn on Render's `$PORT`.

## Required Environment Variables

Set these in Render when creating the service:

```text
AUTH_TOKEN=<private staff access token>
```

Optional AI-backed features use these (the blueprint already sets the model
names; supply the keys to enable them):

```text
OPENAI_API_KEY=<OpenAI API key>   # live X-ray reads + patient-ID scanner
EXA_API_KEY=<Exa API key>         # differential evidence / guideline lookup
```

`OPENAI_MODEL` (reasoning, `gpt-5.4`) and `OPENAI_VISION_MODEL` (vision,
`gpt-4o-mini`) are pre-set in `render.yaml` — override only if you change models.

## Health Check

Render should use:

```text
/health
```

The frontend and backend are served from the same origin. Browser calls to
`/api/...` route to the FastAPI API aliases.

## Local Verification

Verify the production image the same way Render builds it:

```bash
docker build -t clinic-dashboard .
docker run --rm -p 8000:8000 -e AUTH_TOKEN=clinic-demo-token clinic-dashboard
```

Then check:

```text
http://127.0.0.1:8000/             # served frontend
http://127.0.0.1:8000/health       # health check (200, no auth)
http://127.0.0.1:8000/api/auth/status
```

(Or, without Docker, run `./start.sh` from the repo root — same single-origin
setup on http://localhost:8000.)
