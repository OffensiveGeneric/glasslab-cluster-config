# Version Control Workflow

`/home/glasslab/cluster-config` is the canonical infrastructure repository.

What is tracked:

- Ansible inventory, variables, playbooks, docs, and helper scripts
- Snapshots of active provisioner PXE/web/service configuration under `live-config/provisioner/`

What is intentionally not tracked:

- Large binary artifacts such as ISOs and kernel/initrd images
- Timestamped `.bak-*` files created for safety during edits

Typical workflow:

1. Edit the live system files or Ansible content.
2. Run `scripts/snapshot-provisioner-config.sh` to copy active provisioner configs into the repo.
3. Review with `git status` and `git diff`.
4. Commit with a meaningful message.

Rollback workflow:

1. Use Git to check out the desired commit or file version in `/home/glasslab/cluster-config`.
2. Run `scripts/restore-provisioner-config.sh` to push the tracked snapshot back onto the live provisioner.
3. The restore script writes timestamped `.bak-<stamp>` backups before overwriting live files and restarts `dnsmasq`, `tftpd-hpa`, and `nginx`.
