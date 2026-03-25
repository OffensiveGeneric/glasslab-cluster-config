# Provisioner Dependence Close Criteria

This note narrows issue `#3`.

The epic should not stay open as a vague statement that `.44` is still important.

It should stay open only for the specific remaining dependence classes that are still operationally significant.

## What Is Already Good Enough

These parts have improved enough that they should not be described as the main problem anymore:

- `workflow-api` and runner images are on a pullable GHCR path
- non-`node03` scheduling has already been validated
- OpenClaw runtime export no longer assumes one single in-cluster inference endpoint

That means the epic is no longer primarily about node-local image import for the main v2 backend path.

## What Still Keeps The Epic Open

### 1. Break-Glass Import Still Exists

This is acceptable for now, but it should stay explicitly secondary.

The close condition is:

- primary runbooks and real deploy flow use pullable images by default
- manual import is documented only as fallback

### 2. Runtime Materialization Is Still `.44`-Centered

OpenClaw runtime export and apply still rely on the canonical provisioner workflow.

The close condition is not "remove `.44`."

The close condition is:

- runtime export steps are explicit and reviewable
- remote access to `.44` is operationally workable
- backend switching no longer depends on ad hoc source edits

### 3. Secret Material Intentionally Remains Local

This should not block closure forever if the boundary is intentional and backed up.

The close condition is:

- local-only secret posture remains explicit
- encrypted off-host backup exists and is maintained
- secret-local work is not confused with image/runtime portability

### 4. `.44` As Canonical Admin Host Remains By Design

This should not be treated as a failure of the epic by itself.

The close condition is:

- `.44` centrality is documented as intentional
- off-site access to `.44` is workable
- the remaining specialness is operationally boring rather than hidden

## Practical Close Rule

Issue `#3` becomes closeable when:

1. pullable-image paths are the normal path for the active custom services
2. runtime export/apply steps are explicit and no longer depend on hidden local edits
3. local-only secrets are documented and backed up rather than accidental
4. `.44` specialness is reduced to intentional admin-context and secret-local roles, not fragile hidden deployment hacks

## What Should Not Be Required To Close It

Do not require these before calling the epic materially addressed:

- eliminating `.44` as the canonical admin host
- moving secrets into Git
- removing every break-glass path
- replacing the bastion model entirely

Those are separate decisions.

## Bottom Line

The goal is not to make `.44` disappear.

The goal is to make the remaining `.44` dependence explicit, intentional, and boring.

## References

- `provisioner-dependence-inventory.md`
- `image-distribution.md`
- `remote-admin-path.md`
- `openclaw-runtime-portability.md`
