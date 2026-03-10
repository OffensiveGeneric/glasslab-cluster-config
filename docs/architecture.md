# Architecture

This lab keeps infrastructure and Kubernetes roles separated.

- `192.168.1.44` (`glasslab-PXE-01`) is the PXE host, bastion, Ansible control machine, and kubectl workstation.
- `192.168.1.49` (`cp01`) is the first dedicated control-plane candidate.
- `192.168.1.48` (`node01`) is prepared as a Kubernetes worker candidate only.
- No Kubernetes control plane is initialized yet.

Why this layout stays clean:

- The provisioner remains focused on PXE, inventory, docs, keys, Git, and admin workflows.
- The first control plane is separated from the provisioner, which avoids building an all-in-one box.
- Worker capacity stays independent from management infrastructure.
- Additional control-plane or worker nodes can be added through the same Ansible structure later.

Current readiness:

- `cp01` has containerd, kubeadm, kubelet, and kubectl installed and is ready for `kubeadm init`.
- `node01` has containerd, kubeadm, kubelet, and kubectl installed and is ready for `kubeadm join` after the control plane is initialized.
