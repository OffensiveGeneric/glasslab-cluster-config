# Research Session CLI

While OpenClaw is still unreliable for the first-turn research loop, the canonical deterministic control path is:

- [research-session-cli.sh](/home/gr66ss/cluster-config/scripts/research-session-cli.sh) on `.44`
- [research-session-remote.sh](/home/gr66ss/cluster-config/scripts/research-session-remote.sh) from the laptop

## Current Commands

Fresh topic:

```bash
./scripts/research-session-remote.sh new "forged art detection with computer vision methods and open datasets"
```

Resume or reuse active session:

```bash
./scripts/research-session-remote.sh start "forged art detection with computer vision methods and open datasets"
```

Inspect current session:

```bash
./scripts/research-session-remote.sh context
```

Refresh the active queue:

```bash
./scripts/research-session-remote.sh more-papers
```

Stage the next paper from the active queue:

```bash
./scripts/research-session-remote.sh next-paper
```

Append a manual paper candidate:

```bash
./scripts/research-session-remote.sh add-paper "https://arxiv.org/abs/2401.12345"
```

Save a note on the active session:

```bash
./scripts/research-session-remote.sh note "focus on CV datasets first"
```

Inspect the latest operation:

```bash
./scripts/research-session-remote.sh op
```

## Why This Exists

This CLI is not the final product.

It exists because the deterministic backend/session path is currently more reliable than the OpenClaw front door for:

- starting a research session
- starting literature search
- staging the next paper

The matching OpenClaw command surface is now:

- `!research <topic>`
- `!session`
- `!more-papers`
- `!add-paper <url|title>`
- `!next-paper`
- `!note <text>`
- `!op`
- `!help`

That makes it the right control path while the OpenClaw UX boundary is being reworked.
