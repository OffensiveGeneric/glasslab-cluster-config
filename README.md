# Glasslab Cluster Config

Canonical cluster management lives here.

- `ansible/`: inventory, variables, and playbooks
- `docs/`: architecture, bootstrap, GPU, package-maintenance, version-control, and next-step notes
- `kubeadm/`: versioned cluster init, network, and cluster add-on manifests
- `live-config/`: tracked snapshots of active provisioner configuration
- `scripts/`: helper wrappers for repeatable operations

Current roles:

- `192.168.1.44` (`glasslab-PXE-01`): provisioner, bastion, Ansible control host, kubectl admin workstation
- `192.168.1.49` (`cp01`): Kubernetes control plane
- `192.168.1.48` (`node01`): Kubernetes worker and NVIDIA GPU candidate
- `192.168.1.11` (`node02`): Kubernetes worker and active NVIDIA GPU worker

Current cluster state:

- `cp01`, `node01`, and `node02` are PXE-provisioned and reachable by SSH.
- `kubectl` on the provisioner is wired to the live cluster.
- Calico is installed with a non-overlapping pod CIDR of `10.244.0.0/16`.
- Smoke pods were scheduled successfully onto `node01` and `node02` and removed.
- SSH password auth is disabled on the current Kubernetes nodes; provisioner access is still local-password based.
- GPU preflight lives in `ansible/playbooks/prepare-gpu-node.yml`.
- GPU enablement lives in `ansible/playbooks/enable-gpu-node.yml`.
- `node02` runs the NVIDIA 580-open driver stack with `nvidia-smi` working on-host.
- Kubernetes advertises `nvidia.com/gpu=1` on `node02`.
- Package maintenance lives in `ansible/playbooks/maintain-packages.yml` and `docs/package-maintenance.md`.
