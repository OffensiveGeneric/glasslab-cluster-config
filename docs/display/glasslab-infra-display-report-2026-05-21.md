# Glasslab Infra Display Report: 2026-05-21

This report is meant to feed a physical wall display or generated network
diagram for Glasslab.

It records the state observed from the lab laptop at `192.168.1.36` on
2026-05-21. It deliberately separates observed reachability from repo-declared
intended roles.

## Observed Now

Observed from the lab LAN:

| IP | Name | Observed state | Role |
| --- | --- | --- | --- |
| `192.168.1.100` | lab gateway | reachable | default route for lab LAN |
| `192.168.1.2` | `projector-san` | reachable | OptiPlex 990 projector machine, Xubuntu GUI, `lightdm` active |
| `192.168.1.12` | Mac service host | reachable by ping | documented OpenClaw/chat/ranker host, SSH key not accepted from this laptop during this check |
| `192.168.1.19` | exo worker Mac | reachable by ping | documented exo worker, SSH key not accepted from this laptop during this check |
| `192.168.1.21` | `CS60138N73111` | reachable by SSH | exo master Mac, Ollama host |
| `192.168.1.23` | `CS60140N7311` | reachable by SSH | heavier Mac inference host |
| `192.168.1.207` | g-nas | reachable | NFS/shared storage target |
| `192.168.1.44` | `glasslab-PXE-01` | unreachable | PXE/provisioner/canonical apply host |
| `192.168.1.47` | `node05` | unreachable | Kubernetes worker in repo docs |
| `192.168.1.48` | `node01` | unreachable | Kubernetes worker in repo docs |
| `192.168.1.49` | `cp01` | unreachable | Kubernetes control plane in repo docs |
| `192.168.1.50` | `node03` | unreachable | Kubernetes worker in repo docs |
| `192.168.1.51` | `node04` | unreachable | Kubernetes worker in repo docs |
| `192.168.1.11` | `node02` | unreachable | Kubernetes GPU worker in repo docs |

Implication:

- The live Kubernetes cluster could not be validated from `.44` because `.44`
  is currently unreachable from both the lab laptop and the public bastion path.
- The current physical display should show the Kubernetes/PXE plane as
  `down/unverified`, not as healthy.
- The projector machine itself is up and suitable as the wall-display endpoint.

## Current Display Endpoint

| Field | Value |
| --- | --- |
| IP | `192.168.1.2` |
| Hostname | `projector-san` |
| OS role | Xubuntu projector/display machine |
| Network | `eno1`, `192.168.1.2/24` |
| GUI state | `lightdm` active |
| Existing display asset | `/home/glasslab/Pictures/glasslab-network-topology.svg` |

## Intended Infra Roles From Repo

| IP | Name | Intended role |
| --- | --- | --- |
| `192.168.1.44` | `glasslab-PXE-01` | PXE, TFTP, HTTP provisioning, bastion, Ansible, kubectl, canonical repo checkout |
| `192.168.1.49` | `cp01` | Kubernetes control plane |
| `192.168.1.48` | `node01` | Kubernetes worker, documented GPU candidate |
| `192.168.1.11` | `node02` | Kubernetes worker, documented RTX A4000 GPU host |
| `192.168.1.50` | `node03` | Kubernetes worker |
| `192.168.1.51` | `node04` | Kubernetes worker, documented GTX 1060 GPU host |
| `192.168.1.47` | `node05` | Kubernetes worker, documented landing area for several v2 services |
| `192.168.1.207` | g-nas | NFS target for shared datasets and artifacts |
| `192.168.1.12` | Mac service host | documented OpenClaw/chat/ranker host |
| `192.168.1.21` | Mac service host | exo master and Ollama host |
| `192.168.1.19` | Mac service host | exo worker |
| `192.168.1.23` | Mac service host | heavier inference host |

## Intended Service Map From Repo

The repo currently defines the primary v2 command path as:

1. `whatsapp-gateway`
2. `research-ingress`
3. `research-command-router`
4. `workflow-api`
5. Kubernetes Jobs, artifacts, evaluation, reports

Repo-declared service relationships:

| Service | Namespace / host | Repo-declared role |
| --- | --- | --- |
| `glasslab-whatsapp-gateway` | `glasslab-v2` | WhatsApp/control-shell ingress |
| `glasslab-research-ingress` | `glasslab-v2` | command normalization and intake boundary |
| `glasslab-research-command-router` | `glasslab-v2` | deterministic command router |
| `glasslab-workflow-api` | `glasslab-v2`, pinned to `node05` in manifests | session state, run planning, job submission, artifact handoff |
| `glasslab-postgres` | `glasslab-v2` | durable workflow state |
| `glasslab-minio` | `glasslab-v2` | object-style artifact/source storage where needed |
| `glasslab-nats` | `glasslab-v2`, pinned to `node05` in manifests | event/message substrate |
| `glasslab-interpretation-agent` | `glasslab-v2` | interpretation-stage helper, configured against `.21` Ollama endpoint |
| `glasslab-intake-agent` | `glasslab-v2` | intake helper, currently disabled in workflow-api config |
| `glasslab-assessment-agent` | `glasslab-v2` | assessment helper, currently disabled in workflow-api config |
| `glasslab-design-agent` | `glasslab-v2` | design helper, currently disabled in workflow-api config |
| `.12` Ollama | `192.168.1.12:11434` | coding notebook model target in workflow-api config |
| `.12` ranker | `192.168.1.12:8181` | ranker target in workflow-api config, ranker currently disabled |
| `.207` NFS | `192.168.1.207` | `glasslab-shared-datasets` and `glasslab-shared-artifacts` backing store |

## Diagram Source

Use this Mermaid block as the source for an image generator or diagram renderer.

```mermaid
flowchart LR
  operator[Operator phone / WhatsApp] --> wg[whatsapp-gateway]
  wg --> ingress[research-ingress]
  ingress --> router[research-command-router]
  router --> api[workflow-api]
  api --> pg[(Postgres)]
  api --> minio[(MinIO)]
  api --> nats[(NATS)]
  api --> jobs[Kubernetes Jobs]
  jobs --> datasets[(NFS datasets PVC<br/>192.168.1.207)]
  jobs --> artifacts[(NFS artifacts PVC<br/>192.168.1.207)]
  api -. coding notebook .-> mac12[192.168.1.12<br/>Ollama qwen2.5-coder:14b]
  api -. interpretation .-> mac21[192.168.1.21<br/>Ollama/exo master]
  api -. heavier inference .-> mac23[192.168.1.23<br/>Mac inference host]

  subgraph LabLAN[Lab LAN 192.168.1.0/24]
    gateway[192.168.1.100<br/>gateway]
    projector[192.168.1.2<br/>projector-san<br/>display endpoint]
    provisioner[192.168.1.44<br/>glasslab-PXE-01<br/>PXE + kubectl + canonical repo<br/>OBSERVED DOWN]
    nas[192.168.1.207<br/>g-nas NFS<br/>OBSERVED UP]
  end

  subgraph Kubernetes[Documented Kubernetes plane<br/>OBSERVED DOWN/UNVERIFIED 2026-05-21]
    cp01[192.168.1.49 cp01<br/>control plane]
    node01[192.168.1.48 node01<br/>worker/GPU candidate]
    node02[192.168.1.11 node02<br/>worker RTX A4000]
    node03[192.168.1.50 node03<br/>worker]
    node04[192.168.1.51 node04<br/>worker GTX 1060]
    node05[192.168.1.47 node05<br/>worker/service landing area]
  end

  subgraph Macs[Mac service hosts]
    mac12
    mac19[192.168.1.19<br/>exo worker]
    mac21
    mac23
  end

  provisioner -. manages .-> Kubernetes
  Kubernetes --> nas
  projector -. displays .-> LabLAN
```

## Visual Encoding Recommendation

For a physical wall diagram:

- green: observed reachable now
- red: observed unreachable now
- amber: reachable but not fully validated
- blue: intended Kubernetes/service control path
- purple: external Mac model-service hosts
- gray dashed border: repo-declared but not live-validated

