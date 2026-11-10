# Backend image. Build context is the repository root (see docker-compose.yml).
FROM python:3.12-slim

# WeasyPrint needs Pango; DejaVu/Noto are the PDF font fallbacks (incl. Arabic).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/app

# Dependency layer: only re-runs when pyproject.toml changes.
COPY backend/pyproject.toml backend/pyproject.toml
RUN mkdir -p backend/app && touch backend/app/__init__.py \
    && pip install --no-cache-dir -e "backend[dev]"

COPY backend backend
COPY scripts scripts
# Nicer PDF fonts (Fredoka, Nunito, Noto Naskh Arabic, Cairo). Offline builds fall back to system fonts.
RUN python scripts/fetch_fonts.py || echo "font download skipped; using system fonts"

ENV HOST=0.0.0.0 PORT=8000 DATA_DIR=/data
WORKDIR /srv/app/backend
EXPOSE 8000
CMD ["python", "-m", "app.main"]
