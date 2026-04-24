#!/bin/bash
# HRMS Deployment Script
# Run as root on server: bash deploy.sh

set -e

APP_DIR="/var/www/hrms"
VENV="$APP_DIR/venv"
SERVICE="gunicorn_hrms"

echo "=== Pulling latest code ==="
cd $APP_DIR
git pull origin main

echo "=== Activating virtualenv ==="
source $VENV/bin/activate

echo "=== Installing/updating requirements ==="
pip install -r requirements.txt --quiet

echo "=== Running migrations ==="
python manage.py migrate --noinput

echo "=== Collecting static files ==="
python manage.py collectstatic --noinput

echo "=== Restarting gunicorn ==="
systemctl restart $SERVICE

echo "=== Deployment complete ==="
