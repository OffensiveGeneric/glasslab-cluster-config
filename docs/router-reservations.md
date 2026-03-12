# Router Reservations

Canonical DHCP reservation list for the Glasslab lab.

| IP | MAC | Hostname | Status | Notes |
| --- | --- | --- | --- | --- |
| `192.168.1.44` | `18:66:da:16:25:9d` | `glasslab-PXE-01` | active | provisioner, bastion, Ansible control host |
| `192.168.1.49` | `18:66:da:23:44:38` | `cp01` | active | Kubernetes control plane |
| `192.168.1.48` | `90:b1:1c:90:22:50` | `node01` | active | Kubernetes worker |
| `192.168.1.11` | `90:b1:1c:90:ad:18` | `node02` | active | Kubernetes worker, NVIDIA RTX A4000 |
| `192.168.1.50` | `18:66:da:23:12:05` | pending | provisioning | currently in PXE/autoinstall flow |
| `192.168.1.51` | `18:66:da:24:44:de` | pending | PXE seen | currently on early PXE path |

Update rule:

- keep this file as the canonical router reservation source
- replace `pending` with the final hostname once the node finishes install and joins the inventory
