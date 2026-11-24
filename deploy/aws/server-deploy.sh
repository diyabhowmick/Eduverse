#!/bin/bash
# Runs ON the server (sent through SSM by deploy.ps1): pull the new image, restart, wait until it is ready.
# A failed readiness check rolls back to the image that was running before.
set -euo pipefail
cd /opt/eduverse
source .env
TAG="${1:-latest}"
REGISTRY="${IMAGE%%/*}"
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$REGISTRY" >/dev/null
PREV="$(docker inspect --format '{{.Config.Image}}' "$(docker compose ps -q api 2>/dev/null | head -1)" 2>/dev/null || true)"
NEW="${IMAGE%:*}:$TAG"
sed -i "s#^IMAGE=.*#IMAGE=$NEW#" .env
docker compose pull api worker
docker compose up -d --remove-orphans
for i in $(seq 1 40); do
  if docker compose exec -T api python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/ready', timeout=4).status == 200 else 1)" 2>/dev/null; then
    echo "READY $NEW"; docker image prune -f >/dev/null; exit 0
  fi
  sleep 5
done
echo "NOT READY after 200 seconds"
if [ -n "$PREV" ] && [ "$PREV" != "$NEW" ]; then
  echo "Rolling back to $PREV"; sed -i "s#^IMAGE=.*#IMAGE=$PREV#" .env; docker compose up -d
fi
docker compose logs --tail 80 api
exit 1
