#!/bin/bash
# HRMS Initial Server Setup Script
# Run once on a fresh Ubuntu 22.04 VPS as root

set -e

APP_DIR="/var/www/hrms"
REPO_URL="https://github.com/Maheswarbiswal/hrms.git"
SERVICE="gunicorn_hrms"
DOMAIN="hrms.softmateconsulting.com"

echo "=== 1. Update system packages ==="
apt-get update -y && apt-get upgrade -y

echo "=== 2. Install dependencies ==="
apt-get install -y python3 python3-pip python3-venv \
    mysql-server libmysqlclient-dev \
    nginx certbot python3-certbot-nginx \
    git curl build-essential \
    pkg-config default-libmysqlclient-dev

echo "=== 3. Start and secure MySQL ==="
systemctl enable mysql
systemctl start mysql
mysql -e "CREATE DATABASE IF NOT EXISTS hrms CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -e "CREATE USER IF NOT EXISTS 'hrms_user'@'localhost' IDENTIFIED BY '${DB_PASSWORD}';"
mysql -e "GRANT ALL PRIVILEGES ON hrms.* TO 'hrms_user'@'localhost';"
mysql -e "FLUSH PRIVILEGES;"

echo "=== 4. Clone repository ==="
mkdir -p $APP_DIR
git clone $REPO_URL $APP_DIR || (cd $APP_DIR && git pull origin main)

echo "=== 5. Set up Python virtual environment ==="
cd $APP_DIR
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "=== 6. Create .env file ==="
cat > $APP_DIR/.env << EOF
DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY}
DJANGO_DEBUG=False
ALLOWED_HOSTS=${DOMAIN},localhost,127.0.0.1
DB_NAME=hrms
DB_USER=hrms_user
DB_PASSWORD=${DB_PASSWORD}
DB_HOST=localhost
DB_PORT=3306
EOF

echo "=== 7. Run migrations and collect static ==="
cd $APP_DIR
source venv/bin/activate
python manage.py migrate --noinput
python manage.py collectstatic --noinput

echo "=== 8. Set permissions ==="
chown -R www-data:www-data $APP_DIR/media $APP_DIR/staticfiles 2>/dev/null || true
chmod -R 755 $APP_DIR

echo "=== 9. Create gunicorn systemd service ==="
cat > /etc/systemd/system/${SERVICE}.service << EOF
[Unit]
Description=Gunicorn daemon for HRMS
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/venv/bin/gunicorn \
    --workers 3 \
    --bind unix:/run/${SERVICE}.sock \
    hrms.wsgi:application
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable $SERVICE
systemctl start $SERVICE

echo "=== 10. Configure Nginx ==="
cat > /etc/nginx/sites-available/hrms << EOF
server {
    listen 80;
    server_name ${DOMAIN};

    client_max_body_size 20M;

    location /static/ {
        alias ${APP_DIR}/staticfiles/;
        expires 30d;
    }

    location /media/ {
        alias ${APP_DIR}/media/;
        expires 7d;
    }

    location / {
        include proxy_params;
        proxy_pass http://unix:/run/${SERVICE}.sock;
        proxy_read_timeout 300;
    }
}
EOF

ln -sf /etc/nginx/sites-available/hrms /etc/nginx/sites-enabled/hrms
nginx -t
systemctl reload nginx

echo "=== 11. Setup SSL with Let's Encrypt ==="
certbot --nginx -d $DOMAIN --non-interactive --agree-tos -m biswalmaheswar200@gmail.com --redirect || echo "SSL setup skipped - DNS may not be propagated yet"

echo "=== Setup Complete! HRMS is live at https://${DOMAIN} ==="
