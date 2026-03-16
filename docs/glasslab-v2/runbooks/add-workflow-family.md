# Add A Workflow Family

1. Create a new JSON definition under `services/workflow-registry/definitions/` by copying the closest existing entry.

2. Keep the definition explicit:

- set a new `workflow_id`
- declare required inputs
- declare allowed models
- declare one runner image
- declare evaluator type
- declare required and optional artifacts
- set one approval tier

3. Validate the registry definitions locally from the provisioner.

```bash
cd /home/glasslab/cluster-config
./scripts/seed-registry.sh
```

4. Update `workflow-api` tests if the new workflow changes validation or acceptance behavior.

```bash
cd /home/glasslab/cluster-config/services/workflow-api
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

5. Build and publish or import a new `workflow-api` image if the registry content is baked into the image for your current deployment path.

6. Update the deployment image if needed and roll the service.

```bash
kubectl -n glasslab-v2 rollout restart deploy/glasslab-workflow-api
```

7. Verify the new workflow appears in the API.

```bash
kubectl -n glasslab-v2 port-forward svc/glasslab-workflow-api 18081:8080
curl http://127.0.0.1:18081/workflow-families
```
