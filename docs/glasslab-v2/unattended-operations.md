# Unattended Operations

OpenClaw cron or scheduled workers can support unattended operation, but only within explicit approval tiers.

## Scheduling role

OpenClaw may own recurring operator-facing tasks such as digests, reminders, and bounded workflow submissions. The backend remains responsible for checking registry membership and approval tiers.

## Approval tiers

- `Tier 1 read-only autonomy`: status checks, artifact summaries, literature digests, and notifications
- `Tier 2 bounded approved workflow execution`: recurring runs for already approved workflows, models, datasets, and runner images
- `Tier 3 explicit human approval required`: infrastructure changes, new workflow families, unreviewed datasets, or any change to execution scope

## Allowed unattended tasks

- nightly literature digest for tracked topics or paper queues
- daily run summary from completed workflow artifacts
- recurring benchmark on a known dataset and approved workflow family
- notify when a workflow run fails or stays pending

## Disallowed unattended tasks

- infrastructure modification
- arbitrary shell execution
- Git mutation or push
- creation of new unapproved workflows
- unrestricted dataset or model changes outside the reviewed registry

## Enforcement rule

Unattended jobs should fail closed. If the request cannot be mapped to an approved workflow ID, approved model list, and approved tier, it should stop and require a human.
