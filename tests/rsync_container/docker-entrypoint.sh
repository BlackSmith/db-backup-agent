#!/bin/sh
set -eu

: "${RSYNC_USER:=backup}"
: "${RSYNC_PASSWORD:=backup}"
: "${RSYNC_MODULE:=data}"
: "${RSYNC_PATH:=/data}"
: "${RSYNC_UID:=root}"
: "${RSYNC_GID:=root}"

mkdir -p "${RSYNC_PATH}"

cat > /etc/rsyncd.secrets <<EOF
${RSYNC_USER}:${RSYNC_PASSWORD}
EOF

chmod 600 /etc/rsyncd.secrets

cat > /etc/rsyncd.conf <<EOF
uid = ${RSYNC_UID}
gid = ${RSYNC_GID}
use chroot = no
read only = no
max connections = 10
log file = /dev/stdout
pid file = /run/rsyncd.pid

[${RSYNC_MODULE}]
    path = ${RSYNC_PATH}
    comment = Docker RSYNC Share
    auth users = ${RSYNC_USER}
    secrets file = /etc/rsyncd.secrets
    list = yes
EOF

exec rsync --daemon --no-detach --config=/etc/rsyncd.conf