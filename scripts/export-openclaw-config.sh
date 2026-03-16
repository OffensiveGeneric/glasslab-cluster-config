#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="$ROOT_DIR/services/openclaw-config"
KUBECTL="${KUBECTL:-kubectl}"
NAMESPACE="${GLASSLAB_V2_NAMESPACE:-glasslab-v2}"
CONFIGMAP_NAME="${GLASSLAB_OPENCLAW_CONFIGMAP_NAME:-glasslab-openclaw-config}"
OUTPUT_DIR=""
APPLY_CONFIGMAP=true
TMP_DIR=""
TMP_ARCHIVE=""

usage() {
  cat <<'USAGE'
Usage: export-openclaw-config.sh [--output-dir DIR] [--no-apply]

Generate the native OpenClaw runtime bundle from services/openclaw-config.

The generated runtime contract is:
- source repo config: services/openclaw-config
- generated config file: openclaw.json
- generated workspaces: workspaces/<agent>/
- generated source mirror: glasslab-config/
- configmap key when applied: openclaw-runtime.tar.gz
- in-container runtime root: /var/lib/openclaw/runtime
- in-container config path: /var/lib/openclaw/runtime/openclaw.json

Options:
- --output-dir DIR  write the generated runtime tree to DIR for inspection
- --no-apply        do not apply the ConfigMap, only generate the runtime tree
USAGE
}

cleanup() {
  if [[ -n "$TMP_ARCHIVE" && -f "$TMP_ARCHIVE" ]]; then
    rm -f "$TMP_ARCHIVE"
  fi
  if [[ -n "$TMP_DIR" && -d "$TMP_DIR" ]]; then
    rm -rf "$TMP_DIR"
  fi
}
trap cleanup EXIT

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    printf '[export-openclaw-config] missing command: %s\n' "$1" >&2
    exit 1
  }
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir)
      [[ $# -ge 2 ]] || {
        printf '[export-openclaw-config] --output-dir requires a value\n' >&2
        exit 1
      }
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --no-apply)
      APPLY_CONFIGMAP=false
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      printf '[export-openclaw-config] unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

need_cmd python3
need_cmd tar
if [[ "$APPLY_CONFIGMAP" == true ]]; then
  need_cmd "$KUBECTL"
fi

[[ -d "$SOURCE_DIR" ]] || {
  printf '[export-openclaw-config] source directory not found: %s\n' "$SOURCE_DIR" >&2
  exit 1
}

TMP_DIR="$(mktemp -d)"
python3 - "$SOURCE_DIR" "$TMP_DIR/runtime" <<'PY'
import json
import shutil
import sys
from pathlib import Path

import yaml

source_dir = Path(sys.argv[1])
runtime_dir = Path(sys.argv[2])
repo_root = source_dir.parents[1]
registry_dir = repo_root / "services" / "workflow-registry" / "definitions"

required_files = [
    "agents/operator/agent.yaml",
    "agents/operator/prompt.md",
    "agents/literature/agent.yaml",
    "agents/literature/prompt.md",
    "agents/designer/agent.yaml",
    "agents/designer/prompt.md",
    "agents/reporter/agent.yaml",
    "agents/reporter/prompt.md",
    "bindings/workflow-api.yaml",
    "bindings/reporting.yaml",
    "providers/local-vllm-openai-compatible.yaml",
    "policy/tool-policy.yaml",
    "policy/approval-tiers.yaml",
    "plugins/workflow-api-tool/openclaw.plugin.json",
    "plugins/workflow-api-tool/package.json",
    "plugins/workflow-api-tool/index.ts",
]

for rel in required_files:
    path = source_dir / rel
    if not path.is_file():
        raise SystemExit(f"missing required source file: {path}")


def load_yaml(rel_path: str):
    with (source_dir / rel_path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


agents = {}
for agent_name in ("operator", "literature", "designer", "reporter"):
    agents[agent_name] = load_yaml(f"agents/{agent_name}/agent.yaml")

prompts = {
    agent_name: (source_dir / f"agents/{agent_name}/prompt.md").read_text(encoding="utf-8").strip()
    for agent_name in agents
}

workflow_binding = load_yaml("bindings/workflow-api.yaml")
reporting_binding = load_yaml("bindings/reporting.yaml")
provider = load_yaml("providers/local-vllm-openai-compatible.yaml")
tool_policy = load_yaml("policy/tool-policy.yaml")
approval_tiers = load_yaml("policy/approval-tiers.yaml")

if not registry_dir.is_dir():
    raise SystemExit(f"workflow registry directory not found: {registry_dir}")

known_workflow_ids = []
for definition_path in sorted(registry_dir.glob("*.json")):
    payload = json.loads(definition_path.read_text(encoding="utf-8"))
    workflow_id = payload.get("workflow_id")
    if isinstance(workflow_id, str) and workflow_id.strip():
        known_workflow_ids.append(workflow_id.strip())

if not known_workflow_ids:
    raise SystemExit(f"no workflow_ids found in registry directory: {registry_dir}")

expected_workflow_api = "http://glasslab-workflow-api.glasslab-v2.svc.cluster.local:8080"
expected_vllm = "http://vllm.glasslab-agents.svc.cluster.local:8000/v1"

if workflow_binding.get("base_url") != expected_workflow_api:
    raise SystemExit(
        "workflow-api binding must point at "
        f"{expected_workflow_api}, found {workflow_binding.get('base_url')!r}"
    )

if provider.get("base_url") != expected_vllm:
    raise SystemExit(
        "provider base_url must point at "
        f"{expected_vllm}, found {provider.get('base_url')!r}"
    )

validation_run_request = workflow_binding.get("validation_run_request")
if not isinstance(validation_run_request, dict):
    raise SystemExit("workflow-api binding must define validation_run_request")

for key in ("workflow_id", "objective", "inputs", "models"):
    if key not in validation_run_request:
        raise SystemExit(
            f"workflow-api validation_run_request is missing required key {key!r}"
        )

default_model = provider.get("default_model")
if not default_model:
    raise SystemExit("provider default_model is required")

context_window = int(provider.get("context_window", 4096))
max_output_tokens = int(provider.get("max_output_tokens", 4096))

if context_window < 1:
    raise SystemExit("provider context_window must be positive")

if max_output_tokens < 1:
    raise SystemExit("provider max_output_tokens must be positive")

runtime_dir.mkdir(parents=True, exist_ok=True)
workspaces_dir = runtime_dir / "workspaces"
glasslab_config_dir = runtime_dir / "glasslab-config"
shutil.copytree(source_dir, glasslab_config_dir, dirs_exist_ok=True)
container_runtime_root = Path("/var/lib/openclaw/runtime")
container_workspaces_root = container_runtime_root / "workspaces"

# Keep day-one turns on a narrow tool surface until broader validation is intentional.
dangerous_tools = [
    "exec",
    "process",
    "write",
    "edit",
    "apply_patch",
    "session_status",
    "gateway",
    "cron",
    "nodes",
    "browser",
    "canvas",
    "sessions_spawn",
    "sessions_send",
]

model_ref = f"glasslab-vllm/{default_model}"

allowed_runtime_tools = {
    "web_fetch",
    "workflow_api_get_families",
    "workflow_api_create_validation_run",
    "workflow_api_get_last_validation_run",
    "workflow_api_get_family_by_id",
}
allowed_runtime_profiles = {"minimal", "coding", "messaging", "full"}

for agent_name, agent_cfg in agents.items():
    runtime_profile = agent_cfg.get("runtime_tools_profile")
    if runtime_profile and runtime_profile not in allowed_runtime_profiles:
        raise SystemExit(
            f"agent {agent_name!r} requested unsupported runtime tool profile {runtime_profile!r}"
        )
    for tool_id in agent_cfg.get("runtime_tools_allow", []):
        if tool_id not in allowed_runtime_tools:
            raise SystemExit(
                f"agent {agent_name!r} requested unsupported runtime tool {tool_id!r}"
            )
    for tool_id in agent_cfg.get("runtime_tools_deny", []):
        if tool_id not in allowed_runtime_tools:
            raise SystemExit(
                f"agent {agent_name!r} requested unsupported runtime deny tool {tool_id!r}"
            )

runtime_config = {
    "gateway": {
        "bind": "lan",
        "port": 18789,
        "auth": {
            "mode": "token",
            "token": "${OPENCLAW_GATEWAY_TOKEN}",
        },
    },
    "tools": {
        "profile": "minimal",
        "web": {
            "fetch": {"enabled": True},
            "search": {"enabled": False},
        },
    },
    "models": {
        "mode": "merge",
        "providers": {
            "glasslab-vllm": {
                "baseUrl": provider["base_url"],
                "apiKey": "${OPENCLAW_VLLM_API_KEY}",
                "api": "openai-completions",
                "models": [
                    {
                        "id": default_model,
                        "name": default_model,
                        "reasoning": False,
                        "input": ["text"],
                        "cost": {
                            "input": 0,
                            "output": 0,
                            "cacheRead": 0,
                            "cacheWrite": 0,
                        },
                        "contextWindow": context_window,
                        "maxTokens": max_output_tokens,
                    }
                ],
            }
        }
    },
    "agents": {
        "defaults": {
            "skipBootstrap": True,
            "model": {
                "primary": model_ref,
            },
            "models": {
                model_ref: {
                    "alias": "glasslab-qwen-local",
                    "params": {
                        "temperature": provider.get("temperature", 0.0),
                    },
                }
            },
        },
        "list": [],
    },
    "plugins": {
        "allow": ["workflow-api-tool"],
        "load": {
            "paths": [
                str(container_runtime_root / "glasslab-config" / "plugins" / "workflow-api-tool"),
            ],
        },
        "entries": {
            "workflow-api-tool": {
                "enabled": True,
                "config": {
                    "baseUrl": workflow_binding["base_url"],
                    "validationRunRequest": validation_run_request,
                    "knownWorkflowIds": known_workflow_ids,
                },
            },
        },
    },
}

runtime_contract_lines = [
    "# OpenClaw Runtime Contract",
    "",
    "- source repo config: `services/openclaw-config`",
    "- generated runtime root: `/var/lib/openclaw/runtime`",
    "- generated native config file: `/var/lib/openclaw/runtime/openclaw.json`",
    "- generated agent workspaces: `/var/lib/openclaw/runtime/workspaces/<agent>/`",
    "- mirrored source tree: `/var/lib/openclaw/runtime/glasslab-config/`",
    "- workflow-api binding: "
    + workflow_binding["base_url"],
    "- provider base URL: "
    + provider["base_url"],
    "- workflow-api plugin path: `/var/lib/openclaw/runtime/glasslab-config/plugins/workflow-api-tool`",
    "- operator runtime allowlist: `workflow_api_get_families`, `workflow_api_create_validation_run`, `workflow_api_get_last_validation_run`, `workflow_api_get_family_by_id`",
    "- workflow-api tool audit log: `/var/lib/openclaw/state/workflow-api-tool/tool-call-audit.jsonl`",
    "",
    "The native runtime bundle is generated by `scripts/export-openclaw-config.sh`.",
]


def workspace_text(agent_name: str, agent_cfg: dict) -> dict[str, str]:
    policy_name = agent_cfg["policy_profile"]
    policy_profile = tool_policy["profile_defaults"][policy_name]
    lines_agents = [
        "# AGENTS",
        "",
        f"- agent id: `{agent_name}`",
        f"- role: `{agent_cfg['role']}`",
        f"- summary: {agent_cfg['summary']}",
        f"- default provider: `{agent_cfg['default_provider']}`",
        f"- policy profile: `{policy_name}`",
        "",
        "Approved bindings:",
    ]
    for binding in agent_cfg.get("allowed_bindings", []):
        lines_agents.append(f"- `{binding}`")

    lines_identity = [
        "# IDENTITY",
        "",
        prompts[agent_name],
    ]

    lines_tools = [
        "# TOOLS",
        "",
        "This workspace is exported from repo-managed Glasslab v2 config.",
        "Native OpenClaw runtime denies mutation-heavy tools and keeps web search disabled.",
        "",
        "Profile capabilities recorded from source policy:",
        "",
        "Allow:",
    ]
    for item in policy_profile.get("allow", []):
        lines_tools.append(f"- `{item}`")
    lines_tools.extend(["", "Deny:"])
    for item in policy_profile.get("deny", []):
        lines_tools.append(f"- `{item}`")
    deny_tools = dangerous_tools + agent_cfg.get("runtime_tools_deny", [])
    lines_tools.extend(["", "Runtime deny list:"])
    for item in deny_tools:
        lines_tools.append(f"- `{item}`")
    runtime_allow = agent_cfg.get("runtime_tools_allow", [])
    runtime_profile = agent_cfg.get("runtime_tools_profile")
    if runtime_allow:
        lines_tools.extend(["", "Explicit runtime allowlist:"])
        for item in runtime_allow:
            lines_tools.append(f"- `{item}`")
    else:
        lines_tools.extend(["", "Explicit runtime allowlist:", "- none"])
    lines_tools.extend(["", "Explicit runtime tool profile:"])
    if runtime_profile:
        lines_tools.append(f"- `{runtime_profile}`")
    else:
        lines_tools.append("- inherit global profile")

    lines_user = [
        "# USER",
        "",
        "In-cluster service references:",
        f"- workflow-api: `{workflow_binding['base_url']}`",
        f"- vLLM provider: `{provider['base_url']}`",
        "",
        "Approval tiers:",
    ]
    for tier_name, tier_cfg in approval_tiers["approval_tiers"].items():
        lines_user.append(
            f"- `{tier_name}`: {tier_cfg['description']}"
        )
    lines_user.extend(
        [
            "",
            "Reporting binding contract:",
        ]
    )
    for item in reporting_binding["artifact_contract"]["required_inputs"]:
        lines_user.append(f"- required artifact: `{item}`")
    for item in reporting_binding["artifact_contract"].get("optional_inputs", []):
        lines_user.append(f"- optional artifact: `{item}`")

    return {
        "AGENTS.md": "\n".join(lines_agents) + "\n",
        "IDENTITY.md": "\n".join(lines_identity) + "\n",
        "TOOLS.md": "\n".join(lines_tools) + "\n",
        "USER.md": "\n".join(lines_user) + "\n",
    }


for agent_name, agent_cfg in agents.items():
    workspace_dir = workspaces_dir / agent_name
    workspace_dir.mkdir(parents=True, exist_ok=True)
    rendered_files = workspace_text(agent_name, agent_cfg)
    for file_name, content in rendered_files.items():
        (workspace_dir / file_name).write_text(content, encoding="utf-8")

    deny_tools = dangerous_tools + agent_cfg.get("runtime_tools_deny", [])
    runtime_config["agents"]["list"].append(
        {
            "id": agent_name,
            "name": agent_cfg["name"].replace("-", " ").title(),
            "workspace": str(container_workspaces_root / agent_name),
            "tools": {
                **({"profile": agent_cfg["runtime_tools_profile"]} if agent_cfg.get("runtime_tools_profile") else {}),
                "allow": agent_cfg.get("runtime_tools_allow", []),
                "deny": deny_tools,
            },
        }
    )

(runtime_dir / "openclaw.json").write_text(
    json.dumps(runtime_config, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
(runtime_dir / "RUNTIME-CONTRACT.md").write_text(
    "\n".join(runtime_contract_lines) + "\n",
    encoding="utf-8",
)
PY

if [[ -n "$OUTPUT_DIR" ]]; then
  rm -rf "$OUTPUT_DIR"
  mkdir -p "$OUTPUT_DIR"
  cp -R "$TMP_DIR/runtime/." "$OUTPUT_DIR/"
  printf '[export-openclaw-config] wrote generated runtime tree to %s\n' "$OUTPUT_DIR"
fi

TMP_ARCHIVE="$(mktemp)"
tar -C "$TMP_DIR/runtime" -czf "$TMP_ARCHIVE" .

if [[ "$APPLY_CONFIGMAP" == true ]]; then
  "$KUBECTL" -n "$NAMESPACE" create configmap "$CONFIGMAP_NAME" \
    --from-file=openclaw-runtime.tar.gz="$TMP_ARCHIVE" \
    --dry-run=client -o yaml | "$KUBECTL" apply -f -
fi

printf '[export-openclaw-config] source repo path: %s\n' "$SOURCE_DIR"
printf '[export-openclaw-config] configmap key: openclaw-runtime.tar.gz\n'
printf '[export-openclaw-config] in-container runtime root: /var/lib/openclaw/runtime\n'
printf '[export-openclaw-config] in-container config path: /var/lib/openclaw/runtime/openclaw.json\n'

if [[ "$APPLY_CONFIGMAP" == true ]]; then
  printf '[export-openclaw-config] applied configmap/%s in namespace %s\n' "$CONFIGMAP_NAME" "$NAMESPACE"
else
  printf '[export-openclaw-config] skipped ConfigMap apply (--no-apply)\n'
fi
