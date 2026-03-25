# Test OpenClaw Shared State

This runbook exists to make issue `#14` concrete.

It is for a non-production migration test only.

Do not treat it as a default deploy path.

## Goal

Determine whether OpenClaw writable state can move from the current local PV on `node01` to shared NFS-backed storage without creating operational weirdness.

## Current Baseline

Current live default:

- PVC: `glasslab-openclaw-state`
- backing path: `/var/lib/glasslab-v2/openclaw-state` on `node01`

Test candidate:

- PVC: `glasslab-openclaw-state-shared-test`
- backing path: `/volume1/backup/glasslab-v2/openclaw-state-test` on `192.168.1.207`

## 1. Apply The Non-Production Test PV/PVC

From `.44`:

```bash
cd /home/glasslab/cluster-config
kubectl apply -f kubeadm/glasslab-v2/storage/30-openclaw-shared-state.example.yaml
kubectl -n glasslab-v2 get pvc glasslab-openclaw-state-shared-test
```

## 2. Back Up The Current OpenClaw State First

Use the existing local-PV backup runbook before changing the claim wiring:

```bash
sed -n '1,260p' docs/glasslab-v2/runbooks/backup-restore-local-pv-services.md
```

At minimum, preserve a tarball or copied snapshot of the current OpenClaw state.

## 3. Keep The Test Explicitly Non-Production

Recommended safety rules:

- scale OpenClaw to `0` before changing claim wiring
- keep the change on a test branch or clearly temporary patch
- do not combine this with unrelated OpenClaw runtime or prompt edits

## 4. Patch The Deployment To Use The Test Claim

Example patch command:

```bash
kubectl -n glasslab-v2 patch deploy/glasslab-openclaw \
  --type='json' \
  -p='[{"op":"replace","path":"/spec/template/spec/volumes/2/persistentVolumeClaim/claimName","value":"glasslab-openclaw-state-shared-test"}]'
```

Then restart or scale up OpenClaw deliberately.

## 5. Validate The Test

Check:

- the pod starts normally
- OpenClaw can still read and write its state directory
- linked WhatsApp or session continuity behaves as expected
- a pod restart does not lose the expected state

Useful commands:

```bash
kubectl -n glasslab-v2 get pods -l app.kubernetes.io/name=glasslab-openclaw -o wide
kubectl -n glasslab-v2 logs deploy/glasslab-openclaw --tail=200
kubectl -n glasslab-v2 exec deploy/glasslab-openclaw -- find /var/lib/openclaw/state -maxdepth 3 -type f | sort | head -n 50
```

## 6. Record The Result

If the test is good, record:

- startup behavior
- restart behavior
- any latency or odd file-behavior concerns
- whether session continuity was acceptable

If the test is bad, write down the failure mode precisely before rolling back.

## 7. Roll Back To The Current Local-PV Path

Patch the Deployment back to the default claim:

```bash
kubectl -n glasslab-v2 patch deploy/glasslab-openclaw \
  --type='json' \
  -p='[{"op":"replace","path":"/spec/template/spec/volumes/2/persistentVolumeClaim/claimName","value":"glasslab-openclaw-state"}]'
kubectl -n glasslab-v2 rollout restart deploy/glasslab-openclaw
kubectl -n glasslab-v2 rollout status deploy/glasslab-openclaw --timeout=300s
```

If needed, restore the prior state snapshot captured before the test.

## Success Condition

This test is successful only if:

- OpenClaw starts cleanly on the shared claim
- expected writable state survives restart
- operator-facing session continuity is acceptable
- rollback back to the local-PV claim is straightforward
