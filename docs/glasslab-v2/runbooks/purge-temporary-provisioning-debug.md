# Purge Temporary Provisioning Debug

This runbook is intentionally separate from the live v2 bring-up because the remaining PXE/autoinstall cleanup still overlaps with current node-maintenance assumptions.

## Current tracked leftovers

- `live-config/provisioner/var/www/html/pxe/cloud-init/node48/user-data` still contains explicit `chpasswd` late-commands for `clusteradmin`.
- Multiple tracked cloud-init profiles still carry a shared `identity.password` hash even though SSH password login is disabled.
- `docs/next-step-control-plane.md` still tracks this cleanup as unfinished work.
- `scripts/build-import-workflow-api-image.sh` and `scripts/sync-titanic-dataset.sh` still assume a node sudo password may be required.

## Safe cleanup order

1. Replace password-dependent helper flows first.

Preferred replacements:

- key-only SSH plus passwordless sudo for the narrow maintenance commands that still need node-side root
- or Ansible playbooks that run with a reviewed privilege model instead of ad hoc password prompts

2. After those helpers are no longer password-dependent, update the tracked PXE/autoinstall snapshots.

Target files:

- `live-config/provisioner/var/www/html/pxe/cloud-init/default/user-data`
- `live-config/provisioner/var/www/html/pxe/cloud-init/node48/user-data`
- `live-config/provisioner/var/www/html/pxe/cloud-init/node49/user-data`
- `live-config/provisioner/var/www/html/pxe/cloud-init/node02/user-data`
- `live-config/provisioner/var/www/html/pxe/cloud-init/node03/user-data`
- `live-config/provisioner/var/www/html/pxe/cloud-init/node04/user-data`
- `live-config/provisioner/var/www/html/pxe/cloud-init/node05/user-data`

3. Remove the explicit `chpasswd` late-commands from legacy profiles such as `node48`.

4. Replace the shared autoinstall password hash with a rotated non-shared value or another reviewed noninteractive bootstrap approach.

5. Snapshot the live provisioner config again.

```bash
cd /home/glasslab/cluster-config
./scripts/snapshot-provisioner-config.sh
git diff -- live-config/provisioner
```

6. Test one non-production PXE install before relying on the hardened profiles for the next worker.

## What not to do

- Do not remove password-dependent provisioning material from the tracked snapshots while current node-maintenance scripts still rely on it.
- Do not assume that changing the repo snapshot alone updates the live provisioner. The live files must be changed first and then re-snapshotted.
