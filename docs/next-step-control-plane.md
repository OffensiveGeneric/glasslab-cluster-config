# Recommended Next Step

Initialize Kubernetes on `cp01` (`192.168.1.49`) and then join `node01`.

Suggested sequence:

1. Run `kubeadm init` on `cp01` with an explicit pod CIDR and advertised address.
2. Copy `/etc/kubernetes/admin.conf` from `cp01` to `/home/glasslab/.kube/config` on `192.168.1.44`.
3. Install a CNI plugin after the control plane is up.
4. Generate a worker join command from `cp01`.
5. Join `node01` to the cluster.
6. Validate `kubectl get nodes -o wide` from `192.168.1.44`.

This preserves the intended architecture while moving the lab from prepared nodes to an actual cluster.
