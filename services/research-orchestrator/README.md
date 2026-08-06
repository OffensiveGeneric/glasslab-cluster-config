# Research Orchestrator

This service coordinates Honeydew and Beaker as separate agent runtimes.
It owns durable research state, approvals, policy, job reconciliation, event
history, and report acceptance. It delegates bounded execution to
`workflow-api`; it does not give either agent Kubernetes credentials.

OpenCode remains the live default. An experimental Hermes adapter can be
selected explicitly with:

```text
GLASSLAB_ORCHESTRATOR_AGENT_RUNTIME_BACKEND=hermes
```

That switch is not sufficient for deployment: the image must first contain a
reviewed, pinned Hermes executable and satisfy the isolation gates in
[`../../docs/glasslab-v2/adr/0002-hermes-agent-runtime-pilot.md`](../../docs/glasslab-v2/adr/0002-hermes-agent-runtime-pilot.md).

Local checks:

```bash
python -m pip install -r requirements-dev.txt
PYTHONPATH=. pytest -p no:cacheprovider -q
PYTHONPATH=. python -m app.smoke
```

The smoke path uses scripted OpenCode output, a fake cluster executor, the
repository example evaluation contract, and disabled Discord.

Generic task archives are compiled by Honeydew into a validated TaskSpec and
then mapped by deterministic policy to fixed CPU or GPU workspace profiles.
Use `/task-start` in Discord or `POST /task-bundles/import`; inspect
`GET /task-bundles/{task_id}/preflight` before creating a run.

See [`../../docs/research-orchestrator.md`](../../docs/research-orchestrator.md)
for the architecture, trust boundaries, deployment state, and limitations.
