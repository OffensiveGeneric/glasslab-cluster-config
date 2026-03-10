# GPU Worker Notes

Current status:

- `node02` is the first GPU worker candidate.
- Kubernetes labels mark it as `glasslab.io/gpu-candidate=true` and `glasslab.io/gpu-vendor=nvidia`.
- The node is joined and schedulable as a normal worker.
- Linux does not currently enumerate any NVIDIA PCI device on `node02`, so driver rollout is blocked on hardware or firmware visibility.

Current evidence on `node02`:

- `lspci -nn` does not show any `10de:*` NVIDIA device.
- `/sys/bus/pci/devices/*/vendor` contains no `0x10de` entries.
- `dmidecode -t slot` reports all system slots as `Current Usage: Available`.
- This is not a package-selection problem. The OS does not currently see the card.

Use the GPU preflight playbook:

```bash
cd /home/glasslab/cluster-config/ansible
ansible-playbook playbooks/prepare-gpu-node.yml --limit node02 -K
```

That playbook does three things:

1. installs support packages such as `pciutils`, `mokutil`, and `ubuntu-drivers-common`
2. checks whether Linux can see an NVIDIA PCI device at all
3. refuses driver installation if the GPU is still invisible

When hardware visibility is fixed:

```bash
cd /home/glasslab/cluster-config/ansible
ansible-playbook playbooks/prepare-gpu-node.yml --limit node02 -K -e gpu_driver_install_enabled=true
```

Practical checks before the second run:

- confirm the GPU is fully seated
- confirm any required auxiliary PCIe power is connected
- confirm the BIOS has the slot enabled
- confirm the BIOS display/primary-video setting does not hide the discrete GPU
- confirm Secure Boot policy before attempting NVIDIA driver installation

After the OS sees the GPU and the driver is installed, the next Kubernetes steps are:

1. install NVIDIA container runtime integration on GPU workers
2. deploy the NVIDIA device plugin or GPU Operator
3. add scheduling policy for GPU workloads
