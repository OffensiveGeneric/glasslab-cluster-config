# Glasslab v2 Kubernetes Manifests

This tree holds namespace, storage placeholders, messaging, workflow-api, bounded stage-agent services, OpenClaw, secret examples, and ingress placeholders for the v2 stack.

The committed manifests should be read through the session/skill/template model:

- sessions are the primary state object for operator work
- skills are bounded state transitions that update a session in place
- workflow families are execution templates used when a session is ready to run
- OpenClaw should stay the narrow operator surface at the edge

This is the committed manifest tree, not a live state dump.

Use it to understand the intended cluster layout:

- namespaces
- storage and PVC/PV declarations
- service and deployment manifests
- RBAC and priority classes
- secret examples and bootstrap templates

Live `.44` state may still differ because:

- ignored local secret manifests are applied only on the provisioner
- some resources are created or refreshed live before the repo is pulled forward
- runtime bundles and imported images are generated artifacts, not committed source

When in doubt, treat `.44` as the source of live truth and this tree as the source of committed intent.
