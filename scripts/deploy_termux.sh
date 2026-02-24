#!/data/data/com.termux/files/usr/bin/bash
set -e
cd /data/data/com.termux/files/home/price-checker
git pull
sv restart price-checker || true
echo "✅ Updated (and restarted if service exists)"