# Architecture

This lab keeps infrastructure and Kubernetes roles separated.

- `192.168.1.44` (`glasslab-PXE-01`) is the PXE host, bastion, Ansible control machine, Git remote sync point, and kubectl workstation.
- `192.168.1.49` (`cp01`) is the active Kubernetes control plane.
- `192.168.1.48` (`node01`) is the first Kubernetes worker.

Current cluster design:

- Single control plane on dedicated hardware.
- Workers remain separate from the provisioner.
- Pod networking is Calico with `10.244.0.0/16` to avoid overlap with the lab LAN `192.168.1.0/24`.
- Additional workers can be added with the existing PXE + Ansible + `kubeadm join` flow.

Scaling note:

- If you later want multiple control-plane nodes, plan a stable control-plane endpoint or VIP before converting this into an HA control-plane topology.
