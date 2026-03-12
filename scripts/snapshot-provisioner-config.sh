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
copy_file /srv/tftp/node51/pxelinux.cfg/default srv/tftp/node51/pxelinux.cfg/default
copy_file /var/www/html/pxe/ipxe/boot.ipxe var/www/html/pxe/ipxe/boot.ipxe

while IFS= read -r dir; do
  name="$(basename "$dir")"
  copy_tree "$dir" "var/www/html/pxe/cloud-init/$name"
done < <(sudo find /var/www/html/pxe/cloud-init -mindepth 1 -maxdepth 1 -type d | sort)

sudo chown -R "$USER":"$USER" "$SNAPROOT"
printf 'Snapshot updated under %s\n' "$SNAPROOT"
