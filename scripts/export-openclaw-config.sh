#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="$ROOT_DIR/services/openclaw-config"
KUBECTL="${KUBECTL:-kubectl}"
NAMESPACE="${GLASSLAB_V2_NAMESPACE:-glasslab-v2}"
CONFIGMAP_NAME="${GLASSLAB_OPENCLAW_CONFIGMAP_NAME:-glasslab-openclaw-config}"
GIT_SHA="${GLASSLAB_GIT_SHA:-$(git -C "$ROOT_DIR" rev-parse --short HEAD)}"
BUILD_SOURCE="${GLASSLAB_BUILD_SOURCE:-git:${GIT_SHA}}"
export GLASSLAB_GIT_SHA="$GIT_SHA"
export GLASSLAB_BUILD_SOURCE="$BUILD_SOURCE"
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

Environment overrides:
- GLASSLAB_OPENCLAW_PROVIDER_BASE_URL  override the inference provider base URL
- GLASSLAB_OPENCLAW_PROVIDER_API       override the provider API type: openai-completions or ollama
- GLASSLAB_OPENCLAW_PROVIDER_ID        override the exported provider id prefix
- GLASSLAB_OPENCLAW_PROVIDER_API_KEY_ENV  override the OpenClaw secret env var used for the provider key
- GLASSLAB_OPENCLAW_DEFAULT_MODEL      override the primary inference model id
- GLASSLAB_OPENCLAW_MODEL_ALIAS        override the exported OpenClaw model alias
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
import os
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

import yaml

source_dir = Path(sys.argv[1])
runtime_dir = Path(sys.argv[2])
repo_root = source_dir.parents[1]
registry_dir = repo_root / "services" / "workflow-registry" / "definitions"
openclaw_local_secret_path = repo_root / "kubeadm" / "glasslab-v2" / "secrets" / "30-openclaw.local.yaml"
build_source_revision = os.environ.get("GLASSLAB_GIT_SHA", "unknown").strip() or "unknown"
build_source_label = os.environ.get("GLASSLAB_BUILD_SOURCE", "unspecified").strip() or "unspecified"

required_files = [
    "agents/operator/agent.yaml",
    "agents/operator/prompt.md",
    "agents/router/agent.yaml",
    "agents/router/prompt.md",
    "agents/literature/agent.yaml",
    "agents/literature/prompt.md",
    "agents/designer/agent.yaml",
    "agents/designer/prompt.md",
    "agents/reporter/agent.yaml",
    "agents/reporter/prompt.md",
    "bindings/workflow-api.yaml",
    "bindings/reporting.yaml",
    "channels/whatsapp.yaml",
    "providers/local-ollama-native.yaml",
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
for agent_name in ("operator", "router", "literature", "designer", "reporter"):
    agents[agent_name] = load_yaml(f"agents/{agent_name}/agent.yaml")

prompts = {
    agent_name: (source_dir / f"agents/{agent_name}/prompt.md").read_text(encoding="utf-8").strip()
    for agent_name in agents
}

workflow_binding = load_yaml("bindings/workflow-api.yaml")
reporting_binding = load_yaml("bindings/reporting.yaml")
whatsapp_channel = load_yaml("channels/whatsapp.yaml")
provider = load_yaml("providers/local-ollama-native.yaml")
tool_policy = load_yaml("policy/tool-policy.yaml")
approval_tiers = load_yaml("policy/approval-tiers.yaml")

openclaw_local_secret = {}
if openclaw_local_secret_path.is_file():
    with openclaw_local_secret_path.open("r", encoding="utf-8") as handle:
        openclaw_local_secret = yaml.safe_load(handle) or {}

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


def workflow_lookup_tool_name(workflow_id: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", workflow_id.strip().lower()).strip("_")
    return f"workflow_api_get_family_{slug or 'unknown'}"


generated_workflow_lookup_tools = [workflow_lookup_tool_name(workflow_id) for workflow_id in known_workflow_ids]

expected_workflow_api = "http://glasslab-workflow-api.glasslab-v2.svc.cluster.local:8080"
expected_ollama = "http://192.168.1.12:11434"
provider_base_url_override = os.environ.get("GLASSLAB_OPENCLAW_PROVIDER_BASE_URL", "").strip()
provider_api_override = os.environ.get("GLASSLAB_OPENCLAW_PROVIDER_API", "").strip()
provider_id_override = os.environ.get("GLASSLAB_OPENCLAW_PROVIDER_ID", "").strip()
provider_api_key_env_override = os.environ.get("GLASSLAB_OPENCLAW_PROVIDER_API_KEY_ENV", "").strip()
default_model_override = os.environ.get("GLASSLAB_OPENCLAW_DEFAULT_MODEL", "").strip()
model_alias_override = os.environ.get("GLASSLAB_OPENCLAW_MODEL_ALIAS", "").strip()

if workflow_binding.get("base_url") != expected_workflow_api:
    raise SystemExit(
        "workflow-api binding must point at "
        f"{expected_workflow_api}, found {workflow_binding.get('base_url')!r}"
    )

if not provider_base_url_override and provider.get("base_url") != expected_ollama:
    raise SystemExit(
        "provider base_url must point at "
        f"{expected_ollama}, found {provider.get('base_url')!r}"
    )

provider_base_url = provider_base_url_override or provider.get("base_url")
if not provider_base_url:
    raise SystemExit("provider base_url is required")

provider_api = provider_api_override or provider.get("api") or "ollama"
if provider_api not in {"openai-completions", "ollama"}:
    raise SystemExit(
        "provider api must be one of 'openai-completions' or 'ollama', "
        f"found {provider_api!r}"
    )

default_provider_id = "glasslab-vllm" if provider_api == "openai-completions" else "glasslab-ollama"
provider_id = provider_id_override or default_provider_id
if not provider_id:
    raise SystemExit("provider id is required")

default_provider_api_key_env = (
    "OPENCLAW_VLLM_API_KEY"
    if provider_api == "openai-completions"
    else "OPENCLAW_OLLAMA_API_KEY"
)
provider_api_key_env = provider_api_key_env_override or default_provider_api_key_env

parsed_provider_url = urlparse(provider_base_url)
if parsed_provider_url.scheme not in {"http", "https"} or not parsed_provider_url.netloc:
    raise SystemExit(
        "provider base_url must be a full http(s) URL, "
        f"found {provider_base_url!r}"
    )
if parsed_provider_url.hostname in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}:
    raise SystemExit("provider base_url must be reachable from the OpenClaw pod, not localhost")
if provider_api == "ollama" and parsed_provider_url.path.rstrip("/") == "/v1":
    raise SystemExit("provider base_url must not end in /v1 when provider api is 'ollama'")

paper_intake_request = workflow_binding.get("paper_intake_request")
if not isinstance(paper_intake_request, dict):
    raise SystemExit("workflow-api binding must define paper_intake_request")

for key in ("raw_request",):
    if key not in paper_intake_request:
        raise SystemExit(
            f"workflow-api paper_intake_request is missing required key {key!r}"
        )

literature_intake_request = workflow_binding.get("literature_intake_request")
if not isinstance(literature_intake_request, dict):
    raise SystemExit("workflow-api binding must define literature_intake_request")

for key in ("raw_request",):
    if key not in literature_intake_request:
        raise SystemExit(
            f"workflow-api literature_intake_request is missing required key {key!r}"
        )

replication_intake_request = workflow_binding.get("replication_intake_request")
if not isinstance(replication_intake_request, dict):
    raise SystemExit("workflow-api binding must define replication_intake_request")

for key in ("raw_request",):
    if key not in replication_intake_request:
        raise SystemExit(
            f"workflow-api replication_intake_request is missing required key {key!r}"
        )

literature_review_request = workflow_binding.get("literature_review_request")
if not isinstance(literature_review_request, dict):
    raise SystemExit("workflow-api binding must define literature_review_request")

for key in ("resolved_inputs", "review_notes"):
    if key not in literature_review_request:
        raise SystemExit(
            f"workflow-api literature_review_request is missing required key {key!r}"
        )

validation_run_request = workflow_binding.get("validation_run_request")
if not isinstance(validation_run_request, dict):
    raise SystemExit("workflow-api binding must define validation_run_request")

for key in ("workflow_id", "objective", "inputs", "models"):
    if key not in validation_run_request:
        raise SystemExit(
            f"workflow-api validation_run_request is missing required key {key!r}"
        )

default_model = default_model_override or provider.get("default_model")
if not default_model:
    raise SystemExit("provider default_model is required")

model_alias = model_alias_override or "glasslab-inference-primary"

context_window = int(provider.get("context_window", 4096))
max_output_tokens = int(provider.get("max_output_tokens", 4096))

if context_window < 1:
    raise SystemExit("provider context_window must be positive")

if max_output_tokens < 1:
    raise SystemExit("provider max_output_tokens must be positive")

if whatsapp_channel.get("channel") != "whatsapp":
    raise SystemExit("channels/whatsapp.yaml must declare channel: whatsapp")

if whatsapp_channel.get("agent_id") not in {"operator", "router"}:
    raise SystemExit("channels/whatsapp.yaml must route the first chat channel to operator or router")

if whatsapp_channel.get("dm_policy") != "allowlist":
    raise SystemExit("channels/whatsapp.yaml must keep dm_policy set to allowlist")

if whatsapp_channel.get("group_policy") != "disabled":
    raise SystemExit("channels/whatsapp.yaml must keep group_policy set to disabled")

openclaw_secret_values = openclaw_local_secret.get("stringData", {})
whatsapp_owner = openclaw_secret_values.get(whatsapp_channel.get("owner_env", "OPENCLAW_WHATSAPP_OWNER"))
enable_whatsapp_channel = isinstance(whatsapp_owner, str) and bool(whatsapp_owner.strip())
whatsapp_allow_from_raw = openclaw_secret_values.get("OPENCLAW_WHATSAPP_ALLOW_FROM", "")
whatsapp_allow_from = []
if enable_whatsapp_channel:
    whatsapp_allow_from.append("${OPENCLAW_WHATSAPP_OWNER}")
for candidate in str(whatsapp_allow_from_raw).split(","):
    candidate = candidate.strip()
    if candidate and candidate not in whatsapp_allow_from:
        whatsapp_allow_from.append(candidate)

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

model_ref = f"{provider_id}/{default_model}"

allowed_runtime_tools = {
    "web_fetch",
    "workflow_api_start_paper_intake",
    "workflow_api_start_literature_intake",
    "workflow_api_start_replication_intake",
    "workflow_api_dispatch_latest_user_message",
    "workflow_api_get_research_session_bootstrap_status",
    "workflow_api_bootstrap_research_session_from_latest_user_message",
    "workflow_api_create_research_session_from_latest_research_problem",
    "workflow_api_get_latest_research_session",
    "workflow_api_get_latest_research_session_context",
    "workflow_api_stage_research_problem_from_latest_session",
    "workflow_api_create_paper_intake_queue_from_latest_session",
    "workflow_api_stage_next_intake_from_latest_session",
    "workflow_api_create_paper_intake_queue_from_latest_research_problem",
    "workflow_api_get_latest_paper_intake_queue",
    "workflow_api_stage_next_intake_from_latest_queue",
    "workflow_api_get_latest_operation",
    "workflow_api_get_last_intake",
    "workflow_api_get_latest_source_document",
    "workflow_api_get_latest_interpretation",
    "workflow_api_create_assessment_from_latest_interpretation",
    "workflow_api_get_latest_assessment",
    "workflow_api_create_design_draft_from_last_intake",
    "workflow_api_create_design_draft_from_last_assessment",
    "workflow_api_get_last_design_draft",
    "workflow_api_get_execution_preflight_from_last_design",
    "workflow_api_review_last_design_for_literature_path",
    "workflow_api_create_validation_run_from_last_design",
    "workflow_api_get_last_run_status",
    "workflow_api_get_last_run_artifacts",
    "workflow_api_get_last_run_logs",
    "workflow_api_run_research_problem_pipeline",
    "workflow_api_run_latest_research_problem_pipeline",
    "workflow_api_get_families",
    "workflow_api_create_validation_run",
    "workflow_api_get_last_validation_run",
    "workflow_api_get_family_by_id",
}
allowed_runtime_tools.update(generated_workflow_lookup_tools)
allowed_runtime_profiles = {"minimal", "coding", "messaging", "full"}


def expanded_runtime_allow(agent_cfg: dict) -> list[str]:
    runtime_allow = list(agent_cfg.get("runtime_tools_allow", []))
    if "workflow_api_get_family_by_id" in runtime_allow:
        for tool_id in generated_workflow_lookup_tools:
            if tool_id not in runtime_allow:
                runtime_allow.append(tool_id)
    return runtime_allow

for agent_name, agent_cfg in agents.items():
    runtime_profile = agent_cfg.get("runtime_tools_profile")
    if runtime_profile and runtime_profile not in allowed_runtime_profiles:
        raise SystemExit(
            f"agent {agent_name!r} requested unsupported runtime tool profile {runtime_profile!r}"
        )
    for tool_id in expanded_runtime_allow(agent_cfg):
        if tool_id not in allowed_runtime_tools:
            raise SystemExit(
                f"agent {agent_name!r} requested unsupported runtime tool {tool_id!r}"
            )
    for tool_id in agent_cfg.get("runtime_tools_deny", []):
        if tool_id not in allowed_runtime_tools:
            raise SystemExit(
                f"agent {agent_name!r} requested unsupported runtime deny tool {tool_id!r}"
            )

provider_config = {
    "baseUrl": provider_base_url,
    "api": provider_api,
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

if provider_api_key_env:
    provider_config["apiKey"] = "${" + provider_api_key_env + "}"

runtime_config = {
    "gateway": {
        "mode": "local",
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
            provider_id: provider_config
        }
    },
    "agents": {
        "defaults": {
            "skipBootstrap": True,
            "model": {
                "primary": model_ref,
            },
            "compaction": {
                "keepRecentTokens": 3000,
                "recentTurnsPreserve": 4,
                "reserveTokens": 1024,
                "reserveTokensFloor": 0,
                "memoryFlush": {
                    "enabled": True,
                    "forceFlushTranscriptBytes": 0,
                },
            },
            "models": {
                model_ref: {
                    "alias": model_alias,
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
                    "timeoutSeconds": workflow_binding.get("timeoutSeconds", 10),
                    "paperIntakeRequest": paper_intake_request,
                    "literatureIntakeRequest": literature_intake_request,
                    "replicationIntakeRequest": replication_intake_request,
                    "literatureReviewRequest": literature_review_request,
                    "validationRunRequest": validation_run_request,
                    "knownWorkflowIds": known_workflow_ids,
                },
            },
        },
    },
}

if enable_whatsapp_channel:
    runtime_config["plugins"]["allow"].append("whatsapp")
    runtime_config["plugins"]["entries"]["whatsapp"] = {
        "enabled": True,
    }
    runtime_config["channels"] = {
        "whatsapp": {
            "defaultAccount": whatsapp_channel.get("account_id", "default"),
            "dmPolicy": whatsapp_channel["dm_policy"],
            "allowFrom": whatsapp_allow_from,
            "selfChatMode": bool(whatsapp_channel.get("self_chat_mode", False)),
            "groupPolicy": whatsapp_channel["group_policy"],
            "sendReadReceipts": bool(whatsapp_channel.get("send_read_receipts", False)),
            "accounts": {
                whatsapp_channel.get("account_id", "default"): {
                    "enabled": True,
                    "authDir": "/var/lib/openclaw/state/credentials/whatsapp/default",
                    "dmPolicy": whatsapp_channel["dm_policy"],
                    "allowFrom": whatsapp_allow_from,
                    "selfChatMode": bool(whatsapp_channel.get("self_chat_mode", False)),
                    "groupPolicy": whatsapp_channel["group_policy"],
                    "sendReadReceipts": bool(whatsapp_channel.get("send_read_receipts", False)),
                }
            },
        }
    }
    runtime_config["bindings"] = [
        {
            "agentId": whatsapp_channel["agent_id"],
            "match": {
                "channel": "whatsapp",
            },
        }
    ]

runtime_contract_lines = [
    "# OpenClaw Runtime Contract",
    "",
    "- source repo config: `services/openclaw-config`",
    "- build source revision: `" + build_source_revision + "`",
    "- build source label: `" + build_source_label + "`",
    "- generated runtime root: `/var/lib/openclaw/runtime`",
    "- generated native config file: `/var/lib/openclaw/runtime/openclaw.json`",
    "- generated agent workspaces: `/var/lib/openclaw/runtime/workspaces/<agent>/`",
    "- mirrored source tree: `/var/lib/openclaw/runtime/glasslab-config/`",
    "- workflow-api binding: "
    + workflow_binding["base_url"],
    "- provider base URL: "
    + provider_base_url,
    "- provider API: "
    + provider_api,
    "- provider id: "
    + provider_id,
    "- provider default model: "
    + default_model,
    "- workflow-api plugin path: `/var/lib/openclaw/runtime/glasslab-config/plugins/workflow-api-tool`",
    "- operator runtime allowlist includes repo-managed no-arg workflow family lookup tools derived from the approved registry IDs, alongside `workflow_api_get_families`, `workflow_api_create_validation_run`, `workflow_api_get_last_validation_run`, and the experimental `workflow_api_get_family_by_id` path",
    "- workflow-api tool audit log: `/var/lib/openclaw/state/workflow-api-tool/tool-call-audit.jsonl`",
]

if enable_whatsapp_channel:
    runtime_contract_lines.extend(
        [
            "- first chat channel: `whatsapp` in direct-message self-chat validation mode",
            "- whatsapp linked credentials path: `/var/lib/openclaw/state/credentials/whatsapp/default/`",
        ]
    )
else:
    runtime_contract_lines.extend(
        [
            "- first chat channel: disabled until `kubeadm/glasslab-v2/secrets/30-openclaw.local.yaml` defines `OPENCLAW_WHATSAPP_OWNER`",
        ]
    )

runtime_contract_lines.extend(
    [
        "",
        "The native runtime bundle is generated by `scripts/export-openclaw-config.sh`.",
    ]
)


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
    runtime_allow = expanded_runtime_allow(agent_cfg)
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
        f"- inference provider: `{provider_base_url}`",
        f"- default model: `{default_model}`",
        "",
        "Chat gateway references:",
        "- first chat channel: `whatsapp`",
        "- first chat route: `whatsapp` direct messages -> `operator` agent",
        "- first chat policy: self-chat only during validation, groups disabled",
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
                "allow": expanded_runtime_allow(agent_cfg),
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
(runtime_dir / "PROVENANCE.json").write_text(
    json.dumps(
        {
            "build_source_revision": build_source_revision,
            "build_source_label": build_source_label,
            "source_repo_config": "services/openclaw-config",
        },
        indent=2,
        sort_keys=True,
    )
    + "\n",
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
printf '[export-openclaw-config] build source revision: %s\n' "$GIT_SHA"
printf '[export-openclaw-config] build source label: %s\n' "$BUILD_SOURCE"
printf '[export-openclaw-config] configmap key: openclaw-runtime.tar.gz\n'
printf '[export-openclaw-config] in-container runtime root: /var/lib/openclaw/runtime\n'
printf '[export-openclaw-config] in-container config path: /var/lib/openclaw/runtime/openclaw.json\n'

if [[ "$APPLY_CONFIGMAP" == true ]]; then
  printf '[export-openclaw-config] applied configmap/%s in namespace %s\n' "$CONFIGMAP_NAME" "$NAMESPACE"
else
  printf '[export-openclaw-config] skipped ConfigMap apply (--no-apply)\n'
fi
