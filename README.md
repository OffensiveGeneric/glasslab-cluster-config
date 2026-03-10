# Glasslab Cluster Config

Canonical cluster management lives here.

- `ansible/`: inventory, variables, and playbooks
- `docs/`: architecture, version-control, and next-step notes
- `live-config/`: tracked snapshots of active provisioner configuration
- `scripts/`: helper wrappers for repeatable operations

Current intended roles:

- `192.168.1.44` (`glasslab-PXE-01`): provisioner, bastion, Ansible control host, kubectl admin workstation
- `192.168.1.49` (`cp01`): dedicated Kubernetes control-plane candidate
- `192.168.1.48` (`node01`): Kubernetes worker candidate
- future dedicated nodes: add under `control_plane` or `workers` in `ansible/inventory/hosts.yml`

Current cluster state:

- `cp01` and `node01` are PXE-provisioned and reachable by SSH.
- Both nodes have the cluster management SSH key installed.
- `cp01` is bootstrapped with Kubernetes prerequisites and is ready for `kubeadm init`.
- `node01` is bootstrapped with Kubernetes prerequisites and is ready to join once the control plane exists.
