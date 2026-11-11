# Backend-only image for Fly.io (Milestone 7, issue #27). backend/
# doesn't import anything from parser/ or static_parser/ at runtime -
# those only run offline, via scripts/push_test_inventory.py - so this
# image needs Python only, not Node, and copies just backend/.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ backend/

ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}"]
