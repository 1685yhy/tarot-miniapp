#!/bin/bash
set -e

echo "Deploying to production..."

sshpass -p "${SERVER_PASSWORD}" ssh root@${SERVER_HOST} << 'EOF'
  cd /opt/tarot/backend
  git pull origin master
  systemctl restart tarot-api
  sleep 3
  curl -s localhost:8000/health
EOF

echo "Deploy complete!"
