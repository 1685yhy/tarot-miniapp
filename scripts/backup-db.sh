#!/bin/bash
# Automated database backup script for Starlight Tarot
# Usage: ./backup-db.sh
# Scheduled: daily at 3am via cron

BACKUP_DIR="/opt/tarot/backups"
DB_NAME="tarot"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/tarot_$TIMESTAMP.sql.gz"

mkdir -p "$BACKUP_DIR"
mysqldump -u tarot -p'tarot123' tarot | gzip > "$BACKUP_FILE"

# Keep only last 7 days of backups
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +7 -delete

echo "Backup complete: $BACKUP_FILE ($(du -h $BACKUP_FILE | cut -f1))"
