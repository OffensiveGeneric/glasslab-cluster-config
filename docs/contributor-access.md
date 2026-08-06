# Contributor Access

Glasslab uses separate identities at each trust boundary. Logging into the
gateway does not automatically grant Docker, repository, Kubernetes, or GitHub
package permissions.

| Boundary | Account or role | Granted capability |
| --- | --- | --- |
| Public gateway | personal Unix account | enter the lab network over SSH |
| Provisioner | matching personal Unix account | work in the canonical checkout |
| Canonical checkout | `glasslab` group | inspect and operate the live checkout when authorized |
| Local Docker daemon | `docker` group, explicitly approved | build and test images on the provisioner |
| GitHub repository | personal GitHub collaborator | push branches and trigger workflows |
| GHCR publication | GitHub Actions `GITHUB_TOKEN` | publish approved service images |
| Kubernetes administration | administrator workflow | not implied by contributor access |

The `docker` group is root-equivalent on the provisioner. It is appropriate
only for the currently trusted contributors and must not become the default
for future untrusted accounts.

## Normal Connection Path

Each contributor should define local SSH aliases equivalent to:

```sshconfig
Host glasslab-gateway
  HostName glasslab.org
  User <personal-user>
  IdentityFile ~/.ssh/<personal-key>

Host glasslab-provisioner
  HostName 192.168.1.44
  User <same-personal-user>
  IdentityFile ~/.ssh/<personal-key>
  ProxyJump glasslab-gateway

Host glasslab-exo17
  HostName 192.168.1.17
  User <same-personal-user>
  IdentityFile ~/.ssh/<personal-key>
  ProxyJump glasslab-gateway

Host glasslab-exo18
  HostName 192.168.1.18
  User <same-personal-user>
  IdentityFile ~/.ssh/<personal-key>
  ProxyJump glasslab-gateway
```

Public keys should be installed on both hosts. Password reuse between the
gateway and provisioner is not the account synchronization mechanism.

Password retirement is staged. Existing passwords remain available until the
contributor has demonstrated key-only login from every computer they actively
use. An administrator then changes the account's committed
`password_locked` setting and reapplies the identity playbook.

## Development Checkouts

Contributors must develop in separate clones under their own home directories.
Do not use `/home/glasslab/cluster-config` as a shared development worktree;
simultaneous branches, builds, and generated files would interfere with each
other and with live rollouts.

After authenticating the GitHub CLI, create a personal checkout:

```bash
cd ~
gh repo clone OffensiveGeneric/glasslab-cluster-config cluster-config
cd ~/cluster-config
git switch -c <personal-feature-branch>
```

The checkout under `/home/glasslab/cluster-config` remains the clean canonical
apply and validation tree.

## Building And Publishing Images

After an administrator grants `docker` membership, start a new SSH login before
testing it:

```bash
id
docker info
```

Local Docker access is for builds and checks. The normal GHCR publication path
is GitHub Actions, so contributors do not need a shared GHCR token on `.44`.

Authenticate the GitHub CLI as your own GitHub account:

```bash
gh auth login --web
```

Then request a repository-owned build:

```bash
./scripts/request-service-image.sh workflow-api
./scripts/request-service-image.sh research-orchestrator
```

The caller must be a repository collaborator. The workflow records who
requested the build, builds from committed `main`, and publishes with its
short-lived `GITHUB_TOKEN`.

## Provisioning Accounts

Gateway, provisioner, and exo personal accounts are managed from one committed
identity ledger. See [Identity Management](identity-management.md) for the
role model, revocation procedure, and recovery boundary.

Run from the canonical checkout on the provisioner:

```bash
cd /home/glasslab/cluster-config
./scripts/manage-identities.sh check
./scripts/manage-identities.sh apply
```

Public keys and role assignments live in
`ansible/group_vars/identity_hosts.yml`. Private keys, passwords, and access
tokens must not be added there.
