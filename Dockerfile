# Backend-only image for Fly.io (Milestone 7, issue #27). backend/
# imports parser/ for the reporter endpoint (stdlib only) but never runs
# static_parser/ (Node) - that only happens offline or in the customer's CI -
# so this image needs Python only, not Node.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ backend/
# The reporter endpoint (issue #44) interprets raw reports/scan facts with the
# same stdlib-only parsers the CLI uses. No Node needed: the scan itself runs
# on the customer's side.
COPY parser/ parser/

ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}"]
