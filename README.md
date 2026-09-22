# FinTech SaaS

Client account statements, GST invoices, loan/EMI schedules and portfolio reports — generated as branded PDFs and emailed to clients. Multi-tenant: each company that signs up gets its own isolated data (clients, settings, uploads, generated PDFs) and can add staff accounts under their own login.

## Quick start (local dev)

```bash
python3.11 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env            # edit as needed — a SECRET_KEY is auto-generated if left default

python app.py                   # http://127.0.0.1:5000
```

Requires **Python 3.10+** (the code uses `str | None` union-type syntax). On macOS, if port 5000 is taken by AirPlay Receiver, either disable it (System Settings → General → AirDrop & Handoff) or run on another port: `PORT=5001 python app.py`.

Open the app, click **Create your company account**, and sign up — this creates your company (tenant) and your owner login. There is no default/shared admin account.

### Optional: LibreOffice (for high-fidelity Word import)

The **Email Template** and **Template Designer** "Import from Word" features use LibreOffice headless to convert `.docx` → HTML, since it renders the document the way Word does (fonts, colors, alignment, tables, spacing). Without it, the app automatically falls back to `mammoth`, which still works but produces simplified HTML that drops most direct formatting.

- **macOS**: install [LibreOffice](https://www.libreoffice.org/download/download/) into `/Applications`.
- **Linux**: `sudo apt install libreoffice-writer`
- **Docker**: already included in the `Dockerfile` — no setup needed.

The app looks for `soffice` on `PATH`, then the standard macOS/Debian install locations. No configuration needed either way.

## Quick start (Docker)

```bash
cp .env.example .env            # edit as needed
docker compose up --build -d
```

App is now on `http://localhost:8000`, served by gunicorn (not the Flask dev server). The `./data` folder on your host is mounted into the container — it holds the SQLite database and every tenant's files, so it survives container rebuilds/restarts. **Back this folder up.**

## Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `SECRET_KEY` | Flask session signing key | auto-generated on first run if left as the placeholder |
| `COMPANY_NAME` / `SENDER_NAME` | Fallback defaults for a brand-new tenant's settings | "FinTech Solutions..." |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASS` | Fallback defaults for a tenant's own client-facing SMTP (each tenant can override these in Settings → SMTP) | Gmail SMTP |
| `SYS_SMTP_HOST` / `SYS_SMTP_PORT` / `SYS_SMTP_USER` / `SYS_SMTP_PASS` | **Platform** transactional email (password-reset links). Separate from tenant SMTP — used before a tenant may have configured their own. If left blank, reset links are written to that tenant's audit log instead, so local/dev works without real SMTP. | blank |

## First-run signup & accounts

- `/signup` creates a new company (tenant) and its first user, who gets the **owner** role.
- Owners can add **staff** accounts under Settings → Team. Staff can use the app but can't manage the team or other owner-only settings.
- Forgot your password? Use the **Forgot password?** link on the login page. Without `SYS_SMTP_*` configured, ask whoever has server access to check that tenant's audit log (Settings → Security → Audit Log, or `sqlite3 data/app.db "select * from audit_log where action='PASSWORD_RESET_LINK' order by id desc limit 5;"`) for the reset link.

## Multi-tenancy model

- One SQLite database (`data/app.db`) holds `tenants`, `users`, and each tenant's settings/clients/mapping/activity as JSON rows keyed by `tenant_id` — isolated per company, crash-safe (SQLite transactions), and queryable.
- Each tenant's uploaded Excel files, generated PDFs, logo and Word templates live in their own folder: `data/tenants/<tenant_id>/uploads/` and `data/tenants/<tenant_id>/output/`. Tenants never see each other's files.
- Existing single-admin installs (pre-multi-tenant) are migrated automatically on first boot: if `uploads/settings.json` exists and no tenants exist yet in the database, a "Legacy Company" tenant is created from the old admin account and all old files/settings/clients are imported. No manual steps needed.

## Production deployment (Docker + nginx + HTTPS)

1. Point a domain's DNS at your server.
2. `docker compose up --build -d` (binds to `127.0.0.1:8000` by default via the compose port mapping — adjust if your server needs otherwise).
3. Install nginx + certbot: `sudo apt install nginx certbot python3-certbot-nginx`.
4. Copy `deploy/nginx.conf.example` to `/etc/nginx/sites-available/fintech-saas`, replace `your-domain.com`, symlink into `sites-enabled`, `nginx -t && systemctl reload nginx`.
5. `sudo certbot --nginx -d your-domain.com` — certbot handles the HTTPS server block and redirect automatically.
6. Set a real `SECRET_KEY` and (recommended) `SYS_SMTP_*` in `.env` before going live.

## Backups

Everything that matters lives under `data/`: the SQLite database (`data/app.db`, all tenants/users/settings/clients) and every tenant's files (`data/tenants/<id>/`). Back up that one directory — e.g. a nightly `tar czf backup-$(date +%F).tar.gz data/` shipped off-server.

## Architecture

- `app.py` — Flask app: routes, auth, tenant-scoped storage helpers.
- `modules/db.py` — SQLite access layer (tenants, users, password resets, audit log, per-tenant JSON settings/clients/mapping/activity blobs).
- `modules/*_generator.py`, `modules/pdf_generator.py`, `modules/statement_builder.py` — PDF generation (reportlab).
- `modules/excel_reader.py`, `modules/column_detector.py` — Excel ingestion & column auto-mapping.
- `modules/email_sender.py` — SMTP sending (per-tenant creds for statements, system creds for password resets).
- `templates/` — Jinja2 + Bootstrap 5 UI.
