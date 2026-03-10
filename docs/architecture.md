# Architecture

This lab keeps infrastructure and Kubernetes roles separated.

- `192.168.1.44` (`glasslab-PXE-01`) is the PXE host, bastion, Ansible control machine, Git remote sync point, and kubectl workstation.
- `192.168.1.49` (`cp01`) is the active Kubernetes control plane.
- `192.168.1.48` (`node01`) is a general Kubernetes worker.
- `192.168.1.11` (`node02`) is a Kubernetes worker reserved as the first GPU candidate.

Current cluster design:

- Single control plane on dedicated hardware.
- Workers remain separate from the provisioner.
- Pod networking is Calico with `10.244.0.0/16` to avoid overlap with the lab LAN `192.168.1.0/24`.
- Additional workers can be added with the existing PXE + Ansible + `kubeadm join` flow.

GPU note:

- `node02` is labeled as a GPU candidate in Kubernetes and inventory.
- The base OS is joined and schedulable.
- NVIDIA driver/runtime enablement is intentionally deferred until after cluster bring-up.
- Current package-free PCI probes did not expose an NVIDIA device to the OS yet, so hardware visibility still needs confirmation on `node02` before driver rollout.

Scaling note:

- If you later want multiple control-plane nodes, plan a stable control-plane endpoint or VIP before converting this into an HA control-plane topology.
