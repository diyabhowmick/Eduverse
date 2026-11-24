#!/bin/sh
# Hands the storage volume to the app user, then runs the command as that user.
if [ "$(id -u)" = "0" ]; then
  chown -R 10001:10001 "${STORAGE_DIR:-/data/storage}" 2>/dev/null || true
  exec setpriv --reuid=10001 --regid=10001 --init-groups "$@"
fi
exec "$@"
