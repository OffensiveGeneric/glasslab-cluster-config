# Contributor Access

Glasslab uses separate identities at each trust boundary. Logging into the
gateway does not automatically grant Docker, repository, Kubernetes, or GitHub
package permissions.

| Boundary | Account or role | Granted capability |
| --- | --- | --- |
| Public gateway | personal Unix account | enter the lab network over SSH |
| Provisioner | matching personal Unix account | work in the canonical checkout |
| Canonical checkout | `glasslab` group | read and write the shared repository tree |
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
```

Public keys should be installed on both hosts. Password reuse between the
gateway and provisioner is not the account synchronization mechanism.

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

Provisioner accounts are managed with:

```bash
cd /home/glasslab/cluster-config/ansible
ansible-playbook -i inventory/hosts.yml \
  playbooks/manage-provisioner-contributors.yml \
  -e @/path/to/contributors.local.yml
```

Example local variables:

```yaml
glasslab_contributors:
  - username: denic
    comment: Denise Cakoni
    docker_access: true
    authorized_keys:
      - ssh-ed25519 AAAA... deni-personal
```

Keep the real variables file outside Git. It contains personal public keys and
the explicit list of people receiving root-equivalent Docker access.
