# Research Orchestrator Deployment

These manifests define one orchestrator replica with no Kubernetes API token.
The service calls `workflow-api` for bounded execution and stores SQLite WAL,
worktrees, and run artifacts on `glasslab-shared-artifacts`.

The init container maintains a detached checkout of the one approved public
repository. Production rollout still requires:

- a published orchestrator image matching the manifest tag
- live exo reachability from `node05`
- a published evaluation-contract image configured in the workflow-api trusted
  catalog
- a local secret containing a generated operator API token
- a local secret containing the Discord bot token and channel webhook URL when
  Discord is enabled

Discord application, guild, and channel IDs are non-secret values in the
ConfigMap. The bot must be installed in the guild and have View Channel, Send
Messages, Read Message History, Create Public Threads, and Send Messages in
Threads on the configured channel. Administrator is not required.

Do not treat the example Discord secret as deployable.
