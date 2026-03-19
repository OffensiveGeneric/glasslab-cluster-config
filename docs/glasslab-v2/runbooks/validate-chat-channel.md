# Validate Chat Channel

1. Log into the provisioner host and move to the canonical repo.

```bash
ssh glasslab@192.168.1.44
cd /home/glasslab/cluster-config
```

2. Confirm the first chat channel config is present in the repo-managed source tree.

```bash
sed -n '1,200p' services/openclaw-config/channels/whatsapp.yaml
```

Expected policy:
- channel: `whatsapp`
- route: direct messages to `operator`
- `dm_policy: allowlist`
- `self_chat_mode: true`
- `group_policy: disabled`

3. Confirm the existing OpenClaw secret exists.

```bash
kubectl -n glasslab-v2 get secret glasslab-openclaw
```

4. Add the operator's WhatsApp number to the local non-committed OpenClaw secret manifest.

Required local file:
- `kubeadm/glasslab-v2/secrets/30-openclaw.local.yaml`

Required additional key:
- `OPENCLAW_WHATSAPP_OWNER`

Example patch:

```bash
python3 - <<'PY'
from pathlib import Path
import yaml

path = Path("kubeadm/glasslab-v2/secrets/30-openclaw.local.yaml")
payload = yaml.safe_load(path.read_text())
payload.setdefault("stringData", {})["OPENCLAW_WHATSAPP_OWNER"] = "+15551234567"
path.write_text(yaml.safe_dump(payload, sort_keys=False))
PY
chmod 600 kubeadm/glasslab-v2/secrets/30-openclaw.local.yaml
```

5. Re-export the runtime bundle, apply the updated Secret manifest, and restart the live OpenClaw Deployment so the pod unpacks the updated runtime.

```bash
kubectl apply -f kubeadm/glasslab-v2/secrets/30-openclaw.local.yaml
./scripts/export-openclaw-config.sh
kubectl -n glasslab-v2 rollout restart deploy/glasslab-openclaw
kubectl -n glasslab-v2 rollout status deploy/glasslab-openclaw --timeout=300s
```

6. Verify the live runtime bundle contains the WhatsApp channel block and the operator binding.

```bash
kubectl -n glasslab-v2 exec deploy/glasslab-openclaw -- \
  sed -n '1,260p' /var/lib/openclaw/runtime/openclaw.json
```

Confirm:
- `channels.whatsapp.dmPolicy` is `allowlist`
- `channels.whatsapp.allowFrom[0]` is `${OPENCLAW_WHATSAPP_OWNER}`
- `channels.whatsapp.selfChatMode` is `true`
- `channels.whatsapp.groupPolicy` is `disabled`
- `bindings[]` includes `channel: "whatsapp"` for agent `operator`

7. Link the WhatsApp account from the live OpenClaw pod.

```bash
kubectl -n glasslab-v2 exec -it deploy/glasslab-openclaw -- \
  openclaw channels login --channel whatsapp --account default --verbose
```

Expected behavior:
- OpenClaw prints a QR code or pairing prompt in the terminal
- scan it from the operator phone's WhatsApp client
- this first validation path assumes self-chat on the linked account only

8. Verify channel readiness.

```bash
kubectl -n glasslab-v2 exec deploy/glasslab-openclaw -- openclaw channels list
kubectl -n glasslab-v2 exec deploy/glasslab-openclaw -- openclaw channels status
kubectl -n glasslab-v2 logs deploy/glasslab-openclaw --tail=200 | grep -i whatsapp
```

Success indicators:
- `channels list` shows WhatsApp configured
- `channels status` reports gateway reachable
- logs show the WhatsApp listener connected without repeated auth failures

9. Send the first test message from the linked WhatsApp account to itself.

Recommended first message:
- `What workflow families are available?`

Optional backend-backed messages:
- `Create the validation run.`
- `What was the last validation run?`
- `Summarize the last validation run.`

10. Verify the operator reply in the same WhatsApp chat and confirm backend proof in `workflow-api` logs.

For the workflow-family read path:

```bash
kubectl -n glasslab-v2 logs deploy/glasslab-workflow-api --since=5m | grep 'GET /workflow-families'
```

For the validation run create path:

```bash
kubectl -n glasslab-v2 logs deploy/glasslab-workflow-api --since=5m | grep 'POST /runs'
```

For the validation run retrieval path:

```bash
kubectl -n glasslab-v2 logs deploy/glasslab-workflow-api --since=5m | grep '/runs/'
```

Expected response shape:
- the WhatsApp reply is plain-language operator text
- the backend proof is in `workflow-api` logs, not in the WhatsApp message itself
- the safe path still relies on the existing no-arg workflow-api tools

11. If the runtime changes again later, re-export and restart before retesting.

```bash
./scripts/export-openclaw-config.sh
kubectl -n glasslab-v2 rollout restart deploy/glasslab-openclaw
```

12. Roll back or disable the channel validation path if needed.

```bash
kubectl -n glasslab-v2 exec deploy/glasslab-openclaw -- \
  openclaw channels logout --channel whatsapp --account default || true
kubectl -n glasslab-v2 scale deploy/glasslab-openclaw --replicas=0
```

If you want the gateway to stay up but remove the linked chat session only:

```bash
kubectl -n glasslab-v2 exec deploy/glasslab-openclaw -- \
  rm -rf /var/lib/openclaw/state/credentials/whatsapp/default
kubectl -n glasslab-v2 rollout restart deploy/glasslab-openclaw
```

Operational caveat:
- `/var/lib/openclaw/state` now uses a retained local PV/PVC on `node01`
- replacing the pod no longer removes the linked WhatsApp credentials
- this is still local-node durability, not shared-storage failover
