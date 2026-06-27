# Deployment Testing

This branch is prepared for a permanent Render deployment.

## Render Blueprint

Use `render.yaml` from the `deployment-testing` branch. It defines a Docker web
service that:

1. Builds the Vite frontend.
2. Installs `backend/requirements-deploy.txt`.
3. Copies the frontend build into the final Python image.
4. Starts FastAPI with Uvicorn on Render's `$PORT`.

## Required Environment Variables

Set these in Render when creating the service:

```text
AUTH_TOKEN=<private staff access token>
```

Optional AI-backed features use these:

```text
OPENAI_API_KEY=<OpenAI API key>
EXA_API_KEY=<Exa API key>
```

## Health Check

Render should use:

```text
/health
```

The frontend and backend are served from the same origin. Browser calls to
`/api/...` route to the FastAPI API aliases.

## Local Verification

From the repo root:

```powershell
cd frontend
npm install
npm run build

cd ..\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

Then check:

```text
http://127.0.0.1:8010/
http://127.0.0.1:8010/health
http://127.0.0.1:8010/api/auth/status
```
