# Architecture

This lab keeps infrastructure and Kubernetes roles separated.

- `192.168.1.44` (`glasslab-PXE-01`) is the PXE host, bastion, Ansible control machine, and kubectl workstation.
- `192.168.1.48` (`node01`) is prepared as a Kubernetes worker candidate only.
- `control_plane` is an explicit inventory group reserved for the first dedicated control-plane node.
- No Kubernetes control plane is initialized yet.

Why control plane is deferred:

- The provisioner should stay focused on PXE, inventory, docs, keys, and admin workflows.
- A single worker-only node is not a useful Kubernetes cluster.
- The clean next move is to PXE-provision a dedicated control-plane node, bootstrap it with the same Ansible project, then join `node01` as a worker.
