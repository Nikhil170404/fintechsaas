#!/usr/bin/env bash
# FinTech Desk — Database & file backup script
# Add to crontab: 0 2 * * * /opt/fintechdesk/backup.sh >> /var/log/fintechdesk_backup.log 2>&1

set -euo pipefail
cd "$(dirname "$0")"

BACKUP_DIR="data/backups"
DB_FILE="data/app.db"
TENANT_DIR="data/tenants"
DATE=$(date +%Y%m%d_%H%M%S)
KEEP_DAYS="${BACKUP_DAYS:-30}"

mkdir -p "$BACKUP_DIR"

echo "=== FinTech Desk Backup: $DATE ==="

# 1. Hot backup of SQLite database
if [ -f "$DB_FILE" ]; then
    DEST="$BACKUP_DIR/app_${DATE}.db"
    sqlite3 "$DB_FILE" ".backup '$DEST'"
    SIZE=$(du -sh "$DEST" | cut -f1)
    echo "DB backup: $DEST ($SIZE)"
else
    echo "WARNING: $DB_FILE not found, skipping DB backup"
fi

# 2. Zip tenant files
if [ -d "$TENANT_DIR" ]; then
    TENANT_ZIP="$BACKUP_DIR/tenants_${DATE}.zip"
    zip -r -q "$TENANT_ZIP" "$TENANT_DIR"
    SIZE=$(du -sh "$TENANT_ZIP" | cut -f1)
    echo "Tenant files backup: $TENANT_ZIP ($SIZE)"
fi

# 3. Prune old backups
find "$BACKUP_DIR" -name "app_*.db" -mtime "+$KEEP_DAYS" -delete
find "$BACKUP_DIR" -name "tenants_*.zip" -mtime "+$KEEP_DAYS" -delete
echo "Pruned backups older than $KEEP_DAYS days"

# 4. Optional: Sync to S3/Backblaze (uncomment and configure)
# if [ -n "${S3_BUCKET:-}" ]; then
#     aws s3 sync "$BACKUP_DIR" "s3://$S3_BUCKET/backups/" --storage-class STANDARD_IA
#     echo "Synced to s3://$S3_BUCKET/backups/"
# fi

echo "=== Backup complete ==="
