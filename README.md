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
- `192.168.1.48` (`node01`): Kubernetes worker and active NVIDIA GPU worker
- `192.168.1.11` (`node02`): Kubernetes worker and active NVIDIA GPU worker
- `192.168.1.50` (`node03`): Kubernetes worker
- `192.168.1.47` (`node05`): Kubernetes worker
- `192.168.1.51` (`node04`): Kubernetes worker and active NVIDIA GPU worker

Current cluster state:

- `cp01`, `node01`, `node02`, `node03`, `node04`, and `node05` are reachable by SSH and part of the live cluster.
- `kubectl` on the provisioner is wired to the live cluster.
- Calico is installed with a non-overlapping pod CIDR of `10.244.0.0/16`.
- SSH password auth is disabled on the current Kubernetes nodes; provisioner access is still local-password based.
- GPU preflight lives in `ansible/playbooks/prepare-gpu-node.yml`.
- GPU enablement lives in `ansible/playbooks/enable-gpu-node.yml`.
- `node01` runs the NVIDIA stack for its Quadro P4000 and advertises `nvidia.com/gpu=1`.
- `node02` runs the NVIDIA stack for its RTX A4000 and advertises `nvidia.com/gpu=1`.
- `node05` has a visible Quadro K2000 but remains CPU-only because it would require a legacy NVIDIA 470 driver path.
- `node04` runs the NVIDIA stack for its GeForce GTX 1060 6GB and advertises `nvidia.com/gpu=1`.
- Package maintenance lives in `ansible/playbooks/maintain-packages.yml` and `docs/package-maintenance.md`.
