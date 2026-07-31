# Glasslab Access Topology

Use role names rather than IP-derived nicknames when describing the remote
administration path.

| Canonical name | Address | Hostname | Responsibility |
| --- | --- | --- | --- |
| Glasslab | n/a | n/a | The overall lab and project |
| gateway | `glasslab.org` | `glasslab` | Public SSH entry point only |
| provisioner | `192.168.1.44` | `glasslab-PXE-01` | PXE, Ansible, canonical repo, image builds, and `kubectl` |
| control plane | `192.168.1.49` | `cp01` | Kubernetes API and control plane |
| workers | lab LAN addresses | `node01` through `node05` | Kubernetes workloads |

The gateway and provisioner are separate machines:

```text
contributor workstation
        |
        | ssh glasslab-gateway
        v
public gateway at glasslab.org
        |
        | ProxyJump
        v
internal provisioner at 192.168.1.44
        |
        +--> Kubernetes API on cp01
        +--> Ansible management of cluster nodes
```

## SSH Names

Canonical personal aliases:

```bash
ssh glasslab-gateway
ssh glasslab-provisioner
```

Canonical shared-administrator aliases, for exceptional use only:

```bash
ssh glasslab-gateway-admin
ssh glasslab-provisioner-admin
```

The older `glasslab-bastion`, `glasslab-44`, `glasslab-bastion-admin`, and
`glasslab-44-admin` aliases remain compatible. New documentation and scripts
must use the canonical role names.

## Identity Names

`glasslab` is also the legacy shared Unix administrator account on multiple
hosts. It is not a host name in architecture prose. Prefer personal accounts
for normal access and state the shared account explicitly as `the shared
glasslab account` when it is unavoidable.

## Operational Boundaries

- The gateway terminates public SSH access. It is not the canonical repo,
  Ansible controller, PXE host, or Kubernetes workstation.
- The provisioner is the canonical live checkout and cluster administration
  host. It is not publicly reachable without the gateway hop.
- Kubernetes workers are not normal contributor login targets. Research work
  should enter through the orchestrator and bounded job APIs.
- Ansible runs from the provisioner and currently manages the control plane and
  workers. Contributor access on the provisioner is described in
  [contributor-access.md](contributor-access.md).
