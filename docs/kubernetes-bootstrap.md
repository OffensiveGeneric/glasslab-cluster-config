# Kubernetes Bootstrap Notes

Current live cluster:

- Control plane: `cp01` (`192.168.1.49`)
- Workers: `node01` (`192.168.1.48`), `node02` (`192.168.1.11`)
- Kubernetes version: `v1.35.2`
- Pod CIDR: `10.244.0.0/16`
- Service CIDR: `10.96.0.0/12`
- CNI: Calico operator with a custom `Installation` resource

Why this pod CIDR:

- The lab LAN is `192.168.1.0/24`.
- Calico's common `192.168.0.0/16` example would overlap the LAN.
- `10.244.0.0/16` avoids that conflict.

Bootstrap summary:

1. `kubeadm init` was run on `cp01` using `kubeadm/cp01-init.yaml`.
2. `/etc/kubernetes/admin.conf` was copied to `/home/glasslab/.kube/config` on the provisioner.
3. Calico CRDs and the operator were installed from pinned upstream `v3.31.4` manifests.
4. The local `kubeadm/calico-installation.yaml` resource was applied.
5. `node01` and `node02` joined successfully via `kubeadm join`.
6. Smoke pods scheduled successfully on `node01` and `node02` and were removed.
7. `node02` was labeled as the first GPU candidate worker.
8. NVIDIA driver/runtime enablement completed on `node02`.
9. The pinned NVIDIA device plugin now advertises `nvidia.com/gpu=1` on `node02`.
