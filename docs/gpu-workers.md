# GPU Worker Notes

Current status:

- `node02` is the first active GPU worker.
- `node01` is now tracked as an NVIDIA GPU candidate.
- `cp01` also has a visible NVIDIA card, but it remains a control-plane host and is not a workload target.
- Kubernetes labels mark `node02` as `glasslab.io/gpu-candidate=true` and `glasslab.io/gpu-vendor=nvidia`.
- The node is joined and schedulable as a normal worker.
- Linux enumerates the discrete GPU as `GA104GL [RTX A4000] [10de:24b0]` on `node02`.
- `nvidia-smi -L` works on the host.
- Kubernetes advertises `nvidia.com/gpu=1` on `node02`.

Current visible NVIDIA hardware across the cluster:

- `cp01`: `Quadro K620 [10de:13bb]`
- `node01`: `Quadro P4000 [10de:1bb1]` plus `NVS 310 [10de:107d]`
- `node02`: `RTX A4000 [10de:24b0]`

CUDA-capable summary:

- `node02` is the only node with a validated CUDA runtime today.
- `node01` has a CUDA-capable `Quadro P4000` present and is a reasonable next GPU-enable target.
- `cp01` has an older CUDA-capable `Quadro K620`, but it should stay out of general GPU scheduling unless you deliberately repurpose control-plane hardware.
- CUDA core counts for `cp01` and `node01` are inferred from GPU model specs, not yet validated by `nvidia-smi` on those hosts.

What is pinned:

- driver package: `nvidia-driver-580-open`
- device plugin image: `nvcr.io/nvidia/k8s-device-plugin:v0.18.2`
- runtime class: `nvidia`

Enablement flow now tracked in Git:

1. preflight hardware visibility with `ansible/playbooks/prepare-gpu-node.yml`
2. enable the driver + container runtime with `ansible/playbooks/enable-gpu-node.yml`
3. apply the pinned Kubernetes runtime and device-plugin manifests in `kubeadm/`
4. verify GPU scheduling with `kubeadm/nvidia-smi-test.yaml`

Host enablement:

```bash
cd /home/glasslab/cluster-config/ansible
ansible-playbook playbooks/enable-gpu-node.yml --limit node02 -K \
  -e gpu_driver_install_enabled=true \
  -e gpu_nvidia_container_toolkit_enabled=true
```

Kubernetes side:

```bash
kubectl apply -f /home/glasslab/cluster-config/kubeadm/nvidia-runtimeclass.yaml
kubectl apply -f /home/glasslab/cluster-config/kubeadm/nvidia-device-plugin.yaml
kubectl apply -f /home/glasslab/cluster-config/kubeadm/nvidia-smi-test.yaml
```

GPU workloads should request:

- `resources.limits.nvidia.com/gpu`
- `runtimeClassName: nvidia`
