# Roll Back Glasslab v2

1. Log into the provisioner and move to the canonical repo.

```bash
ssh glasslab@192.168.1.44
cd /home/glasslab/cluster-config
```

2. Record current v2 objects before changing anything.

```bash
kubectl -n glasslab-v2 get deploy,statefulset,svc,configmap,secret
```

3. Disable the user-facing deployments first.

```bash
kubectl -n glasslab-v2 scale deploy/glasslab-openclaw --replicas=0 || true
kubectl -n glasslab-v2 scale deploy/glasslab-workflow-api --replicas=0
```

4. If the rollback is caused by a bad repo change, revert or check out the last known-good commit.

```bash
git log --oneline -n 5
git revert <bad-commit>
```

5. Re-apply the known-good manifests and exported OpenClaw config.

```bash
./scripts/export-openclaw-config.sh
./scripts/deploy-glasslab-v2.sh
```

6. If the workflow-api image itself is the problem, set the deployment back to the previous image tag before scaling up.

```bash
kubectl -n glasslab-v2 set image deploy/glasslab-workflow-api workflow-api=<known-good-image>
```

7. Scale the workflow-api back up and verify health.

```bash
kubectl -n glasslab-v2 scale deploy/glasslab-workflow-api --replicas=1
./scripts/smoke-test-v2.sh
```

8. Only scale OpenClaw up again after its config export, image, and secret inputs are confirmed.
