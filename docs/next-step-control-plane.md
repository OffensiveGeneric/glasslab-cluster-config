# Recommended Next Step

Initial bootstrap is complete.

Suggested next steps:

1. Keep DHCP reservations fixed so `cp01` stays `192.168.1.49`, `node01` stays `192.168.1.48`, and `node02` stays `192.168.1.11`.
2. Remove the temporary debug SSH/password allowances from the PXE autoinstall profiles once you no longer need them.
3. Confirm GPU hardware visibility on `node02`, then standardize the NVIDIA driver and container runtime integration through Ansible.
4. Decide the next cluster primitives you want to standardize, such as ingress, software load balancing, and storage.
5. Add more worker nodes by PXE-provisioning them, bootstrapping with Ansible, and joining them from `cp01`.
6. If you intend to add more control-plane nodes later, introduce a proper stable control-plane endpoint before doing so.
