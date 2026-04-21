# exo Golden Path

Last updated: 2026-04-21

This is the known-good recovery path for the two-node exo + Thunderbolt RDMA + OpenCode setup on the two Mac Studios.

## 0. Optional: make sure both Macs are on the known-good exo version

Run on both Macs:

```bash
cd ~/exo
git fetch origin
git reset --hard origin/main
uv sync
git rev-parse --short HEAD
```

Known-good commit from the restored state: `49670c86`.

## 1. Verify Thunderbolt RDMA on both Macs

On `.21`:

```bash
ifconfig en5
networksetup -getinfo "EXO Thunderbolt 4"
ibv_devices
route -n get 192.168.0.2
```

On `.19`:

```bash
ifconfig en5
networksetup -getinfo "EXO Thunderbolt 4"
ibv_devices
route -n get 192.168.0.1
```

What you want:

- `.21` has `192.168.0.1/30` on `en5`
- `.19` has `192.168.0.2/30` on `en5`
- `rdma_en5` exists on both Macs

## 2. If either Mac lost its Thunderbolt IP, rebind it

On `.21` only:

```bash
sudo ifconfig en5 inet 192.168.0.1 netmask 255.255.255.252 up
ifconfig en5
```

On `.19` only:

```bash
sudo ifconfig en5 inet 192.168.0.2 netmask 255.255.255.252 up
ifconfig en5
```

## 3. Verify the point-to-point link works both ways

From `.21`:

```bash
ping -S 192.168.0.1 -c 5 192.168.0.2
```

From `.19`:

```bash
ping -S 192.168.0.2 -c 5 192.168.0.1
```

These need to succeed before you bother with exo.

## 4. Start exo once on each Mac

On `.21`:

```bash
cd ~/exo
nohup caffeinate -dimsu env EXO_LIBP2P_NAMESPACE=glasslab-rdma-test EXO_FAST_SYNCH=1 uv run exo > ~/exo-21.log 2>&1 < /dev/null &
```

On `.19`:

```bash
cd ~/exo
nohup caffeinate -dimsu env EXO_LIBP2P_NAMESPACE=glasslab-rdma-test EXO_FAST_SYNCH=1 uv run exo > ~/exo-19.log 2>&1 < /dev/null &
```

Those are the exact environment settings from the working restore.

## 5. On `.21`, run the health/model preflight

```bash
~/opencode-with-exo.sh --dry-run
```

Expected result:

- 2-node cluster
- RDMA edges on `rdma_en5`
- usable 2-node `MlxJaccl` preview
- active instance or successful readiness check

## 6. If dry-run passes, use the model through OpenCode

```bash
opencode-with-exo
```

Or with a one-shot prompt:

```bash
opencode-with-exo "Summarize this repository and suggest 3 improvements."
```

## 7. Direct smoke test, if you want to verify the model manually

From `.21`:

```bash
curl -X POST http://127.0.0.1:52415/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"mlx-community/Qwen3-Coder-Next-4bit","messages":[{"role":"user","content":"Reply with exactly OK."}],"max_tokens":8,"stream":false}'
```

Expected result: HTTP `200` and content `OK`.

## 8. Handy fallback commands

Health check only:

```bash
exo-rdma-health-check
```

Bring model up directly:

```bash
exo-bringup-model --model mlx-community/Qwen3-Coder-Next-4bit
```

Recover a node and start exo:

On `.21`:

```bash
exo-node-recover --self 192.168.0.1 --peer 192.168.0.2 --start-exo
```

On `.19`:

```bash
exo-node-recover --self 192.168.0.2 --peer 192.168.0.1 --start-exo
```

Those helper scripts are installed both in `~` and on `PATH` on both Macs.

## 9. Minimal “do this after reboot” version

On both Macs:

```bash
ifconfig en5
networksetup -getinfo "EXO Thunderbolt 4"
ibv_devices
```

If needed:

```bash
sudo ifconfig en5 inet 192.168.0.1 netmask 255.255.255.252 up   # .21
sudo ifconfig en5 inet 192.168.0.2 netmask 255.255.255.252 up   # .19
```

Then:

```bash
ping -S 192.168.0.1 -c 5 192.168.0.2   # on .21
ping -S 192.168.0.2 -c 5 192.168.0.1   # on .19
```

Then:

```bash
cd ~/exo
nohup caffeinate -dimsu env EXO_LIBP2P_NAMESPACE=glasslab-rdma-test EXO_FAST_SYNCH=1 uv run exo > ~/exo-21.log 2>&1 < /dev/null &
nohup caffeinate -dimsu env EXO_LIBP2P_NAMESPACE=glasslab-rdma-test EXO_FAST_SYNCH=1 uv run exo > ~/exo-19.log 2>&1 < /dev/null &
```

Then on `.21`:

```bash
~/opencode-with-exo.sh --dry-run
opencode-with-exo
```

This is the exact path that restored the 2-node exo cluster with Thunderbolt RDMA and a working `mlx-community/Qwen3-Coder-Next-4bit` serving stack.
