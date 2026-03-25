# Provisioner Dependence Inventory

This note narrows issue `#3`.

The current problem is not that everything still depends on `.44` equally.

Different dependencies have different fixes.

## Current dependency classes

### 1. Pullable image dependency

This is the part that has improved the most.

Current state:

- `workflow-api` and the runner images now have a private GHCR path
- the old `.44` import helper remains as a fallback, not the preferred steady-state path

Reference:

- `docs/glasslab-v2/image-distribution.md`

Remaining gap:

- treat manual `ctr import` as break-glass only
- keep validating non-`node03` scheduling so the cluster does not silently drift back into import-era assumptions

### 2. Runtime export dependency

This has improved, but it is not gone.

Current state:

- the OpenClaw runtime export can now target reviewed internal inference backends without source-YAML edits
- `.44` is still the canonical apply and validation host

Reference:

- `docs/glasslab-v2/openclaw-runtime-portability.md`

Remaining gap:

- the runtime export/apply flow is still operationally centered on `.44`

### 3. Secret material dependency

This is intentionally still `.44`-special.

Current state:

- live secret manifests remain local-only on `.44`
- encrypted off-host backup exists, but Git is not the source of truth for secrets

Reference:

- `docs/glasslab-v2/secrets-and-dr.md`

Remaining gap:

- this is a DR and secret-management question, not an image-distribution question

### 4. Live admin context dependency

This is also still `.44`-special by design.

Current state:

- `.44` is the canonical `kubectl` admin workstation
- live validation claims still need to be grounded there

Remaining gap:

- do not confuse this with image portability
- removing it would be a separate operator-access and bastion decision

## Practical conclusion

Issue `#3` should not be treated as one giant migration.

The current realistic near-term goal is:

1. keep pullable-image paths as the default
2. keep manual import as break-glass only
3. keep secrets local-only for now, but backed up
4. keep `.44` as the apply/validation host until there is a deliberate operator-access replacement

That is less glamorous than “remove `.44` dependence,” but it is a more accurate description of the real state and the actual next work.
