import { appendFile, mkdir, readFile, writeFile } from "node:fs/promises";
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

function resolvePaperIntakeRequest(api: any): Record<string, unknown> {
  const value = api?.pluginConfig?.paperIntakeRequest;
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(
      "plugins.entries.workflow-api-tool.config.paperIntakeRequest is required"
    );
  }
  return value;
}

function resolveLiteratureIntakeRequest(api: any): Record<string, unknown> {
  const value = api?.pluginConfig?.literatureIntakeRequest;
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(
      "plugins.entries.workflow-api-tool.config.literatureIntakeRequest is required"
    );
  }
  return value;
}

function resolveReplicationIntakeRequest(api: any): Record<string, unknown> {
  const value = api?.pluginConfig?.replicationIntakeRequest;
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(
      "plugins.entries.workflow-api-tool.config.replicationIntakeRequest is required"
    );
  }
  return value;
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

function resolveKnownWorkflowIds(api: any): string[] {
  const value = api?.pluginConfig?.knownWorkflowIds;
  if (!Array.isArray(value)) {
    throw new Error("plugins.entries.workflow-api-tool.config.knownWorkflowIds is required");
  }
  const workflowIds = value
    .map((item) => (typeof item === "string" ? item.trim() : ""))
    .filter(Boolean);
  if (workflowIds.length === 0) {
    throw new Error(
      "plugins.entries.workflow-api-tool.config.knownWorkflowIds must contain at least one workflow_id"
    );
  }
  return workflowIds;
}

function resolveStateDir(): string {
  return join(process.env.OPENCLAW_STATE_DIR || DEFAULT_STATE_DIR, "workflow-api-tool");
}

function resolveStatePath(name: string): string {
  return join(
    resolveStateDir(),
    name
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

async function appendAuditEvent(event: Record<string, unknown>): Promise<void> {
  const stateDir = resolveStateDir();
  await mkdir(stateDir, { recursive: true });
  const auditPath = resolveStatePath("tool-call-audit.jsonl");
  const record = {
    timestamp: new Date().toISOString(),
    ...event
  };
  await appendFile(auditPath, `${JSON.stringify(record)}\n`, "utf8");
}

async function saveLastRunId(runId: string): Promise<void> {
  const statePath = resolveStatePath("last-validation-run.json");
  await mkdir(dirname(statePath), { recursive: true });
  await writeFile(statePath, JSON.stringify({ run_id: runId }, null, 2));
}

async function loadLastRunId(): Promise<string> {
  const statePath = resolveStatePath("last-validation-run.json");
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
  description: "Narrow workflow-api helper for Glasslab v2 validation.",
  register(api: any) {
    api.registerTool(
      {
        name: "workflow_api_get_families",
        description: "List approved Glasslab v2 workflow families.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          try {
            const { endpoint, payload } = await requestJson(api, "/workflow-families");
            await appendAuditEvent({
              tool: "workflow_api_get_families",
              status: "ok",
              endpoint,
              result_count: Array.isArray(payload) ? payload.length : null
            });
            return buildJsonResult({
              endpoint,
              workflow_families: payload
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_get_families",
              status: "error",
              error: error instanceof Error ? error.message : String(error)
            });
            throw error;
          }
        }
      },
      { optional: true }
    );

    api.registerTool(
      {
        name: "workflow_api_start_paper_intake",
        description: "Create the repo-managed paper intake record.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          const requestBody = resolvePaperIntakeRequest(api);
          try {
            const { endpoint, payload } = await requestJson(api, "/intakes", {
              method: "POST",
              body: JSON.stringify(requestBody)
            });
            await appendAuditEvent({
              tool: "workflow_api_start_paper_intake",
              status: "ok",
              endpoint,
              intake_id: payload?.intake_id ?? null,
              source_type: payload?.source_type ?? null
            });
            return buildJsonResult({
              endpoint,
              request: requestBody,
              intake: payload
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_start_paper_intake",
              status: "error",
              error: error instanceof Error ? error.message : String(error)
            });
            throw error;
          }
        }
      },
      { optional: true }
    );

    api.registerTool(
      {
        name: "workflow_api_start_literature_intake",
        description: "Create the repo-managed literature-to-experiment intake record.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          const requestBody = resolveLiteratureIntakeRequest(api);
          try {
            const { endpoint, payload } = await requestJson(api, "/intakes", {
              method: "POST",
              body: JSON.stringify(requestBody)
            });
            await appendAuditEvent({
              tool: "workflow_api_start_literature_intake",
              status: "ok",
              endpoint,
              intake_id: payload?.intake_id ?? null,
              source_type: payload?.source_type ?? null
            });
            return buildJsonResult({
              endpoint,
              request: requestBody,
              intake: payload
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_start_literature_intake",
              status: "error",
              error: error instanceof Error ? error.message : String(error)
            });
            throw error;
          }
        }
      },
      { optional: true }
    );

    api.registerTool(
      {
        name: "workflow_api_start_replication_intake",
        description: "Create the repo-managed replication-lite intake record.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          const requestBody = resolveReplicationIntakeRequest(api);
          try {
            const { endpoint, payload } = await requestJson(api, "/intakes", {
              method: "POST",
              body: JSON.stringify(requestBody)
            });
            await appendAuditEvent({
              tool: "workflow_api_start_replication_intake",
              status: "ok",
              endpoint,
              intake_id: payload?.intake_id ?? null,
              source_type: payload?.source_type ?? null
            });
            return buildJsonResult({
              endpoint,
              request: requestBody,
              intake: payload
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_start_replication_intake",
              status: "error",
              error: error instanceof Error ? error.message : String(error)
            });
            throw error;
          }
        }
      },
      { optional: true }
    );

    api.registerTool(
      {
        name: "workflow_api_get_last_intake",
        description: "Fetch the most recent intake record.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          try {
            const { endpoint, payload } = await requestJson(api, "/intakes/latest");
            await appendAuditEvent({
              tool: "workflow_api_get_last_intake",
              status: "ok",
              endpoint,
              intake_id: payload?.intake_id ?? null,
              intake_status: payload?.status ?? null
            });
            return buildJsonResult({
              endpoint,
              intake: payload
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_get_last_intake",
              status: "error",
              error: error instanceof Error ? error.message : String(error)
            });
            throw error;
          }
        }
      },
      { optional: true }
    );

    api.registerTool(
      {
        name: "workflow_api_create_design_draft_from_last_intake",
        description: "Create a design draft from the latest intake record.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          try {
            const { endpoint, payload } = await requestJson(api, "/design-drafts/from-latest-intake", {
              method: "POST"
            });
            await appendAuditEvent({
              tool: "workflow_api_create_design_draft_from_last_intake",
              status: "ok",
              endpoint,
              design_id: payload?.design_id ?? null,
              design_status: payload?.status ?? null,
              workflow_id: payload?.workflow_id ?? null
            });
            return buildJsonResult({
              endpoint,
              design_draft: payload
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_create_design_draft_from_last_intake",
              status: "error",
              error: error instanceof Error ? error.message : String(error)
            });
            throw error;
          }
        }
      },
      { optional: true }
    );

    api.registerTool(
      {
        name: "workflow_api_get_last_design_draft",
        description: "Fetch the most recent design draft.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          try {
            const { endpoint, payload } = await requestJson(api, "/design-drafts/latest");
            await appendAuditEvent({
              tool: "workflow_api_get_last_design_draft",
              status: "ok",
              endpoint,
              design_id: payload?.design_id ?? null,
              design_status: payload?.status ?? null,
              workflow_id: payload?.workflow_id ?? null
            });
            return buildJsonResult({
              endpoint,
              design_draft: payload
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_get_last_design_draft",
              status: "error",
              error: error instanceof Error ? error.message : String(error)
            });
            throw error;
          }
        }
      },
      { optional: true }
    );

    api.registerTool(
      {
        name: "workflow_api_create_validation_run_from_last_design",
        description: "Create a validation run from the latest design draft.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          try {
            const { endpoint, payload } = await requestJson(api, "/runs/from-latest-design-draft", {
              method: "POST"
            });
            const runId = String(payload?.run_id || "").trim();
            if (runId) {
              await saveLastRunId(runId);
            }
            await appendAuditEvent({
              tool: "workflow_api_create_validation_run_from_last_design",
              status: "ok",
              endpoint,
              run_id: runId || null,
              source_design_id: payload?.source_design_id ?? null,
              source_intake_id: payload?.source_intake_id ?? null
            });
            return buildJsonResult({
              endpoint,
              run_id: runId || null,
              run: payload
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_create_validation_run_from_last_design",
              status: "error",
              error: error instanceof Error ? error.message : String(error)
            });
            throw error;
          }
        }
      },
      { optional: true }
    );

    api.registerTool(
      {
        name: "workflow_api_create_validation_run",
        description: "Create the repo-managed validation run.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          const requestBody = resolveValidationRunRequest(api);
          try {
            const { endpoint, payload } = await requestJson(api, "/runs", {
              method: "POST",
              body: JSON.stringify(requestBody)
            });
            const runId = String(payload?.run_id || "").trim();
            if (!runId) {
              throw new Error("workflow-api create_run response did not include run_id");
            }
            await saveLastRunId(runId);
            await appendAuditEvent({
              tool: "workflow_api_create_validation_run",
              status: "ok",
              endpoint,
              run_id: runId,
              workflow_id: requestBody.workflow_id
            });
            return buildJsonResult({
              endpoint,
              request: requestBody,
              run_id: runId,
              run: payload
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_create_validation_run",
              status: "error",
              workflow_id: requestBody.workflow_id,
              error: error instanceof Error ? error.message : String(error)
            });
            throw error;
          }
        }
      },
      { optional: true }
    );

    api.registerTool(
      {
        name: "workflow_api_get_last_run_status",
        description: "Fetch the latest stored run record and focus on status.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          try {
            const runId = await loadLastRunId();
            const { endpoint, payload } = await requestJson(
              api,
              `/runs/${encodeURIComponent(runId)}`
            );
            await appendAuditEvent({
              tool: "workflow_api_get_last_run_status",
              status: "ok",
              endpoint,
              run_id: runId,
              run_status: payload?.status?.status ?? null
            });
            return buildJsonResult({
              endpoint,
              run_id: runId,
              status: payload?.status ?? null,
              run: payload
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_get_last_run_status",
              status: "error",
              error: error instanceof Error ? error.message : String(error)
            });
            throw error;
          }
        }
      },
      { optional: true }
    );

    api.registerTool(
      {
        name: "workflow_api_get_last_validation_run",
        description: "Fetch the last validation run.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          try {
            const runId = await loadLastRunId();
            const { endpoint, payload } = await requestJson(
              api,
              `/runs/${encodeURIComponent(runId)}`
            );
            await appendAuditEvent({
              tool: "workflow_api_get_last_validation_run",
              status: "ok",
              endpoint,
              run_id: runId
            });
            return buildJsonResult({
              endpoint,
              run_id: runId,
              run: payload
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_get_last_validation_run",
              status: "error",
              error: error instanceof Error ? error.message : String(error)
            });
            throw error;
          }
        }
      },
      { optional: true }
    );

    const knownWorkflowIds = resolveKnownWorkflowIds(api);
    api.registerTool(
      {
        name: "workflow_api_get_last_run_artifacts",
        description: "Fetch the artifact index for the latest stored run.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          try {
            const runId = await loadLastRunId();
            const { endpoint, payload } = await requestJson(
              api,
              `/runs/${encodeURIComponent(runId)}/artifacts`
            );
            const artifactCount = Array.isArray(payload?.artifacts?.artifacts)
              ? payload.artifacts.artifacts.length
              : null;
            await appendAuditEvent({
              tool: "workflow_api_get_last_run_artifacts",
              status: "ok",
              endpoint,
              run_id: runId,
              artifact_count: artifactCount
            });
            return buildJsonResult({
              endpoint,
              run_id: runId,
              artifacts: payload
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_get_last_run_artifacts",
              status: "error",
              error: error instanceof Error ? error.message : String(error)
            });
            throw error;
          }
        }
      },
      { optional: true }
    );

    api.registerTool(
      {
        name: "workflow_api_get_last_run_logs",
        description: "Fetch the logs for the latest stored run.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          try {
            const runId = await loadLastRunId();
            const { endpoint, payload } = await requestJson(
              api,
              `/runs/${encodeURIComponent(runId)}/logs`
            );
            const logCount = Array.isArray(payload?.logs) ? payload.logs.length : null;
            await appendAuditEvent({
              tool: "workflow_api_get_last_run_logs",
              status: "ok",
              endpoint,
              run_id: runId,
              log_count: logCount
            });
            return buildJsonResult({
              endpoint,
              run_id: runId,
              logs: payload
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_get_last_run_logs",
              status: "error",
              error: error instanceof Error ? error.message : String(error)
            });
            throw error;
          }
        }
      },
      { optional: true }
    );

    api.registerTool(
      {
        name: "workflow_api_get_family_by_id",
        description: "Fetch one approved workflow family by exact workflow_id.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {
            workflow_id: {
              type: "string",
              enum: knownWorkflowIds,
              description: "Exact approved workflow_id."
            }
          },
          required: ["workflow_id"]
        },
        async execute(args: any) {
          const workflowId = typeof args?.workflow_id === "string" ? args.workflow_id.trim() : "";
          if (!workflowId) {
            await appendAuditEvent({
              tool: "workflow_api_get_family_by_id",
              status: "error",
              requested_workflow_id: workflowId,
              error: "workflow_id is required"
            });
            throw new Error("workflow_id is required");
          }
          try {
            const { endpoint, payload } = await requestJson(api, "/workflow-families");
            const families = Array.isArray(payload) ? payload : [];
            const match = families.find(
              (item) =>
                item &&
                typeof item === "object" &&
                item.workflow_id === workflowId
            );
            if (!match) {
              throw new Error(`workflow_id not found in approved workflow families: ${workflowId}`);
            }
            const statePath = resolveStatePath("last-family-lookup.json");
            await mkdir(dirname(statePath), { recursive: true });
            await writeFile(
              statePath,
              JSON.stringify(
                {
                  requested_workflow_id: workflowId,
                  matched_workflow_id: workflowId,
                  endpoint
                },
                null,
                2
              )
            );
            await appendAuditEvent({
              tool: "workflow_api_get_family_by_id",
              status: "ok",
              endpoint,
              requested_workflow_id: workflowId,
              matched_workflow_id: workflowId
            });
            return buildJsonResult({
              endpoint,
              requested_workflow_id: workflowId,
              workflow_family: match
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_get_family_by_id",
              status: "error",
              requested_workflow_id: workflowId,
              error: error instanceof Error ? error.message : String(error)
            });
            throw error;
          }
        }
      },
      { optional: true }
    );
  }
};

export default plugin;
