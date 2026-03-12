# Architecture

This lab keeps infrastructure and Kubernetes roles separated.

- `192.168.1.44` (`glasslab-PXE-01`) is the PXE host, bastion, Ansible control machine, Git sync point, and kubectl workstation.
- `192.168.1.49` (`cp01`) is the active Kubernetes control plane.
- `192.168.1.48` (`node01`) is a general Kubernetes worker with a usable NVIDIA Quadro P4000.
- `192.168.1.11` (`node02`) is a Kubernetes worker with a usable NVIDIA RTX A4000.
- `192.168.1.50` (`node03`) is a general Kubernetes worker.
- `192.168.1.47` (`node05`) is a general Kubernetes worker with a legacy Quadro K2000 present but not enabled for CUDA.
- `192.168.1.51` (`node04`) is a Kubernetes worker with an enabled GeForce GTX 1060 6GB.

Current cluster design:

- Single control plane on dedicated hardware.
- Workers remain separate from the provisioner.
- Pod networking is Calico with `10.244.0.0/16` to avoid overlap with the lab LAN `192.168.1.0/24`.
- Additional workers can be added with the existing PXE + Ansible + `kubeadm join` flow.
- GPU workers are managed separately from generic workers through the `gpu_nodes` inventory group.

GPU note:

- `node01`, `node02`, and `node04` are the currently enabled CUDA-capable workers today.
- `node05` has an older Quadro K2000 that Ubuntu 24.04 recommends on the legacy `nvidia-driver-470` branch; it is intentionally left CPU-only for now.
- The current automation entry points are `ansible/playbooks/prepare-gpu-node.yml` and `ansible/playbooks/enable-gpu-node.yml`.

Scaling note:

- If you later want multiple control-plane nodes, plan a stable control-plane endpoint or VIP before converting this into an HA control-plane topology.
