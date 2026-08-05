# Identity Management

Glasslab uses Ansible-managed local accounts. This is deliberately smaller
than LDAP: three current contributors and four identity-bearing machines do
not justify a directory service, its availability dependency, or another
credential store.

```text
personal SSH key
       |
       v
public gateway (glasslab.org)
       |
       +--> provisioner (.44): Git, Ansible, kubectl, optional Docker
       |
       +--> exo17 / exo18: personal shell, shared exo worktree

Kubernetes workers: no personal shell accounts
Kubernetes API: separate RBAC boundary
GitHub/GHCR: personal GitHub identity and GitHub Actions
```

## Source Of Truth

The account ledger is
`ansible/group_vars/identity_hosts.yml`. It records personal public keys,
target machine classes, and roles. Public keys are not credentials and are
committed so access can be reconstructed. Private keys and passwords are never
stored in the repository.

The inventory defines these identity scopes:

| Scope | Machines | Purpose |
| --- | --- | --- |
| `gateway` | `glasslab.org` | Public SSH entry only |
| `provisioner` | `192.168.1.44` | Repo, Ansible, builds, and cluster operations |
| `exo` | `192.168.1.17`, `192.168.1.18` | Distributed model-serving development |

The Kubernetes nodes are intentionally excluded. Interactive access to them
continues through the provisioner's `clusteradmin` automation identity.

## Roles

| Role | Effect |
| --- | --- |
| `lab_contributor` | Personal gateway login and provisioner `glasslab` group |
| `exo_contributor` | Personal exo login and `glasslab-exo` shared-worktree group |
| `container_builder` | Provisioner `docker` group; this is root-equivalent |
| `infrastructure_admin` | `sudo` plus an audited passwordless sudoers entry |

Roles only take effect where they make sense. For example,
`container_builder` does not add a group on the gateway or Macs.

The legacy shared `glasslab` account is not in the personal-account ledger. It
is retained as a service owner and break-glass path while remaining software is
migrated. It is not the normal contributor login.

## Apply Changes

Run identity changes from the canonical checkout on the provisioner. Connect
with agent forwarding so Ansible can use the operator's personal key for the
gateway and exo hosts.

```bash
ssh glasslab-provisioner
cd /home/glasslab/cluster-config
./scripts/manage-identities.sh check
./scripts/manage-identities.sh apply
```

The play runs one host at a time. It sets the exact approved SSH keys and role
groups, enforces each account's staged password-lock setting, validates sudoers
and sshd configuration, and keeps exo shared files group-writable. A second
`check` run should report no changes except where a platform tool cannot report
idempotence.

## Add Or Change A Contributor

1. Obtain the contributor's SSH public key through an authenticated channel.
2. Add a unique user record to `glasslab_identity_users` and its username to
   `glasslab_identity_managed_usernames`.
3. Assign only required targets and roles.
4. Run the check command, review the diff, then apply.
5. Initially set `password_locked: false` when adopting an account that
   already uses password authentication.
6. Have the contributor verify each intended SSH alias and run `id`.
7. Have the contributor force a key-only test from every active client:

   ```bash
   ssh -o PreferredAuthentications=publickey \
     -o PasswordAuthentication=no <alias>
   ```

8. After those tests are recorded, change `password_locked` to `true` in a
   separate reviewed change and apply again.

Do not accept a private key, add a shared password, or put a GitHub token in
Ansible variables. Installing a public key is not sufficient evidence that the
contributor's current SSH client possesses and offers the matching private key.

## Revoke Access

Set the user's `state` to `disabled`; do not delete the ledger entry. Apply the
playbook. On Linux this locks the password, changes the shell to `nologin`,
removes supplementary role groups, and removes `authorized_keys`. On macOS it
changes the shell to `/usr/bin/false`, removes supplementary role groups, and
removes `authorized_keys`. Home directories and audit evidence are preserved.

After revocation, separately remove repository access in GitHub and terminate
any active Kubernetes credentials. Unix, GitHub, and Kubernetes remain
intentional separate trust boundaries.

## Recovery

The personal infrastructure administrator and the legacy `glasslab` account
are the current independent administrative paths. Add Mike's personal key as a
second `infrastructure_admin` record before retiring the shared account.
Back up the provisioner's local secrets and SSH recovery material through the
planned encrypted off-host backup path; Git only reconstructs public identity
policy.
