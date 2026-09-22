FROM python:3.11-slim

WORKDIR /app

# libreoffice-writer: high-fidelity .docx -> HTML conversion for the
# Email Template / Template Designer "Import from Word" features (preserves
# fonts, colors, alignment, tables — mammoth's fallback path drops these).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app
USER appuser

VOLUME /app/data
EXPOSE 8000

CMD ["gunicorn", "-w", "3", "-b", "0.0.0.0:8000", "--timeout", "120", "app:app"]
