# Glasslab Cluster Config

Canonical cluster management lives here.

- `ansible/`: inventory, variables, and playbooks
- `docs/`: architecture, bootstrap, version-control, and next-step notes
- `kubeadm/`: versioned cluster init and network manifests
- `live-config/`: tracked snapshots of active provisioner configuration
- `scripts/`: helper wrappers for repeatable operations

Current roles:

- `192.168.1.44` (`glasslab-PXE-01`): provisioner, bastion, Ansible control host, kubectl admin workstation
- `192.168.1.49` (`cp01`): Kubernetes control plane
- `192.168.1.48` (`node01`): Kubernetes worker

Current cluster state:

- `cp01` and `node01` are PXE-provisioned and reachable by SSH.
- `kubectl` on the provisioner is wired to the live cluster.
- Calico is installed with a non-overlapping pod CIDR of `10.244.0.0/16`.
- A smoke pod was scheduled successfully onto `node01` and removed.
