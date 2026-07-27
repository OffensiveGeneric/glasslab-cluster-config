## Scope

- [ ] `area/core`: workflow-api, workflow-registry, run records, experiment submission
- [ ] `area/infra`: Kubernetes, Ansible, storage, images, rollout scripts
- [ ] `area/workload`: runner or workload integration
- [ ] `area/adapter`: WhatsApp, ingress, router, compatibility surfaces
- [ ] `area/docs`: docs-only or contributor guidance

## Contributor Checks

- [ ] I ran `./scripts/check-before-push.sh` or the narrower relevant mode.
- [ ] I updated current docs if this changes the supported operator path.
- [ ] I marked new secondary/compatibility behavior explicitly.
- [ ] I did not rely on `.44` live state unless I checked it from `.44`.

## Live Rollout

- [ ] Not required.
- [ ] Required after merge; rollout path is documented in the PR.
- [ ] Already rolled from `.44` and smoke-tested.
