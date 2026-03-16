# Ingress

This directory holds future internal-only ingress or reverse-proxy examples for Glasslab v2.

Current posture:

- no live ingress resources are deployed for `glasslab-v2`
- all current v2 Services are `ClusterIP`
- port-forwarding remains acceptable for bring-up and admin tasks

Example:

- `10-internal-services.example.yaml` shows the intended future direction for operator-facing services only

Do not use this directory to publish public endpoints.
