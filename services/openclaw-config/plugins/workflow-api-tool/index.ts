import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";

const DEFAULT_TIMEOUT_SECONDS = 10;
const DEFAULT_STATE_DIR = "/var/lib/openclaw/state";

function resolveBaseUrl(api: any): string {
  const value = api?.pluginConfig?.baseUrl;
  if (typeof value !== "string" || !value.trim()) {
    throw new Error("plugins.entries.workflow-api-tool.config.baseUrl is required");
  }
  return value.trim();
}

function resolveTimeoutSeconds(api: any): number {
  const value = api?.pluginConfig?.timeoutSeconds;
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return DEFAULT_TIMEOUT_SECONDS;
  }
  return Math.max(1, Math.min(30, Math.floor(value)));
}

function buildJsonResult(payload: unknown) {
  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(payload, null, 2)
      }
    ]
  };
}

function resolveValidationRunRequest(api: any): Record<string, unknown> {
  const value = api?.pluginConfig?.validationRunRequest;
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(
      "plugins.entries.workflow-api-tool.config.validationRunRequest is required"
    );
  }
  return value;
}

function resolveStatePath(): string {
  return join(
    process.env.OPENCLAW_STATE_DIR || DEFAULT_STATE_DIR,
    "workflow-api-tool",
    "last-validation-run.json"
  );
}

async function requestJson(
  api: any,
  path: string,
  init: RequestInit = {}
): Promise<{ endpoint: string; payload: any }> {
  const baseUrl = resolveBaseUrl(api);
  const timeoutSeconds = resolveTimeoutSeconds(api);
  const endpoint = new URL(path, baseUrl).toString();
  const response = await fetch(endpoint, {
    ...init,
    headers: {
      accept: "application/json",
      ...(init.body ? { "content-type": "application/json" } : {}),
      ...(init.headers ?? {})
    },
    signal: AbortSignal.timeout(timeoutSeconds * 1000)
  });

  const responseText = await response.text();
  let payload: unknown = null;
  if (responseText) {
    try {
      payload = JSON.parse(responseText);
    } catch {
      payload = responseText;
    }
  }

  if (!response.ok) {
    const detail =
      typeof payload === "string" ? payload : JSON.stringify(payload, null, 2);
    throw new Error(
      `workflow-api request failed (${response.status}) for ${endpoint}: ${
        detail.slice(0, 2000) || response.statusText
      }`
    );
  }

  return { endpoint, payload };
}

async function saveLastRunId(runId: string): Promise<void> {
  const statePath = resolveStatePath();
  await mkdir(dirname(statePath), { recursive: true });
  await writeFile(statePath, JSON.stringify({ run_id: runId }, null, 2));
}

async function loadLastRunId(): Promise<string> {
  const statePath = resolveStatePath();
  const payload = JSON.parse(await readFile(statePath, "utf8"));
  const runId = String(payload?.run_id || "").trim();
  if (!runId) {
    throw new Error(
      "no last validation run is recorded yet; create the validation run before retrieving it"
    );
  }
  return runId;
}

const plugin = {
  id: "workflow-api-tool",
  name: "Workflow API Tool",
  description:
    "Narrow workflow-api helper for Glasslab v2 operator validation and bounded run lifecycle.",
  register(api: any) {
    api.registerTool(
      {
        name: "workflow_api_get_families",
        description:
          "Fetch the approved Glasslab v2 workflow families from the configured internal workflow-api service.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          const { endpoint, payload } = await requestJson(api, "/workflow-families");
          return buildJsonResult({
            endpoint,
            workflow_families: payload
          });
        }
      },
      { optional: true }
    );

    api.registerTool(
      {
        name: "workflow_api_create_validation_run",
        description:
          "Create the repo-managed bounded Glasslab v2 validation run via workflow-api.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          const requestBody = resolveValidationRunRequest(api);
          const { endpoint, payload } = await requestJson(api, "/runs", {
            method: "POST",
            body: JSON.stringify(requestBody)
          });
          const runId = String(payload?.run_id || "").trim();
          if (!runId) {
            throw new Error("workflow-api create_run response did not include run_id");
          }
          await saveLastRunId(runId);
          return buildJsonResult({
            endpoint,
            request: requestBody,
            run_id: runId,
            run: payload
          });
        }
      },
      { optional: true }
    );

    api.registerTool(
      {
        name: "workflow_api_get_last_validation_run",
        description:
          "Fetch the last validation run recorded by workflow_api_create_validation_run using workflow-api GET /runs/{id}.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          const runId = await loadLastRunId();
          const { endpoint, payload } = await requestJson(
            api,
            `/runs/${encodeURIComponent(runId)}`
          );
          return buildJsonResult({
            endpoint,
            run_id: runId,
            run: payload
          });
        }
      },
      { optional: true }
    );
  }
};

export default plugin;
