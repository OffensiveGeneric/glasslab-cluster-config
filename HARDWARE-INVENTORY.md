# Glasslab Hardware Inventory

**Live LAN snapshot:** 2026-08-11, collected from the provisioner on
`192.168.1.44`, Kubernetes, authenticated SSH, and the DHCP lease view.

This is the visible hardware index for the lab. It is deliberately split into
managed compute, storage and network appliances, and connected devices that do
not yet have an approved management path. Do not treat an unauthenticated
network scan as proof of a machine's CPU, RAM, or disk specifications.

CPU counts below are logical CPUs. `Free` is the root/APFS filesystem space at
collection time, not allocatable Kubernetes capacity. GPU entries distinguish
physical hardware from GPUs currently advertised to Kubernetes.

## Managed Compute

| Name | Address | Role | Model | CPU | RAM | Local storage and free space | GPU | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `glasslab-gateway` | `192.168.1.4`, public `glasslab.org` | Public SSH gateway | Dell OptiPlex 990 | Intel Core i7-2600, 8 logical CPUs | 7.7 GiB | 465.8 GB Seagate ST95005620AS; 415 GB root free | 2x AMD Radeon HD 7450 | Reachable |
| `glasslab-PXE-01` | `192.168.1.44` | Provisioner, PXE, Ansible, `kubectl` | Dell Precision Tower 5810 | Intel Xeon E5-1607 v3, 4 logical CPUs | 31.3 GiB | 111.8 GB Crucial BX500; 5.1 GB root free | NVIDIA Quadro K620 | Reachable; root disk needs attention |
| `cp01` | `192.168.1.49` | Kubernetes control plane | Dell Precision Tower 5810 | Intel Xeon E5-1607 v3, 4 logical CPUs | 23.4 GiB | 465.8 GB Samsung SSD 860; 420 GB root free | NVIDIA Quadro K620; not schedulable | Ready |
| `node01` | `192.168.1.48` | Kubernetes GPU worker | Dell Precision T5600 | 2x Intel Xeon E5-2603, 8 logical CPUs | 62.8 GiB | 2x 465.8 GB WDC WD5000HHTZ-7 in `md0`; 343 GB root free | Quadro P4000 plus NVS 310; `nvidia.com/gpu=1` | Ready |
| `node02` | `192.168.1.11` | Kubernetes GPU worker | Dell Precision T5600 | 2x Intel Xeon E5-2603, 8 logical CPUs | 62.8 GiB | 465.8 GB WDC WD5000HHTZ-7; 285 GB root free | RTX A4000; `nvidia.com/gpu=1` | Ready |
| `node03` | `192.168.1.50` | Kubernetes worker | Not collected | Kubernetes last reported 4 CPUs | Kubernetes last reported 31.3 GiB | Prior snapshot: 465.8 GB root disk | Not collected | **Unreachable from provisioner; Kubernetes `Ready=Unknown`** |
| `node04` | `192.168.1.51` | Kubernetes GPU worker | Dell Precision Tower 5810 | Intel Xeon E5-1607 v3, 4 logical CPUs | 31.3 GiB | 931.5 GB Seagate ST1000DM003; 818 GB root free | GeForce GTX 1060 6 GB; `nvidia.com/gpu=1` | Ready |
| `node05` | `192.168.1.47` | Kubernetes worker | Dell Precision T3610 | Intel Xeon E5-1620 v2, 8 logical CPUs | 31.3 GiB | 119.2 GB Samsung PM83; 50 GB root free | Quadro K2000; not schedulable | Ready |
| `archimedes` | `192.168.1.31` | Kubernetes GPU worker | Dell Precision 5820 Tower X-Series | Intel Core i9-9820X, 20 logical CPUs | 62.5 GiB | 476.9 GB Micron SATA, 476.9 GB Lite-On NVMe, 9.1 TB Seagate ST10000NM0086; 8.6 TB root free | GeForce RTX 3080 LHR; `nvidia.com/gpu=1` | Ready |

## Standalone Mac Inference Hosts

These Macs are on the Glasslab LAN but are **not Kubernetes nodes**. Their
Apple GPUs are available to their local model-serving runtimes, not through
`nvidia.com/gpu`.

| DHCP name | Address | Model number | CPU/GPU | RAM | Internal storage and free space | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `CS60137N7311` | `192.168.1.17` | Mac Studio `Mac16,9`, `Z1CD0017ZLL/A` | Apple M4 Max, 16 cores (12P + 4E), integrated Apple GPU | 64 GB | 1.0 TB internal; 649 GiB free | Reachable; exo host |
| `CS60138N73111` | `192.168.1.18` | Mac Studio `Mac16,9`, `Z1CD0017ZLL/A` | Apple M4 Max, 16 cores (12P + 4E), integrated Apple GPU | 64 GB | 1.0 TB internal; 801 GiB free | Reachable; exo host |
| Unnamed Mac Studio | `192.168.1.14` | Mac Studio `Mac16,9`, `Z1CD0017ZLL/A` | Apple M4 Max, 16 cores (12P + 4E), integrated Apple GPU | 64 GB | 1.0 TB internal; 890 GiB free | Reachable; not in Kubernetes |

## Shared Storage And Network Appliances

| Device | Address | Identified hardware/service | Capacity or role | Status |
| --- | --- | --- | --- | --- |
| `g-nas`, management interface | `192.168.1.13` | Synology DSM/NFS/SMB services | Same storage server as `.207`; exact model/RAM require DSM admin access | Reachable |
| `g-nas`, data interface | `192.168.1.207` | Synology DSM/NFS/SMB services | NFS export `192.168.1.207:/volume1/backup`: 11 TB total, 1.9 TB used, 9.0 TB free | Reachable |
| LAN gateway | `192.168.1.100` | Cisco device | Default router/gateway; not compute capacity | Reachable |
| Network switch/controller | `192.168.1.10` | Hewlett Packard Enterprise HTTP management service | Network appliance; not compute capacity | Reachable |
| Netgear device | `192.168.1.3` | Netgear MAC; no management service observed | Network appliance or unmanaged endpoint; no hardware facts available | Reachable |

The shared `glasslab-v2` Kubernetes volumes are NFS-backed by `g-nas` at
`.207`:

- `shared-datasets`: 2 TiB claim
- `shared-artifacts`: 3 TiB claim
- actual mounted shared pool: 11 TB total, 9.0 TB free at collection time

## Connected But Not Yet Manageable

These devices were visible in the live scan or DHCP leases, but no approved
credentials or management API currently allows hardware collection. They are
listed so that absence of specifications is visible rather than silently
forgotten.

| DHCP name or observed identity | Address | Observed type | What is missing |
| --- | --- | --- | --- |
| Unnamed wired endpoint | `192.168.1.5` | Active on the LAN; no scanned management port | Identity, reachability, and management path |
| `CS60140N7311` | `192.168.1.8` | Wired Apple-class device; no scanned management port | Remote-management path and hardware facts |
| `CS60141N7311` | `192.168.1.9` | Wired macOS host with SSH and RTSP | Approved account/key and hardware facts |
| `CS60123N7311` | `192.168.1.29` | Wireless DHCP client; did not answer the active scan | Reachability and management path |
| Unnamed wireless client | `192.168.1.27` | Wireless DHCP client; did not answer the active scan | Identity, reachability, and management path |
| `Gr66ss-secondlife` | `192.168.1.36` | Personal wireless workstation lease | Not lab capacity; exclude from resource planning |
| Unnamed Ubuntu host | `192.168.1.185` | Netgear MAC, OpenSSH 8.9 on Ubuntu | Host owner/account and hardware facts; may be the projector machine, but that is **not confirmed** |

## Refresh Procedure

Run this from the provisioner whenever hardware changes. Use the `glasslab`
Ansible account for cluster nodes because its provisioner-to-node key is not
available to ordinary personal accounts:

```bash
cd /home/glasslab/cluster-config/ansible
sudo -u glasslab HOME=/home/glasslab \
  ansible k8s_nodes -e ansible_become=false -m setup \
  -a 'filter=ansible_product_*' -o
sudo -u glasslab HOME=/home/glasslab \
  ansible k8s_nodes -e ansible_become=false -m setup \
  -a 'filter=ansible_processor*' -o
sudo -u glasslab HOME=/home/glasslab \
  ansible k8s_nodes -e ansible_become=false -m setup \
  -a 'filter=ansible_memtotal_mb' -o
```

Also verify live Kubernetes resource advertisements and NFS capacity:

```bash
kubectl get nodes
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{" gpu="}{.status.allocatable.nvidia\.com/gpu}{"\n"}{end}'
kubectl -n glasslab-v2 exec deployment/glasslab-research-orchestrator -- df -h /mnt/artifacts
```

After each refresh, update this file with the collection date, retain unknowns
as unknowns, and add a managed inventory entry before treating a device as
available lab capacity.
