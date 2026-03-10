#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SNAPROOT="$ROOT/live-config/provisioner"

copy_file() {
  local src="$1"
  local rel="$2"
  install -D -m 0644 /dev/null "$SNAPROOT/$rel"
  sudo cp "$src" "$SNAPROOT/$rel"
}

copy_tree() {
  local src="$1"
  local rel="$2"
  mkdir -p "$SNAPROOT/$rel"
  sudo find "$src" -maxdepth 1 -type f \
    ! -name '*.bak-*' \
    -exec cp {} "$SNAPROOT/$rel/" \;
}

copy_file /etc/dnsmasq.proxy-pxe.conf etc/dnsmasq.proxy-pxe.conf
copy_file /etc/default/tftpd-hpa etc/default/tftpd-hpa
copy_file /etc/nginx/sites-available/default etc/nginx/sites-available/default
copy_file /srv/tftp/autoexec.ipxe srv/tftp/autoexec.ipxe
copy_file /var/www/html/pxe/ipxe/boot.ipxe var/www/html/pxe/ipxe/boot.ipxe
copy_tree /var/www/html/pxe/cloud-init/default var/www/html/pxe/cloud-init/default
copy_tree /var/www/html/pxe/cloud-init/node48 var/www/html/pxe/cloud-init/node48

sudo chown -R "$USER":"$USER" "$SNAPROOT"
printf 'Snapshot updated under %s\n' "$SNAPROOT"
