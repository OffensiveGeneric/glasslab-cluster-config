# Research Orchestrator

This service coordinates Honeydew and Beaker as separate OpenCode runtimes.
It owns durable research state, approvals, policy, job reconciliation, event
history, and report acceptance. It delegates bounded execution to
`workflow-api`; it does not give either agent Kubernetes credentials.

Local checks:

```bash
python -m pip install -r requirements-dev.txt
PYTHONPATH=. pytest -p no:cacheprovider -q
PYTHONPATH=. python -m app.smoke
```

The smoke path uses scripted OpenCode output, a fake cluster executor, the
repository example evaluation contract, and disabled Discord.

See [`../../docs/research-orchestrator.md`](../../docs/research-orchestrator.md)
for the architecture, trust boundaries, deployment state, and limitations.
