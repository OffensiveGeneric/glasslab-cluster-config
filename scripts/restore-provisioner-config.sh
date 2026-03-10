#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SNAPROOT="$ROOT/live-config/provisioner"
STAMP="$(date +%Y%m%d-%H%M%S)"

restore_file() {
  local rel="$1"
  local dest="/$rel"
  local src="$SNAPROOT/$rel"
  [ -f "$src" ] || return 0
  sudo install -D -m 0644 "$src" "$dest.tmp.$STAMP"
  if [ -f "$dest" ]; then
    sudo cp "$dest" "$dest.bak-$STAMP"
  fi
  sudo mv "$dest.tmp.$STAMP" "$dest"
}

restore_tree() {
  local rel="$1"
  local src="$SNAPROOT/$rel"
  local dest="/$rel"
  [ -d "$src" ] || return 0
  sudo mkdir -p "$dest"
  sudo find "$dest" -maxdepth 1 -type f ! -name '*.bak-*' -delete
  sudo cp -a "$src/." "$dest/"
}

restore_file etc/dnsmasq.proxy-pxe.conf
restore_file etc/default/tftpd-hpa
restore_file etc/nginx/sites-available/default
restore_file srv/tftp/autoexec.ipxe
restore_file var/www/html/pxe/ipxe/boot.ipxe
restore_tree var/www/html/pxe/cloud-init/default
restore_tree var/www/html/pxe/cloud-init/node48

sudo systemctl restart dnsmasq tftpd-hpa nginx
printf 'Provisioner configs restored from %s and services restarted.\n' "$SNAPROOT"
