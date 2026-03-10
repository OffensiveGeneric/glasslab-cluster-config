# GPU Worker Notes

Current status:

- `node02` is the first GPU worker candidate.
- Kubernetes labels mark it as `glasslab.io/gpu-candidate=true` and `glasslab.io/gpu-vendor=nvidia`.
- The node is joined and schedulable as a normal worker.
- Linux enumerates the discrete GPU as `GA104GL [RTX A4000] [10de:24b0]` on `node02`.
- `nvidia-smi -L` works on the host.
- Kubernetes now advertises `nvidia.com/gpu=1` on `node02`.

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
