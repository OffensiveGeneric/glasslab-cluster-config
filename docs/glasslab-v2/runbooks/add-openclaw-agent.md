# Add An OpenClaw Agent

1. Create a new agent directory under `services/openclaw-config/agents/`.

2. Add two files at minimum:

- `agent.yaml`: role, provider, allowed bindings, and policy profile
- `prompt.md`: concise role instructions and refusal boundaries

3. Update bindings or policy files if the new agent needs a new internal route or a different policy profile.

4. Re-export the tracked OpenClaw config into the cluster.

```bash
cd /home/glasslab/cluster-config
./scripts/export-openclaw-config.sh
```

5. Restart the OpenClaw deployment after the config export.

```bash
kubectl -n glasslab-v2 rollout restart deploy/glasslab-openclaw
```

6. Verify the new config is mounted and the pod starts cleanly.

```bash
kubectl -n glasslab-v2 get pods -l app.kubernetes.io/name=glasslab-openclaw
kubectl -n glasslab-v2 logs deploy/glasslab-openclaw --tail=200
```
