# Recommended Next Step

Provision one more Ubuntu node as the first dedicated control-plane machine.

Suggested sequence:

1. PXE-provision the new host so it receives the same cluster SSH key.
2. Add the new host to `ansible/inventory/hosts.yml` under the `control_plane` group.
3. Run `scripts/bootstrap-control-plane.sh` from `192.168.1.44` to apply Kubernetes prerequisites.
4. Run `kubeadm init` on the dedicated control-plane node.
5. Copy `admin.conf` back to `/home/glasslab/.kube/config` on `192.168.1.44`.
6. Generate a worker join command from the control plane and join `node01`.

This preserves the intended architecture and avoids turning the provisioner into a cluster node.
