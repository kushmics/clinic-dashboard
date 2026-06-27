FROM node:20-bookworm-slim AS frontend-build

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    UPLOAD_DIR=/tmp/clinic-dashboard/uploads

WORKDIR /app

COPY backend/requirements-deploy.txt ./backend/requirements-deploy.txt
RUN pip install --no-cache-dir -r backend/requirements-deploy.txt

COPY backend ./backend
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

WORKDIR /app/backend
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
