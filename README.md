# Glasslab Cluster Config

Canonical cluster management lives here.

- `ansible/`: inventory, variables, and playbooks
- `docs/`: architecture, version-control, and next-step notes
- `live-config/`: tracked snapshots of active provisioner configuration
- `scripts/`: helper wrappers for repeatable operations

Current intended roles:

- `192.168.1.44` (`glasslab-PXE-01`): provisioner, bastion, Ansible control host, kubectl admin workstation
- `192.168.1.48` (`node01`): Kubernetes worker candidate
- future dedicated nodes: add under `control_plane` or `workers` in `ansible/inventory/hosts.yml`

Control plane is intentionally deferred until a dedicated control-plane node exists.
