#!/bin/bash
# First boot only: Docker, the compose files, and a service that starts EduVerse at every boot.
set -euxo pipefail
dnf install -y docker
systemctl enable --now docker
mkdir -p /usr/local/lib/docker/cli-plugins
curl -fsSL https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-x86_64 -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
# a swap file, so a large book through M1 does not run the box out of memory
fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile && echo '/swapfile none swap sw 0 0' >> /etc/fstab

mkdir -p /opt/eduverse && cd /opt/eduverse
echo '${compose_b64}' | base64 -d > docker-compose.yml
echo '${caddy_b64}' | base64 -d > Caddyfile
echo '${deploy_b64}' | base64 -d > deploy.sh && chmod +x deploy.sh
cat > .env <<ENV
IMAGE=${image}
AWS_REGION=${region}
AWS_SECRET_ID=${secret_id}
DB_HOST=${db_host}
S3_BUCKET=${bucket}
LOG_GROUP=${log_group}
DOMAIN=${domain}
ACME_EMAIL=${acme_email}
SUPERADMIN_EMAIL=${admin}
EDUVERSE_ENV=${env}
ENV
chmod 600 .env

cat > /etc/systemd/system/eduverse.service <<UNIT
[Unit]
Description=EduVerse (docker compose)
After=docker.service network-online.target
Requires=docker.service
[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/eduverse
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable eduverse.service
# The first image may not be pushed yet; deploy.ps1 starts it once it is.
./deploy.sh latest || true
