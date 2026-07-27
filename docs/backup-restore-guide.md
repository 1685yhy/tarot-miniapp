# Database Backup & Restore Guide

## Overview

Automated daily backups of the `tarot` MySQL database are stored in `/opt/tarot/backups/`.
Backups are compressed `.sql.gz` files named `tarot_YYYYMMDD_HHMMSS.sql.gz`.

## Backup Schedule

- **Frequency:** Daily at 3:00 AM
- **Retention:** 7 days (older backups are automatically deleted)
- **Location:** `/opt/tarot/backups/`

## Manual Backup

```bash
# Run the backup script directly
/opt/tarot/backup-db.sh
```

## Restore

### Option 1: Restore latest backup

```bash
# Find the latest backup file
LATEST=$(ls -t /opt/tarot/backups/tarot_*.sql.gz | head -1)

# Decompress and restore
gunzip -c "$LATEST" | mysql -u tarot -p'tarot123' tarot

echo "Restored from: $LATEST"
```

### Option 2: Restore a specific backup

```bash
gunzip -c /opt/tarot/backups/tarot_20260101_030000.sql.gz | mysql -u tarot -p'tarot123' tarot
```

### Option 3: Restore to a different database

```bash
# Create the target database first
mysql -u tarot -p'tarot123' -e "CREATE DATABASE IF NOT EXISTS tarot_restore"

# Restore into the new database
gunzip -c /opt/tarot/backups/tarot_20260101_030000.sql.gz | mysql -u tarot -p'tarot123' tarot_restore
```

## Verification

After restoring, verify the data:

```bash
# Check table count
mysql -u tarot -p'tarot123' tarot -e "SELECT COUNT(*) AS total_tables FROM information_schema.tables WHERE table_schema='tarot'"

# Check user count
mysql -u tarot -p'tarot123' tarot -e "SELECT COUNT(*) AS total_users FROM users"

# Check recent readings
mysql -u tarot -p'tarot123' tarot -e "SELECT id, spread_type, created_at FROM readings ORDER BY created_at DESC LIMIT 5"
```

## Troubleshooting

| Issue | Solution |
|---|---|
| `mysqldump: command not found` | Install MySQL client: `apt install mysql-client` |
| `Access denied for user` | Verify credentials in `/opt/tarot/backup-db.sh` |
| `Can't connect to MySQL server` | Ensure MySQL is running: `systemctl status mysql` |
| Backup file is 0 bytes | Check disk space: `df -h /opt/tarot/backups` |

## Cron Setup

If the cron job is not yet installed:

```bash
# Install daily backup at 3 AM
echo "0 3 * * * /opt/tarot/backup-db.sh" | crontab -

# Verify installation
crontab -l
```
