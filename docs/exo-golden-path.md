# exo Golden Path

Last updated: 2026-08-06

This is the current two-node exo, Thunderbolt RDMA, Qwen, and OpenCode path.
The older `.21` and `.19` topology is retired from this runbook.

## Topology

| Role | LAN | Thunderbolt | exo role |
| --- | --- | --- | --- |
| API/master | `192.168.1.17` | `192.168.0.2/30` | forced master and OpenAI-compatible API |
| Worker | `192.168.1.18` | `192.168.0.1/30` | worker bootstrapped directly to `.17` |

Both nodes use:

- exo tree: `/Users/glasslab/exo`
- namespace: `glasslab-rdma-prod`
- API port: `52415`
- libp2p port: `54216`
- RDMA interface: `rdma_en5`

The approved OpenCode model is
`mlx-community/Qwen3-Coder-Next-4bit`. Its placement must be two-node
`Pipeline + MlxJaccl`.

## Supervised Startup

System `LaunchDaemon` jobs own exo. Do not start another copy with `nohup`.

On `.17`:

- `com.glasslab.exo` supervises the exo master/API.
- `com.glasslab.exo-reconcile` waits for both RDMA-connected nodes and restores
  the approved Qwen placement when no active instance exists.

On `.18`:

- `com.glasslab.exo` supervises the worker.
- the worker obtains `.17`'s current peer ID from the master API and uses an
  explicit Thunderbolt bootstrap multiaddress.

`KeepAlive` restarts a process that exits. Both jobs run as the `glasslab`
account at boot and do not require an interactive login.

## Install Or Update

Copy `scripts/macos/` to each Mac and run:

```bash
sudo ./scripts/macos/install-exo-launchd.sh 18  # on .18 first
sudo ./scripts/macos/install-exo-launchd.sh 17  # on .17 second
```

Installing `.18` first lets the worker wait for the deterministic master while
`.17` is restarted.

## Validate

Check the daemons:

```bash
sudo launchctl print system/com.glasslab.exo
sudo launchctl print system/com.glasslab.exo-reconcile  # .17 only
```

Check the physical path on both Macs:

```bash
ifconfig en5
ibv_devices
```

Expected addresses:

```text
.17 en5: 192.168.0.2
.18 en5: 192.168.0.1
```

Check the authoritative state on `.17`:

```bash
curl -fsS http://127.0.0.1:52415/state | jq '{
  nodes: (.topology.nodes | length),
  connections: .topology.connections,
  instances: (.instances | keys)
}'
```

Run a real completion:

```bash
curl -fsS http://127.0.0.1:52415/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"mlx-community/Qwen3-Coder-Next-4bit","messages":[{"role":"user","content":"Reply exactly: OK"}],"max_tokens":8}'
```

## OpenCode

Use OpenCode from `.17`, where its provider points to the local exo API:

```bash
ssh glasslab-17
cd ~/cluster-config
opencode -m exo/mlx-community/Qwen3-Coder-Next-4bit
```

The model reconciler may need a short interval after both Macs boot before the
instance is ready.

## Logs And Recovery

Logs are retained outside `/tmp`:

```text
/Users/glasslab/Library/Logs/glasslab-exo.log
/Users/glasslab/Library/Logs/glasslab-exo.error.log
/Users/glasslab/Library/Logs/glasslab-exo-reconcile.log
/Users/glasslab/Library/Logs/glasslab-exo-reconcile.error.log
```

Restart a service without creating an unmanaged process:

```bash
sudo launchctl kickstart -k system/com.glasslab.exo
sudo launchctl kickstart -k system/com.glasslab.exo-reconcile  # .17 only
```

If the Thunderbolt interface is absent or inactive, repair that operating
system network state first. `launchd` deliberately waits rather than attempting
privileged network reconfiguration.

## Remaining Limitation

The LAN addresses `.17` and `.18` are currently DHCP leases from
`192.168.1.100`. Reserve their Ethernet MAC addresses on that DHCP server. Exo
itself communicates over the static Thunderbolt addresses, so a changed LAN
lease affects SSH aliases but not the internal model transport.
