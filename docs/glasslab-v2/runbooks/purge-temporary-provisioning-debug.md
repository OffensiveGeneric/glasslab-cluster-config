# Purge Temporary Provisioning Debug

This runbook is intentionally separate from the live v2 bring-up because the remaining PXE/autoinstall cleanup still overlaps with current node-maintenance assumptions.

## Current tracked leftovers

- The tracked PXE snapshots were updated to remove the historical `clusteradmin` password injection from `node48`.
- The tracked cloud-init profiles were updated to replace the old shared `identity.password` hash with rotated non-shared placeholders.
- `docs/next-step-control-plane.md` still tracks this cleanup as unfinished work.
- The helper scripts now prefer passwordless sudo first and can use the reviewed wrapper-based sudo path on the live workers.

## Current live state

Validated on 2026-03-19 from `.44`:

- the helper scripts were updated to prefer passwordless sudo first
- the reviewed wrapper-based sudo path was deployed live to:
  - `node01`
  - `node02`
  - `node03`
  - `node04`
  - `node05`
- `clusteradmin` can now run the reviewed maintenance wrappers without a password on every worker

Implication:

- the maintenance path that previously blocked cleanup has been replaced
- tracked password-era PXE/autoinstall material is now safe to purge from the repo snapshots

## Safe cleanup order

1. Replace password-dependent helper flows first.

Preferred replacements:

- key-only SSH plus passwordless sudo for the narrow maintenance commands that still need node-side root
- or Ansible playbooks that run with a reviewed privilege model instead of ad hoc password prompts

Current status:

- the helper scripts now prefer passwordless sudo when available
- the live workers now have the reviewed wrapper-based passwordless sudo path
- the repo now includes an implementation path for that reviewable model:
  - `ansible/playbooks/enable-narrow-node-maintenance-sudo.yml`
  - root-owned wrappers under `/usr/local/sbin/`
  - a scoped sudoers drop-in for those wrappers only

2. Update the tracked PXE/autoinstall snapshots.

Target files:

- `live-config/provisioner/var/www/html/pxe/cloud-init/default/user-data`
- `live-config/provisioner/var/www/html/pxe/cloud-init/node48/user-data`
- `live-config/provisioner/var/www/html/pxe/cloud-init/node49/user-data`
- `live-config/provisioner/var/www/html/pxe/cloud-init/node02/user-data`
- `live-config/provisioner/var/www/html/pxe/cloud-init/node03/user-data`
- `live-config/provisioner/var/www/html/pxe/cloud-init/node04/user-data`
- `live-config/provisioner/var/www/html/pxe/cloud-init/node05/user-data`

3. Remove any remaining explicit password-setting late-commands from legacy profiles before the next provisioner snapshot. The tracked `node48` snapshot is already cleaned.

4. Replace the shared autoinstall password hash with a rotated non-shared placeholder or another reviewed noninteractive bootstrap approach.

5. Snapshot the live provisioner config again.

```bash
cd /home/glasslab/cluster-config
./scripts/snapshot-provisioner-config.sh
git diff -- live-config/provisioner
```

6. Test one non-production PXE install before relying on the hardened profiles for the next worker.

## What not to do

- Do not assume the tracked snapshots alone update the live provisioner. The live files must still be changed on `.44` and then re-snapshotted.
