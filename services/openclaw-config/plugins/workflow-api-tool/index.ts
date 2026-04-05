import { appendFile, mkdir, readFile, readdir, stat, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";

const DEFAULT_TIMEOUT_SECONDS = 10;
const MAX_TIMEOUT_SECONDS = 90;
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
  return Math.max(1, Math.min(MAX_TIMEOUT_SECONDS, Math.floor(value)));
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

function extractWorkflowApiErrorDetail(error: unknown): string {
  if (!(error instanceof Error)) {
    return String(error);
  }
  const match = error.message.match(/workflow-api request failed \(\d+\) for [^:]+: (.+)$/s);
  return (match?.[1] ?? error.message).trim();
}

function isWorkflowApiTimeout(error: unknown): boolean {
  const detail = extractWorkflowApiErrorDetail(error).toLowerCase();
  return detail.includes("aborted due to timeout") || detail.includes("signal timed out");
}

async function sleep(ms: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

async function recoverLatestQueueAfterTimeout(
  api: any,
  path: string,
  attempts: number = 6,
  delayMs: number = 5000
): Promise<{ endpoint: string; payload: any } | null> {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    await sleep(delayMs);
    try {
      return await requestJson(api, path);
    } catch {
      continue;
    }
  }
  return null;
}

async function ensureLatestResearchSession(
  api: any
): Promise<{
  bootstrapEndpoint: string;
  bootstrapStatus: any;
  session: any;
  researchProblem: any | null;
  createdOrRecovered: boolean;
}> {
  const { endpoint: bootstrapEndpoint, payload: bootstrapStatus } = await requestJson(
    api,
    "/research-sessions/bootstrap-status"
  );

  if (bootstrapStatus?.active_session) {
    return {
      bootstrapEndpoint,
      bootstrapStatus,
      session: bootstrapStatus.active_session,
      researchProblem: bootstrapStatus?.staged_research_problem ?? null,
      createdOrRecovered: false
    };
  }

  if (bootstrapStatus?.can_create_session_from_latest_problem) {
    const { payload } = await requestJson(api, "/research-sessions/from-latest-research-problem", {
      method: "POST"
    });
    return {
      bootstrapEndpoint,
      bootstrapStatus,
      session: payload,
      researchProblem: bootstrapStatus?.staged_research_problem ?? null,
      createdOrRecovered: true
    };
  }

  if (bootstrapStatus?.recommended_next_action === "create-session-manually") {
    const { payload } = await requestJson(api, "/research-sessions/bootstrap", {
      method: "POST"
    });
    if (!payload?.session) {
      throw new Error("workflow-api bootstrap did not return a research session");
    }
    return {
      bootstrapEndpoint,
      bootstrapStatus,
      session: payload.session,
      researchProblem: payload?.staged_research_problem ?? null,
      createdOrRecovered: true
    };
  }

  throw new Error(
    `cannot apply session skills yet: ${String(bootstrapStatus?.detail || "no research session is available")}`
  );
}

async function bootstrapResearchSessionFromLatestUserMessage(api: any): Promise<{
  goalStatement: string;
  session: any;
  researchProblem: any | null;
  queue: any;
  bootstrapEndpoint: string;
  sessionEndpoint: string;
  problemEndpoint: string;
  queueEndpoint: string;
  bootstrapAction: string | null;
}> {
  let goalStatement = "";
  try {
    goalStatement = await loadLatestUserIdeaText();
  } catch {
    goalStatement = "";
  }
  if (goalStatement) {
    const genericCommand =
      /^(start|create|begin|open|make|do|try)\b/i.test(goalStatement) &&
      /\b(session|paper intake|literature harvest|research problem)\b/i.test(goalStatement) &&
      !/\b(on|about|for)\b/i.test(goalStatement);
    if (genericCommand) {
      throw new Error("latest user message looks like an instruction, not a concrete research idea");
    }
  }

  const requestBody = {
    goal_statement: goalStatement || null,
    priorities: [],
    submitted_by: "openclaw-operator"
  };
  const { endpoint: bootstrapEndpoint, payload } = await requestJson(
    api,
    "/research-sessions/start-literature-search",
    { method: "POST", body: JSON.stringify(requestBody) }
  );

  const session = payload?.session ?? null;
  const sessionId = typeof session?.session_id === "string" ? session.session_id.trim() : "";
  if (!sessionId) {
    throw new Error("workflow-api literature start did not return a research session");
  }
  const researchProblem = payload?.research_problem ?? null;
  const queue = payload?.paper_intake_queue ?? null;
  const sessionEndpoint = bootstrapEndpoint;
  const problemEndpoint = bootstrapEndpoint;
  const queueEndpoint = bootstrapEndpoint;

  return {
    goalStatement,
    session,
    researchProblem,
    queue,
    bootstrapEndpoint,
    sessionEndpoint,
    problemEndpoint,
    queueEndpoint,
    bootstrapAction: typeof payload?.action === "string" ? payload.action : null
  };
}

async function startLiteratureSearchForGoal(
  api: any,
  goalStatement: string
): Promise<{
  goalStatement: string;
  session: any;
  researchProblem: any | null;
  queue: any;
  bootstrapEndpoint: string;
  bootstrapAction: string | null;
}> {
  const requestBody = {
    goal_statement: goalStatement || null,
    priorities: [],
    submitted_by: "openclaw-operator"
  };
  const { endpoint: bootstrapEndpoint, payload } = await requestJson(
    api,
    "/research-sessions/start-literature-search",
    { method: "POST", body: JSON.stringify(requestBody) }
  );
  const session = payload?.session ?? null;
  const sessionId = typeof session?.session_id === "string" ? session.session_id.trim() : "";
  if (!sessionId) {
    throw new Error("workflow-api literature start did not return a research session");
  }
  return {
    goalStatement,
    session,
    researchProblem: payload?.research_problem ?? null,
    queue: payload?.paper_intake_queue ?? null,
    bootstrapEndpoint,
    bootstrapAction: typeof payload?.action === "string" ? payload.action : null
  };
}

type RoutedUserIntent =
  | "start-runner"
  | "start-literature-search"
  | "runner-status"
  | "refresh-literature-queue"
  | "stage-next-paper"
  | "add-manual-paper"
  | "summarize-session"
  | "create-interpretation"
  | "create-design"
  | "execution-preflight"
  | "create-run"
  | "start-autoresearch"
  | "draft-methodologies"
  | "draft-notebook"
  | "refine-notebook"
  | "launch-iteration"
  | "decide-latest"
  | "autoresearch-summary"
  | "model-comparison"
  | "runner-compare"
  | "next-runner-step"
  | "capture-note"
  | "latest-operation"
  | "help"
  | "unsupported";

type ExplicitCommand =
  | { command: "start"; argument: string }
  | { command: "research"; argument: string }
  | { command: "status"; argument: "" }
  | { command: "more-papers"; argument: "" }
  | { command: "next-paper"; argument: "" }
  | { command: "add-paper"; argument: string }
  | { command: "session"; argument: "" }
  | { command: "interpret"; argument: "" }
  | { command: "design"; argument: "" }
  | { command: "preflight"; argument: "" }
  | { command: "run"; argument: "" }
  | { command: "start-autoresearch"; argument: "" }
  | { command: "draft-methodologies"; argument: "" }
  | { command: "draft-notebook"; argument: "" }
  | { command: "refine-notebook"; argument: "" }
  | { command: "launch-iteration"; argument: "" }
  | { command: "decide-latest"; argument: "" }
  | { command: "autoresearch"; argument: "" }
  | { command: "model-comparison"; argument: "" }
  | { command: "compare"; argument: "" }
  | { command: "next"; argument: "" }
  | { command: "note"; argument: string }
  | { command: "op"; argument: "" }
  | { command: "help"; argument: "" };

function parseExplicitCommand(message: string): ExplicitCommand | null {
  const trimmed = message.trim();
  let match =
    trimmed.match(/^!([a-z0-9-]+)(?:\s+([\s\S]+))?$/i) ||
    trimmed.match(/^([a-z0-9-]+):(?:\s*([\s\S]+))?$/i);
  if (!match) {
    return null;
  }
  const command = match[1].toLowerCase();
  const argument = (match[2] || "").trim();
  if (command === "start") {
    return { command: "start", argument };
  }
  if (command === "research") {
    return { command: "research", argument };
  }
  if (command === "status") {
    return { command: "status", argument: "" };
  }
  if (command === "more-papers" || command === "papers") {
    return { command: "more-papers", argument: "" };
  }
  if (command === "next-paper") {
    return { command: "next-paper", argument: "" };
  }
  if (command === "add-paper") {
    return { command: "add-paper", argument };
  }
  if (command === "session") {
    return { command: "session", argument: "" };
  }
  if (command === "interpret") {
    return { command: "interpret", argument: "" };
  }
  if (command === "design") {
    return { command: "design", argument: "" };
  }
  if (command === "preflight") {
    return { command: "preflight", argument: "" };
  }
  if (command === "run") {
    return { command: "run", argument: "" };
  }
  if (command === "start-autoresearch") {
    return { command: "start-autoresearch", argument: "" };
  }
  if (command === "draft-methodologies") {
    return { command: "draft-methodologies", argument: "" };
  }
  if (command === "draft-notebook") {
    return { command: "draft-notebook", argument: "" };
  }
  if (command === "refine-notebook") {
    return { command: "refine-notebook", argument: "" };
  }
  if (command === "launch-iteration") {
    return { command: "launch-iteration", argument: "" };
  }
  if (command === "decide-latest") {
    return { command: "decide-latest", argument: "" };
  }
  if (command === "autoresearch") {
    return { command: "autoresearch", argument: "" };
  }
  if (command === "model-comparison") {
    return { command: "model-comparison", argument: "" };
  }
  if (command === "compare") {
    return { command: "compare", argument: "" };
  }
  if (command === "next") {
    return { command: "next", argument: "" };
  }
  if (command === "note") {
    return { command: "note", argument };
  }
  if (command === "op") {
    return { command: "op", argument: "" };
  }
  if (command === "help") {
    return { command: "help", argument: "" };
  }
  return null;
}

function commandHelpText(): string {
  return [
    "Primary runner commands:",
    "!start <topic>      or  start: <topic>",
    "!status             or  status:",
    "!run                or  run:",
    "!next               or  next:",
    "!compare            or  compare:",
    "",
    "Debug commands:",
    "!research <topic>  or  research: <topic>",
    "!more-papers       or  papers:",
    "!next-paper        or  next-paper:",
    "!add-paper <url|title> or  add-paper: <url|title>",
    "!session           or  session:",
    "!interpret         or  interpret:",
    "!design            or  design:",
    "!preflight         or  preflight:",
    "!run               or  run:",
    "!start-autoresearch or start-autoresearch:",
    "!draft-methodologies or draft-methodologies:",
    "!draft-notebook    or  draft-notebook:",
    "!refine-notebook   or  refine-notebook:",
    "!launch-iteration  or  launch-iteration:",
    "!decide-latest     or  decide-latest:",
    "!autoresearch      or  autoresearch:",
    "!model-comparison  or  model-comparison:",
    "!note <text>       or  note: <text>",
    "!op                or  op:",
    "!help              or  help:"
  ].join("\n");
}

function detectRoutedUserIntent(message: string): RoutedUserIntent {
  const text = message.trim().toLowerCase();
  if (!text) {
    return "unsupported";
  }

  const explicitCommand = parseExplicitCommand(message);
  if (explicitCommand) {
    if (explicitCommand.command === "start") {
      return "start-runner";
    }
    if (explicitCommand.command === "research") {
      return "start-literature-search";
    }
    if (explicitCommand.command === "status") {
      return "runner-status";
    }
    if (explicitCommand.command === "more-papers") {
      return "refresh-literature-queue";
    }
    if (explicitCommand.command === "next-paper") {
      return "stage-next-paper";
    }
    if (explicitCommand.command === "add-paper") {
      return "add-manual-paper";
    }
    if (explicitCommand.command === "session") {
      return "summarize-session";
    }
    if (explicitCommand.command === "interpret") {
      return "create-interpretation";
    }
    if (explicitCommand.command === "design") {
      return "create-design";
    }
    if (explicitCommand.command === "preflight") {
      return "execution-preflight";
    }
    if (explicitCommand.command === "run") {
      return "create-run";
    }
    if (explicitCommand.command === "start-autoresearch") {
      return "start-autoresearch";
    }
    if (explicitCommand.command === "draft-methodologies") {
      return "draft-methodologies";
    }
    if (explicitCommand.command === "draft-notebook") {
      return "draft-notebook";
    }
    if (explicitCommand.command === "refine-notebook") {
      return "refine-notebook";
    }
    if (explicitCommand.command === "launch-iteration") {
      return "launch-iteration";
    }
    if (explicitCommand.command === "decide-latest") {
      return "decide-latest";
    }
    if (explicitCommand.command === "autoresearch") {
      return "autoresearch-summary";
    }
    if (explicitCommand.command === "model-comparison") {
      return "model-comparison";
    }
    if (explicitCommand.command === "compare") {
      return "runner-compare";
    }
    if (explicitCommand.command === "next") {
      return "next-runner-step";
    }
    if (explicitCommand.command === "note") {
      return "capture-note";
    }
    if (explicitCommand.command === "op") {
      return "latest-operation";
    }
    if (explicitCommand.command === "help") {
      return "help";
    }
  }

  if (
    /\b(next paper|next intake|another paper|stage next|ingest next|review next paper)\b/.test(text)
  ) {
    return "stage-next-paper";
  }

  if (/\b(add paper|queue paper|manual paper)\b/.test(text)) {
    return "add-manual-paper";
  }

  if (
    /\b(summarize|summary|what('| i)?s the current state|where are we|current literature|session context|what did you find)\b/.test(
      text
    )
  ) {
    return "summarize-session";
  }

  if (
    /\b(note|remember|keep in mind|save this|capture this|focus on|prioritize)\b/.test(text)
  ) {
    return "capture-note";
  }

  if (
    /\b(start|begin|open|create|help me investigate|investigate|research|literature search|gather papers|look for papers|find papers)\b/.test(
      text
    )
  ) {
    return "start-literature-search";
  }

  return "unsupported";
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

function resolveLiteratureReviewRequest(api: any): Record<string, unknown> {
  const value = api?.pluginConfig?.literatureReviewRequest;
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(
      "plugins.entries.workflow-api-tool.config.literatureReviewRequest is required"
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

function buildWorkflowIdProperty(knownWorkflowIds: string[]) {
  return {
    type: "string",
    minLength: 1,
    enum: knownWorkflowIds,
    oneOf: knownWorkflowIds.map((workflowId) => ({
      const: workflowId,
      title: workflowId
    })),
    examples: knownWorkflowIds,
    description: `Exact approved workflow_id. Must be one of: ${knownWorkflowIds.join(", ")}.`
  };
}

function buildWorkflowLookupToolName(workflowId: string): string {
  const slug = workflowId
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return `workflow_api_get_family_${slug || "unknown"}`;
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

function resolveAgentSessionDirsRoot(): string {
  return join(process.env.OPENCLAW_STATE_DIR || DEFAULT_STATE_DIR, "agents");
}

function extractTextContent(content: unknown): string {
  if (!Array.isArray(content)) {
    return "";
  }
  return content
    .flatMap((item) => {
      if (!item || typeof item !== "object") {
        return [];
      }
      const record = item as Record<string, unknown>;
      const type = typeof record.type === "string" ? record.type : "";
      if (type !== "text") {
        return [];
      }
      const text = typeof record.text === "string" ? record.text.trim() : "";
      return text ? [text] : [];
    })
    .join("\n\n")
    .trim();
}

function cleanLatestUserIdea(raw: string): string {
  let text = raw.replace(/\r/g, "").trim();
  text = text.replace(/Conversation info \(untrusted metadata\):\s*```[\s\S]*?```/g, "").trim();
  text = text.replace(/Sender \(untrusted metadata\):\s*```[\s\S]*?```/g, "").trim();
  if (/^System:/m.test(text) && /WhatsApp gateway connected\./.test(text)) {
    text = text.replace(/^System:[\s\S]*$/m, "").trim();
  }
  const paragraphs = text
    .split(/\n\s*\n/)
    .map((item) => item.trim())
    .filter(Boolean)
    .filter((item) => item !== "```");
  const candidate = (paragraphs.length > 0 ? paragraphs[paragraphs.length - 1] : text).trim();
  return candidate.replace(/\s+/g, " ").trim();
}

async function loadLatestUserIdeaText(): Promise<string> {
  const agentsDir = resolveAgentSessionDirsRoot();
  const agentEntries = await readdir(agentsDir, { withFileTypes: true });
  const sessionFiles = await Promise.all(
    agentEntries
      .filter((entry) => entry.isDirectory())
      .flatMap((entry) => {
        const sessionsDir = join(agentsDir, entry.name, "sessions");
        return [
          (async () => {
            try {
              const entries = await readdir(sessionsDir, { withFileTypes: true });
              const files = await Promise.all(
                entries
                  .filter((sessionEntry) => sessionEntry.isFile())
                  .map(async (sessionEntry) => {
                    const name = sessionEntry.name;
                    if (
                      !name.endsWith(".jsonl") ||
                      name.includes(".reset.") ||
                      name.endsWith(".lock")
                    ) {
                      return null;
                    }
                    const path = join(sessionsDir, name);
                    const meta = await stat(path);
                    return { path, mtimeMs: meta.mtimeMs };
                  })
              );
              return files.filter(
                (item): item is { path: string; mtimeMs: number } => item !== null
              );
            } catch {
              return [];
            }
          })()
        ];
      })
  ).then((groups) => groups.flat());
  const ordered = sessionFiles
    .sort((left, right) => right.mtimeMs - left.mtimeMs);
  for (const sessionFile of ordered) {
    const raw = await readFile(sessionFile.path, "utf8");
    const lines = raw
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
    for (let index = lines.length - 1; index >= 0; index -= 1) {
      try {
        const payload = JSON.parse(lines[index]);
        if (payload?.type !== "message") {
          continue;
        }
        const role = payload?.message?.role;
        if (role !== "user") {
          continue;
        }
        const text = extractTextContent(payload?.message?.content);
        const cleaned = cleanLatestUserIdea(text);
        if (cleaned) {
          return cleaned;
        }
      } catch {
        continue;
      }
    }
  }
  throw new Error("no recent user idea was found in the agent session history");
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

async function getLatestSessionId(api: any): Promise<string> {
  const { payload } = await requestJson(api, "/research-sessions/latest/context");
  const sessionId = String(payload?.session?.session_id || "").trim();
  if (!sessionId) {
    throw new Error("research session not found");
  }
  return sessionId;
}

function isMissingCampaignError(error: unknown): boolean {
  const detail = extractWorkflowApiErrorDetail(error).toLowerCase();
  return detail.includes("campaign") || detail.includes("autoresearch");
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
    const knownWorkflowIds = resolveKnownWorkflowIds(api);
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
        description: "Fetch the active research session's latest intake record.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          try {
            const { endpoint, payload } = await requestJson(api, "/research-sessions/latest/intake");
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
        name: "workflow_api_get_latest_interpretation",
        description: "Fetch the active research session's latest interpretation, including literature state, gaps, and bounded experiment ideas.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          try {
            const { endpoint, payload } = await requestJson(api, "/research-sessions/latest/interpretation");
            await appendAuditEvent({
              tool: "workflow_api_get_latest_interpretation",
              status: "ok",
              endpoint,
              interpretation_id: payload?.interpretation_id ?? null,
              intake_id: payload?.intake_id ?? null
            });
            return buildJsonResult({
              endpoint,
              interpretation: payload
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_get_latest_interpretation",
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
        name: "workflow_api_create_assessment_from_latest_interpretation",
        description: "Apply the assessment skill to the latest research session.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          try {
            const { endpoint, payload } = await requestJson(api, "/research-sessions/latest/skills/assessment", {
              method: "POST"
            });
            await appendAuditEvent({
              tool: "workflow_api_create_assessment_from_latest_interpretation",
              status: "ok",
              endpoint,
              assessment_id: payload?.assessment_id ?? null,
              recommendation: payload?.recommendation ?? null,
              recommended_workflow_id: payload?.recommended_workflow_id ?? null
            });
            return buildJsonResult({
              endpoint,
              assessment: payload
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_create_assessment_from_latest_interpretation",
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
        name: "workflow_api_get_latest_assessment",
        description: "Fetch the active research session's latest replicability assessment record.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          try {
            const { endpoint, payload } = await requestJson(api, "/research-sessions/latest/assessment");
            await appendAuditEvent({
              tool: "workflow_api_get_latest_assessment",
              status: "ok",
              endpoint,
              assessment_id: payload?.assessment_id ?? null,
              recommendation: payload?.recommendation ?? null
            });
            return buildJsonResult({
              endpoint,
              assessment: payload
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_get_latest_assessment",
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
        description: "Apply the design skill to the latest research session.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          try {
            const { endpoint, payload } = await requestJson(api, "/research-sessions/latest/skills/design", {
              method: "POST"
            });
            await appendAuditEvent({
              tool: "workflow_api_create_design_draft_from_last_assessment",
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
              tool: "workflow_api_create_design_draft_from_last_assessment",
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
        name: "workflow_api_create_design_draft_from_last_assessment",
        description: "Apply the design skill to the latest research session, preferring the latest ready assessment.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          try {
            const { endpoint, payload } = await requestJson(api, "/research-sessions/latest/skills/design", {
              method: "POST"
            });
            await appendAuditEvent({
              tool: "workflow_api_create_design_draft_from_last_assessment",
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
              tool: "workflow_api_create_design_draft_from_last_assessment",
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
        description: "Fetch the active research session's latest design draft.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          try {
            const { endpoint, payload } = await requestJson(api, "/research-sessions/latest/design");
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
        name: "workflow_api_get_execution_preflight_from_last_design",
        description: "Fetch execution preflight for the workflow referenced by the latest design draft.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          try {
            const { endpoint, payload } = await requestJson(
              api,
              "/research-sessions/latest/execution-preflight"
            );
            await appendAuditEvent({
              tool: "workflow_api_get_execution_preflight_from_last_design",
              status: "ok",
              endpoint,
              workflow_id: payload?.workflow_id ?? null,
              ready: payload?.ready ?? null,
              eligible_node_count: Array.isArray(payload?.eligible_nodes) ? payload.eligible_nodes.length : null
            });
            return buildJsonResult({
              endpoint,
              workflow_id: payload?.workflow_id ?? null,
              execution_preflight: payload
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_get_execution_preflight_from_last_design",
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
        name: "workflow_api_review_last_design_for_literature_path",
        description: "Apply the repo-managed literature review update to the latest design draft.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          const requestBody = resolveLiteratureReviewRequest(api);
          try {
            const { endpoint, payload } = await requestJson(api, "/design-drafts/latest/review", {
              method: "POST",
              body: JSON.stringify(requestBody)
            });
            await appendAuditEvent({
              tool: "workflow_api_review_last_design_for_literature_path",
              status: "ok",
              endpoint,
              design_id: payload?.design_id ?? null,
              design_status: payload?.status ?? null,
              workflow_id: payload?.workflow_id ?? null
            });
            return buildJsonResult({
              endpoint,
              request: requestBody,
              design_draft: payload
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_review_last_design_for_literature_path",
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
            const { endpoint, payload } = await requestJson(api, "/research-sessions/latest/runs/from-design", {
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
        name: "workflow_api_dispatch_latest_user_message",
        description: "Preferred first tool for action-oriented research chat. Deterministically route the latest user message to the right session/literature backend action.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          const latestUserMessage = cleanLatestUserIdea(await loadLatestUserIdeaText());
          const routedIntent = detectRoutedUserIntent(latestUserMessage);
          const explicitCommand = parseExplicitCommand(latestUserMessage);
          try {
            if (routedIntent === "start-runner") {
              const goalStatement =
                explicitCommand?.command === "start" && explicitCommand.argument
                  ? explicitCommand.argument
                  : "";
              if (!goalStatement || goalStatement.length < 12) {
                return buildJsonResult({
                  routed_intent: routedIntent,
                  status: "needs-input",
                  detail: "use !start <topic> or start: <topic>"
                });
              }
              const result = await startLiteratureSearchForGoal(api, goalStatement);
              await appendAuditEvent({
                tool: "workflow_api_dispatch_latest_user_message",
                status: "ok",
                routed_intent: routedIntent,
                session_id: result.session?.session_id ?? null,
                queue_id: result.queue?.queue_id ?? null,
                goal_excerpt: result.goalStatement.slice(0, 160)
              });
              return buildJsonResult({
                routed_intent: routedIntent,
                goal_statement: result.goalStatement,
                session: result.session,
                research_problem: result.researchProblem,
                paper_intake_queue: result.queue
              });
            }

            if (routedIntent === "start-literature-search") {
              const goalStatement =
                explicitCommand?.command === "research" && explicitCommand.argument
                  ? explicitCommand.argument
                  : "";
              const result = goalStatement
                ? await startLiteratureSearchForGoal(api, goalStatement)
                : await bootstrapResearchSessionFromLatestUserMessage(api);
              await appendAuditEvent({
                tool: "workflow_api_dispatch_latest_user_message",
                status: "ok",
                routed_intent: routedIntent,
                session_id: result.session?.session_id ?? null,
                queue_id: result.queue?.queue_id ?? null,
                goal_excerpt: result.goalStatement.slice(0, 160)
              });
              return buildJsonResult({
                routed_intent: routedIntent,
                goal_statement: result.goalStatement,
                session: result.session,
                research_problem: result.researchProblem,
                paper_intake_queue: result.queue
              });
            }

            if (routedIntent === "stage-next-paper") {
              const { payload: contextPayload } = await requestJson(api, "/research-sessions/latest/context");
              const queueId =
                typeof contextPayload?.paper_intake_queue?.queue_id === "string"
                  ? contextPayload.paper_intake_queue.queue_id.trim()
                  : "";
              if (!queueId) {
                throw new Error("active research session has no paper intake queue yet");
              }
              let endpoint = "";
              let payload: any = null;
              try {
                const result = await requestJson(
                  api,
                  `/paper-intake-queues/${queueId}/stage-next-intake`,
                  { method: "POST" }
                );
                endpoint = result.endpoint;
                payload = result.payload;
              } catch (error) {
                const detail = extractWorkflowApiErrorDetail(error);
                if (detail.includes("409") || detail.toLowerCase().includes("conflict")) {
                  await appendAuditEvent({
                    tool: "workflow_api_dispatch_latest_user_message",
                    status: "ok",
                    routed_intent: routedIntent,
                    queue_id: queueId,
                    conflict_detail: detail
                  });
                  return buildJsonResult({
                    routed_intent: routedIntent,
                    queue_id: queueId,
                    status: "conflict",
                    detail
                  });
                }
                throw error;
              }
              await appendAuditEvent({
                tool: "workflow_api_dispatch_latest_user_message",
                status: "ok",
                routed_intent: routedIntent,
                endpoint,
                session_id: payload?.session_id ?? contextPayload?.session?.session_id ?? null,
                intake_id: payload?.intake_id ?? null
              });
              return buildJsonResult({
                routed_intent: routedIntent,
                endpoint,
                intake: payload
              });
            }

            if (routedIntent === "refresh-literature-queue") {
              let endpoint = "";
              let payload: any;
              try {
                const result = await requestJson(
                  api,
                  "/research-sessions/latest/skills/external-literature-search",
                  { method: "POST" }
                );
                endpoint = result.endpoint;
                payload = result.payload;
              } catch {
                const result = await requestJson(
                  api,
                  "/research-sessions/latest/skills/literature-harvest",
                  { method: "POST" }
                );
                endpoint = result.endpoint;
                payload = result.payload;
              }
              await appendAuditEvent({
                tool: "workflow_api_dispatch_latest_user_message",
                status: "ok",
                routed_intent: routedIntent,
                endpoint,
                queue_id: payload?.queue_id ?? null,
                candidate_count: Array.isArray(payload?.candidates) ? payload.candidates.length : null
              });
              return buildJsonResult({
                routed_intent: routedIntent,
                endpoint,
                paper_intake_queue: payload
              });
            }

            if (routedIntent === "add-manual-paper") {
              const explicitCommand = parseExplicitCommand(latestUserMessage);
              const argument =
                explicitCommand?.command === "add-paper" ? explicitCommand.argument.trim() : "";
              if (!argument) {
                return buildJsonResult({
                  routed_intent: routedIntent,
                  status: "needs-input",
                  detail: "use !add-paper <url|title> or add-paper: <url|title>"
                });
              }
              const urlMatch = argument.match(/https?:\/\/\S+/i);
              const officialPage = urlMatch ? urlMatch[0] : null;
              const pdfUrl = officialPage && /\.pdf(?:$|\?)/i.test(officialPage) ? officialPage : null;
              const { endpoint, payload } = await requestJson(
                api,
                "/research-sessions/latest/paper-intake-queue/manual-paper",
                {
                  method: "POST",
                  body: JSON.stringify({
                    title: officialPage ? argument.replace(officialPage, "").trim() || officialPage : argument,
                    official_page: pdfUrl ? null : officialPage,
                    pdf_url: pdfUrl,
                    notes: ["manually queued from OpenClaw command"],
                    tags: ["manual"],
                    submitted_by: "openclaw-operator"
                  })
                }
              );
              await appendAuditEvent({
                tool: "workflow_api_dispatch_latest_user_message",
                status: "ok",
                routed_intent: routedIntent,
                endpoint,
                queue_id: payload?.queue_id ?? null,
                candidate_count: Array.isArray(payload?.candidates) ? payload.candidates.length : null
              });
              return buildJsonResult({
                routed_intent: routedIntent,
                endpoint,
                paper_intake_queue: payload
              });
            }

            if (routedIntent === "summarize-session") {
              const { endpoint, payload } = await requestJson(api, "/research-sessions/latest/context");
              await appendAuditEvent({
                tool: "workflow_api_dispatch_latest_user_message",
                status: "ok",
                routed_intent: routedIntent,
                endpoint,
                session_id: payload?.session?.session_id ?? null
              });
              return buildJsonResult({
                routed_intent: routedIntent,
                endpoint,
                session_context: payload
              });
            }

            if (routedIntent === "runner-status") {
              const { endpoint, payload } = await requestJson(api, "/research-sessions/latest/context");
              let autoresearchSummary: any = null;
              try {
                const summaryResult = await requestJson(api, "/research-sessions/latest/autoresearch-summary");
                autoresearchSummary = summaryResult.payload;
              } catch (error) {
                if (!isMissingCampaignError(error)) {
                  throw error;
                }
              }
              await appendAuditEvent({
                tool: "workflow_api_dispatch_latest_user_message",
                status: "ok",
                routed_intent: routedIntent,
                endpoint,
                session_id: payload?.session?.session_id ?? null
              });
              return buildJsonResult({
                routed_intent: routedIntent,
                endpoint,
                session_context: payload,
                autoresearch_summary: autoresearchSummary
              });
            }

            if (routedIntent === "create-interpretation") {
              const { endpoint, payload } = await requestJson(
                api,
                "/research-sessions/latest/transitions/create-interpretation",
                { method: "POST" }
              );
              await appendAuditEvent({
                tool: "workflow_api_dispatch_latest_user_message",
                status: "ok",
                routed_intent: routedIntent,
                endpoint,
                interpretation_id: payload?.interpretation_id ?? null
              });
              return buildJsonResult({ routed_intent: routedIntent, endpoint, interpretation: payload });
            }

            if (routedIntent === "create-design") {
              const { endpoint, payload } = await requestJson(
                api,
                "/research-sessions/latest/skills/design",
                { method: "POST" }
              );
              await appendAuditEvent({
                tool: "workflow_api_dispatch_latest_user_message",
                status: "ok",
                routed_intent: routedIntent,
                endpoint,
                design_id: payload?.design_id ?? null
              });
              return buildJsonResult({ routed_intent: routedIntent, endpoint, design_draft: payload });
            }

            if (routedIntent === "execution-preflight") {
              const { endpoint, payload } = await requestJson(api, "/research-sessions/latest/execution-preflight");
              await appendAuditEvent({
                tool: "workflow_api_dispatch_latest_user_message",
                status: "ok",
                routed_intent: routedIntent,
                endpoint,
                workflow_id: payload?.workflow_id ?? null
              });
              return buildJsonResult({ routed_intent: routedIntent, endpoint, execution_preflight: payload });
            }

            if (routedIntent === "create-run") {
              const { endpoint, payload } = await requestJson(
                api,
                "/research-sessions/latest/runs/from-design",
                { method: "POST" }
              );
              await appendAuditEvent({
                tool: "workflow_api_dispatch_latest_user_message",
                status: "ok",
                routed_intent: routedIntent,
                endpoint,
                run_id: payload?.run_id ?? null
              });
              return buildJsonResult({ routed_intent: routedIntent, endpoint, run: payload });
            }

            if (routedIntent === "start-autoresearch") {
              const { endpoint, payload } = await requestJson(
                api,
                "/research-sessions/latest/transitions/start-autoresearch-campaign",
                { method: "POST" }
              );
              await appendAuditEvent({
                tool: "workflow_api_dispatch_latest_user_message",
                status: "ok",
                routed_intent: routedIntent,
                endpoint,
                campaign_id: payload?.campaign_id ?? null
              });
              return buildJsonResult({ routed_intent: routedIntent, endpoint, campaign: payload });
            }

            if (routedIntent === "draft-methodologies") {
              const { endpoint, payload } = await requestJson(
                api,
                "/research-sessions/latest/transitions/draft-methodologies",
                { method: "POST" }
              );
              await appendAuditEvent({
                tool: "workflow_api_dispatch_latest_user_message",
                status: "ok",
                routed_intent: routedIntent,
                endpoint
              });
              return buildJsonResult({ routed_intent: routedIntent, endpoint, methodology_drafts: payload });
            }

            if (routedIntent === "draft-notebook") {
              const { endpoint, payload } = await requestJson(
                api,
                "/research-sessions/latest/transitions/draft-autoresearch-notebook",
                { method: "POST" }
              );
              await appendAuditEvent({
                tool: "workflow_api_dispatch_latest_user_message",
                status: "ok",
                routed_intent: routedIntent,
                endpoint,
                storage_uri: payload?.storage_uri ?? null
              });
              return buildJsonResult({ routed_intent: routedIntent, endpoint, notebook_draft: payload });
            }

            if (routedIntent === "refine-notebook") {
              const { endpoint, payload } = await requestJson(
                api,
                "/research-sessions/latest/transitions/refine-autoresearch-notebook",
                { method: "POST" }
              );
              await appendAuditEvent({
                tool: "workflow_api_dispatch_latest_user_message",
                status: "ok",
                routed_intent: routedIntent,
                endpoint,
                storage_uri: payload?.storage_uri ?? null
              });
              return buildJsonResult({ routed_intent: routedIntent, endpoint, notebook_refinement: payload });
            }

            if (routedIntent === "launch-iteration") {
              const { endpoint, payload } = await requestJson(
                api,
                "/research-sessions/latest/transitions/launch-autoresearch-iteration",
                { method: "POST" }
              );
              await appendAuditEvent({
                tool: "workflow_api_dispatch_latest_user_message",
                status: "ok",
                routed_intent: routedIntent,
                endpoint
              });
              return buildJsonResult({ routed_intent: routedIntent, endpoint, iteration_launch: payload });
            }

            if (routedIntent === "decide-latest") {
              const { endpoint, payload } = await requestJson(
                api,
                "/research-sessions/latest/transitions/decide-autoresearch-latest",
                { method: "POST" }
              );
              await appendAuditEvent({
                tool: "workflow_api_dispatch_latest_user_message",
                status: "ok",
                routed_intent: routedIntent,
                endpoint
              });
              return buildJsonResult({ routed_intent: routedIntent, endpoint, autoresearch_decision: payload });
            }

            if (routedIntent === "autoresearch-summary") {
              const { endpoint, payload } = await requestJson(api, "/research-sessions/latest/autoresearch-summary");
              await appendAuditEvent({
                tool: "workflow_api_dispatch_latest_user_message",
                status: "ok",
                routed_intent: routedIntent,
                endpoint
              });
              return buildJsonResult({ routed_intent: routedIntent, endpoint, autoresearch_summary: payload });
            }

            if (routedIntent === "model-comparison") {
              const { endpoint, payload } = await requestJson(api, "/research-sessions/latest/autoresearch-model-comparison");
              await appendAuditEvent({
                tool: "workflow_api_dispatch_latest_user_message",
                status: "ok",
                routed_intent: routedIntent,
                endpoint
              });
              return buildJsonResult({ routed_intent: routedIntent, endpoint, model_comparison: payload });
            }

            if (routedIntent === "runner-compare") {
              try {
                const { endpoint, payload } = await requestJson(api, "/research-sessions/latest/autoresearch-model-comparison");
                await appendAuditEvent({
                  tool: "workflow_api_dispatch_latest_user_message",
                  status: "ok",
                  routed_intent: routedIntent,
                  endpoint
                });
                return buildJsonResult({ routed_intent: routedIntent, endpoint, model_comparison: payload });
              } catch (error) {
                if (!isMissingCampaignError(error)) {
                  throw error;
                }
                await appendAuditEvent({
                  tool: "workflow_api_dispatch_latest_user_message",
                  status: "ok",
                  routed_intent: routedIntent,
                  detail: "no autoresearch campaign yet"
                });
                return buildJsonResult({
                  routed_intent: routedIntent,
                  status: "no-campaign",
                  detail: "No autoresearch campaign yet. Use !next after !run to start one."
                });
              }
            }

            if (routedIntent === "next-runner-step") {
              let campaignExists = true;
              try {
                await requestJson(api, "/research-sessions/latest/autoresearch-summary");
              } catch (error) {
                if (isMissingCampaignError(error)) {
                  campaignExists = false;
                } else {
                  throw error;
                }
              }

              if (!campaignExists) {
                const draftResult = await requestJson(
                  api,
                  "/research-sessions/latest/transitions/draft-methodologies",
                  { method: "POST" }
                );
                const launchResult = await requestJson(
                  api,
                  "/research-sessions/latest/transitions/launch-autoresearch-batch",
                  { method: "POST" }
                );
                await appendAuditEvent({
                  tool: "workflow_api_dispatch_latest_user_message",
                  status: "ok",
                  routed_intent: routedIntent,
                  endpoint: launchResult.endpoint
                });
                return buildJsonResult({
                  routed_intent: routedIntent,
                  draft_endpoint: draftResult.endpoint,
                  launch_endpoint: launchResult.endpoint,
                  methodology_drafts: draftResult.payload,
                  launch_batch: launchResult.payload
                });
              }

              const decideResult = await requestJson(
                api,
                "/research-sessions/latest/transitions/decide-autoresearch-batch",
                { method: "POST" }
              );
              const launchResult = await requestJson(
                api,
                "/research-sessions/latest/transitions/launch-autoresearch-batch",
                { method: "POST" }
              );
              await appendAuditEvent({
                tool: "workflow_api_dispatch_latest_user_message",
                status: "ok",
                routed_intent: routedIntent,
                endpoint: launchResult.endpoint
              });
              return buildJsonResult({
                routed_intent: routedIntent,
                decide_endpoint: decideResult.endpoint,
                launch_endpoint: launchResult.endpoint,
                batch_decision: decideResult.payload,
                launch_batch: launchResult.payload
              });
            }

            if (routedIntent === "capture-note") {
              const noteText =
                explicitCommand?.command === "note" && explicitCommand.argument
                  ? explicitCommand.argument
                  : latestUserMessage;
              if (noteText.length < 12) {
                throw new Error("latest user message is too short to store as a research-session note");
              }
              const { endpoint, payload } = await requestJson(api, "/research-sessions/latest/memory", {
                method: "POST",
                body: JSON.stringify({ working_note: noteText })
              });
              await appendAuditEvent({
                tool: "workflow_api_dispatch_latest_user_message",
                status: "ok",
                routed_intent: routedIntent,
                endpoint,
                session_id: payload?.session_id ?? null,
                note_excerpt: noteText.slice(0, 160)
              });
              return buildJsonResult({
                routed_intent: routedIntent,
                endpoint,
                note_saved: noteText,
                session: payload
              });
            }

            if (routedIntent === "latest-operation") {
              const { endpoint, payload } = await requestJson(api, "/operations/latest");
              await appendAuditEvent({
                tool: "workflow_api_dispatch_latest_user_message",
                status: "ok",
                routed_intent: routedIntent,
                endpoint,
                operation_id: payload?.operation_id ?? null
              });
              return buildJsonResult({
                routed_intent: routedIntent,
                endpoint,
                operation: payload
              });
            }

            if (routedIntent === "help") {
              await appendAuditEvent({
                tool: "workflow_api_dispatch_latest_user_message",
                status: "ok",
                routed_intent: routedIntent,
                latest_user_message: latestUserMessage.slice(0, 200)
              });
              return buildJsonResult({
                routed_intent: routedIntent,
                latest_user_message: latestUserMessage,
                help: commandHelpText()
              });
            }

            await appendAuditEvent({
                tool: "workflow_api_dispatch_latest_user_message",
                status: "unsupported",
              routed_intent: routedIntent,
              latest_user_message: latestUserMessage.slice(0, 200)
            });
            return buildJsonResult({
              routed_intent: routedIntent,
              latest_user_message: latestUserMessage,
              guidance:
                "No deterministic research-loop action matched the latest user message. Use conversational reply or a narrower read tool."
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_dispatch_latest_user_message",
              status: "error",
              routed_intent: routedIntent,
              error: error instanceof Error ? error.message : String(error),
              error_detail: extractWorkflowApiErrorDetail(error)
            });
            throw error;
          }
        }
      },
      { optional: true }
    );

    api.registerTool(
      {
        name: "workflow_api_bootstrap_research_session_from_latest_user_message",
        description: "Create a research session from the latest user chat idea, stage its research problem, and start literature harvest without relying on free-text tool arguments.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          try {
            const {
              goalStatement,
              session,
              researchProblem,
              queue,
              bootstrapEndpoint,
              sessionEndpoint,
              problemEndpoint,
              queueEndpoint,
              bootstrapAction
            } = await bootstrapResearchSessionFromLatestUserMessage(api);
            const sessionId =
              typeof session?.session_id === "string" ? session.session_id.trim() : "";

            await appendAuditEvent({
              tool: "workflow_api_bootstrap_research_session_from_latest_user_message",
              status: "ok",
              session_id: sessionId,
              bootstrap_endpoint: bootstrapEndpoint,
              bootstrap_action: bootstrapAction,
              session_endpoint: sessionEndpoint,
              problem_endpoint: problemEndpoint,
              queue_endpoint: queueEndpoint,
              queue_id: queue?.queue_id ?? null,
              problem_id: researchProblem?.problem_id ?? null,
              goal_excerpt: goalStatement.slice(0, 160)
            });
            return buildJsonResult({
              goal_statement: goalStatement,
              session,
              research_problem: researchProblem,
              paper_intake_queue: queue
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_bootstrap_research_session_from_latest_user_message",
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
        name: "workflow_api_start_literature_search_from_latest_user_message",
        description: "Preferred first action for a new topic. Start or resume the research session from the latest user message, stage the research problem, and begin literature search immediately.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          try {
            const {
              goalStatement,
              session,
              researchProblem,
              queue,
              bootstrapEndpoint,
              sessionEndpoint,
              problemEndpoint,
              queueEndpoint,
              bootstrapAction
            } = await bootstrapResearchSessionFromLatestUserMessage(api);
            const sessionId =
              typeof session?.session_id === "string" ? session.session_id.trim() : "";

            await appendAuditEvent({
              tool: "workflow_api_start_literature_search_from_latest_user_message",
              status: "ok",
              session_id: sessionId,
              bootstrap_endpoint: bootstrapEndpoint,
              bootstrap_action: bootstrapAction,
              session_endpoint: sessionEndpoint,
              problem_endpoint: problemEndpoint,
              queue_endpoint: queueEndpoint,
              queue_id: queue?.queue_id ?? null,
              problem_id: researchProblem?.problem_id ?? null,
              goal_excerpt: goalStatement.slice(0, 160)
            });
            return buildJsonResult({
              goal_statement: goalStatement,
              session,
              research_problem: researchProblem,
              paper_intake_queue: queue
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_start_literature_search_from_latest_user_message",
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
        name: "workflow_api_capture_latest_user_message_as_session_note",
        description: "Save the latest user message as a working note on the active research session.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          try {
            const noteText = cleanLatestUserIdea(await loadLatestUserIdeaText());
            if (noteText.length < 12) {
              throw new Error("latest user message is too short to store as a research-session note");
            }
            const { endpoint, payload } = await requestJson(api, "/research-sessions/latest/memory", {
              method: "POST",
              body: JSON.stringify({ working_note: noteText })
            });
            await appendAuditEvent({
              tool: "workflow_api_capture_latest_user_message_as_session_note",
              status: "ok",
              endpoint,
              session_id: payload?.session_id ?? null,
              note_excerpt: noteText.slice(0, 160)
            });
            return buildJsonResult({
              endpoint,
              note_saved: noteText,
              session: payload
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_capture_latest_user_message_as_session_note",
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
        name: "workflow_api_get_research_session_bootstrap_status",
        description: "Check whether the literature workspace already has an active session, a staged research problem, or needs manual session bootstrap.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          try {
            const { endpoint, payload } = await requestJson(api, "/research-sessions/bootstrap-status");
            await appendAuditEvent({
              tool: "workflow_api_get_research_session_bootstrap_status",
              status: "ok",
              endpoint,
              recommended_next_action: payload?.recommended_next_action ?? null,
              has_active_session: payload?.active_session ? true : false,
              has_staged_research_problem: payload?.staged_research_problem ? true : false
            });
            return buildJsonResult({
              endpoint,
              bootstrap_status: payload
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_get_research_session_bootstrap_status",
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
        name: "workflow_api_create_research_session_from_latest_research_problem",
        description: "Create a persistent research session from the latest staged research problem.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          try {
            const { endpoint, payload } = await requestJson(api, "/research-sessions/from-latest-research-problem", {
              method: "POST"
            });
            await appendAuditEvent({
              tool: "workflow_api_create_research_session_from_latest_research_problem",
              status: "ok",
              endpoint,
              session_id: payload?.session_id ?? null,
              title: payload?.title ?? null
            });
            return buildJsonResult({
              endpoint,
              session: payload
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_create_research_session_from_latest_research_problem",
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
        name: "workflow_api_get_latest_research_session",
        description: "Fetch the active research session record for the current literature workspace.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          try {
            const { endpoint, payload } = await requestJson(api, "/research-sessions/latest");
            await appendAuditEvent({
              tool: "workflow_api_get_latest_research_session",
              status: "ok",
              endpoint,
              session_id: payload?.session_id ?? null,
              title: payload?.title ?? null
            });
            return buildJsonResult({
              endpoint,
              session: payload
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_get_latest_research_session",
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
        name: "workflow_api_get_latest_research_session_context",
        description: "Fetch the latest research session context, including the current problem, queue, documents, and downstream stage records.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          try {
            const { endpoint, payload } = await requestJson(api, "/research-sessions/latest/context");
            await appendAuditEvent({
              tool: "workflow_api_get_latest_research_session_context",
              status: "ok",
              endpoint,
              session_id: payload?.session?.session_id ?? null,
              latest_problem_id: payload?.session?.latest_problem_id ?? null,
              latest_queue_id: payload?.session?.latest_queue_id ?? null
            });
            return buildJsonResult({
              endpoint,
              session_context: payload
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_get_latest_research_session_context",
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
        name: "workflow_api_stage_research_problem_from_latest_session",
        description: "Apply the research-problem skill to the active research session.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          try {
            const ensured = await ensureLatestResearchSession(api);
            if (ensured.researchProblem) {
              await appendAuditEvent({
                tool: "workflow_api_stage_research_problem_from_latest_session",
                status: "ok",
                endpoint: ensured.bootstrapEndpoint,
                session_id: ensured.session?.session_id ?? null,
                problem_id: ensured.researchProblem?.problem_id ?? null,
                bootstrap_recovered: ensured.createdOrRecovered
              });
              return buildJsonResult({
                endpoint: ensured.bootstrapEndpoint,
                bootstrap_status: ensured.bootstrapStatus,
                bootstrap_recovered: ensured.createdOrRecovered,
                research_problem: ensured.researchProblem
              });
            }
            const { endpoint, payload } = await requestJson(
              api,
              "/research-sessions/latest/skills/research-problem",
              {
                method: "POST"
              }
            );
            await appendAuditEvent({
              tool: "workflow_api_stage_research_problem_from_latest_session",
              status: "ok",
              endpoint,
              problem_id: payload?.problem_id ?? null,
              session_id: payload?.session_id ?? null,
              bootstrap_recovered: ensured.createdOrRecovered
            });
            return buildJsonResult({
              endpoint,
              bootstrap_status: ensured.bootstrapStatus,
              bootstrap_recovered: ensured.createdOrRecovered,
              research_problem: payload
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_stage_research_problem_from_latest_session",
              status: "error",
              error: error instanceof Error ? error.message : String(error),
              error_detail: extractWorkflowApiErrorDetail(error)
            });
            throw error;
          }
        }
      },
      { optional: true }
    );

    api.registerTool(
      {
        name: "workflow_api_create_paper_intake_queue_from_latest_session",
        description: "Apply the literature-harvest skill to the active research session.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          try {
            const ensured = await ensureLatestResearchSession(api);
            let endpoint: string;
            let payload: any;
            try {
              const createdQueue = await requestJson(
                api,
                "/research-sessions/latest/skills/literature-harvest",
                {
                  method: "POST"
                }
              );
              endpoint = createdQueue.endpoint;
              payload = createdQueue.payload;
            } catch (error) {
              if (!isWorkflowApiTimeout(error)) {
                throw error;
              }
              const recoveredQueue = await recoverLatestQueueAfterTimeout(
                api,
                "/research-sessions/latest/paper-intake-queue"
              );
              if (recoveredQueue) {
                endpoint = recoveredQueue.endpoint;
                payload = recoveredQueue.payload;
              } else {
                throw error;
              }
            }
            await appendAuditEvent({
              tool: "workflow_api_create_paper_intake_queue_from_latest_session",
              status: "ok",
              endpoint,
              queue_id: payload?.queue_id ?? null,
              session_id: payload?.session_id ?? null,
              candidate_count: Array.isArray(payload?.candidates) ? payload.candidates.length : null,
              bootstrap_recovered: ensured.createdOrRecovered,
              slow_harvest_recovered: endpoint.includes("/paper-intake-queue")
            });
            return buildJsonResult({
              endpoint,
              bootstrap_status: ensured.bootstrapStatus,
              bootstrap_recovered: ensured.createdOrRecovered,
              slow_harvest_recovered: endpoint.includes("/paper-intake-queue"),
              queue: payload
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_create_paper_intake_queue_from_latest_session",
              status: "error",
              error: error instanceof Error ? error.message : String(error),
              error_detail: extractWorkflowApiErrorDetail(error)
            });
            throw error;
          }
        }
      },
      { optional: true }
    );

    api.registerTool(
      {
        name: "workflow_api_stage_next_intake_from_latest_session",
        description: "Apply the paper-intake skill to the active research session.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          try {
            const ensured = await ensureLatestResearchSession(api);
            const { endpoint, payload } = await requestJson(
              api,
              "/research-sessions/latest/skills/paper-intake",
              {
                method: "POST"
              }
            );
            await appendAuditEvent({
              tool: "workflow_api_stage_next_intake_from_latest_session",
              status: "ok",
              endpoint,
              intake_id: payload?.intake_id ?? null,
              session_id: payload?.session_id ?? null,
              bootstrap_recovered: ensured.createdOrRecovered
            });
            return buildJsonResult({
              endpoint,
              bootstrap_status: ensured.bootstrapStatus,
              bootstrap_recovered: ensured.createdOrRecovered,
              intake: payload
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_stage_next_intake_from_latest_session",
              status: "error",
              error: error instanceof Error ? error.message : String(error),
              error_detail: extractWorkflowApiErrorDetail(error)
            });
            throw error;
          }
        }
      },
      { optional: true }
    );

    api.registerTool(
      {
        name: "workflow_api_get_latest_operation",
        description: "Fetch the latest recorded workflow-api operation for the literature/session path.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          try {
            const { endpoint, payload } = await requestJson(api, "/operations/latest");
            await appendAuditEvent({
              tool: "workflow_api_get_latest_operation",
              status: "ok",
              endpoint,
              operation_id: payload?.operation_id ?? null,
              operation_type: payload?.operation_type ?? null
            });
            return buildJsonResult({
              endpoint,
              operation: payload
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_get_latest_operation",
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
        name: "workflow_api_create_paper_intake_queue_from_latest_research_problem",
        description: "Create a controlled-corpus paper intake queue from the latest staged research problem.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          try {
            const { payload: problem } = await requestJson(api, "/research-problems/latest");
            const requestBody = {
              problem_statement: String(problem?.problem_statement || "").trim(),
              max_candidate_papers:
                typeof problem?.max_candidate_papers === "number"
                  ? Math.max(1, Math.min(25, Math.floor(problem.max_candidate_papers)))
                  : 3,
              priorities: Array.isArray(problem?.priorities)
                ? problem.priorities.filter((item: unknown) => typeof item === "string" && item.trim())
                : [],
              submitted_by: typeof problem?.submitted_by === "string" && problem.submitted_by.trim()
                ? problem.submitted_by.trim()
                : "openclaw-operator"
            };
            if (!requestBody.problem_statement) {
              throw new Error("latest research problem is missing problem_statement");
            }
            let endpoint: string;
            let payload: any;
            try {
              const createdQueue = await requestJson(api, "/paper-intake-queues/from-research-problem", {
                method: "POST",
                body: JSON.stringify(requestBody)
              });
              endpoint = createdQueue.endpoint;
              payload = createdQueue.payload;
            } catch (error) {
              if (!isWorkflowApiTimeout(error)) {
                throw error;
              }
              const recoveredQueue = await recoverLatestQueueAfterTimeout(
                api,
                "/paper-intake-queues/latest"
              );
              if (recoveredQueue) {
                endpoint = recoveredQueue.endpoint;
                payload = recoveredQueue.payload;
              } else {
                throw error;
              }
            }
            await appendAuditEvent({
              tool: "workflow_api_create_paper_intake_queue_from_latest_research_problem",
              status: "ok",
              endpoint,
              queue_id: payload?.queue_id ?? null,
              candidate_count: Array.isArray(payload?.candidates) ? payload.candidates.length : null,
              slow_harvest_recovered: endpoint.endsWith("/paper-intake-queues/latest")
            });
            return buildJsonResult({
              endpoint,
              slow_harvest_recovered: endpoint.endsWith("/paper-intake-queues/latest"),
              queue: payload
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_create_paper_intake_queue_from_latest_research_problem",
              status: "error",
              error: error instanceof Error ? error.message : String(error),
              error_detail: extractWorkflowApiErrorDetail(error)
            });
            throw error;
          }
        }
      },
      { optional: true }
    );

    api.registerTool(
      {
        name: "workflow_api_get_latest_paper_intake_queue",
        description: "Fetch the most recent controlled-corpus paper intake queue.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          try {
            const { endpoint, payload } = await requestJson(api, "/paper-intake-queues/latest");
            await appendAuditEvent({
              tool: "workflow_api_get_latest_paper_intake_queue",
              status: "ok",
              endpoint,
              queue_id: payload?.queue_id ?? null,
              queue_status: payload?.status ?? null,
              candidate_count: Array.isArray(payload?.candidates) ? payload.candidates.length : null
            });
            return buildJsonResult({
              endpoint,
              queue: payload
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_get_latest_paper_intake_queue",
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
        name: "workflow_api_stage_next_intake_from_latest_queue",
        description: "Stage the next pending paper from the latest paper intake queue into a real intake record.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          try {
            const { payload: queue } = await requestJson(api, "/paper-intake-queues/latest");
            const queueId = typeof queue?.queue_id === "string" ? queue.queue_id.trim() : "";
            if (!queueId) {
              throw new Error("latest paper intake queue did not include queue_id");
            }
            const { endpoint, payload } = await requestJson(
              api,
              `/paper-intake-queues/${encodeURIComponent(queueId)}/stage-next-intake`,
              {
                method: "POST"
              }
            );
            await appendAuditEvent({
              tool: "workflow_api_stage_next_intake_from_latest_queue",
              status: "ok",
              endpoint,
              queue_id: queueId,
              intake_id: payload?.intake_id ?? null
            });
            return buildJsonResult({
              endpoint,
              queue_id: queueId,
              intake: payload
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_stage_next_intake_from_latest_queue",
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
        name: "workflow_api_get_latest_source_document",
        description: "Fetch the most recent stored source document record from the controlled corpus.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          try {
            const { endpoint, payload } = await requestJson(api, "/source-documents/latest");
            await appendAuditEvent({
              tool: "workflow_api_get_latest_source_document",
              status: "ok",
              endpoint,
              document_id: payload?.document_id ?? null,
              source_url: payload?.source_url ?? null,
              document_status: payload?.status ?? null
            });
            return buildJsonResult({
              endpoint,
              source_document: payload
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_get_latest_source_document",
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

    api.registerTool(
      {
        name: "workflow_api_run_research_problem_pipeline",
        description: "Turn a bounded natural-language research problem into candidate-paper selection and a backend paper-to-artifact run.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {
            problem_statement: {
              type: "string",
              minLength: 12,
              description: "Natural-language research problem statement."
            },
            max_candidate_papers: {
              type: "integer",
              minimum: 1,
              maximum: 5,
              default: 3,
              description: "Maximum approved candidate papers to consider before selecting the top candidate."
            },
            wait_for_terminal_state: {
              type: "boolean",
              default: true,
              description: "When true, wait for the backend run to reach a terminal state before returning."
            }
          },
          required: ["problem_statement"]
        },
        async execute(args: any) {
          const requestBody = {
            problem_statement: String(args?.problem_statement || "").trim(),
            max_candidate_papers:
              typeof args?.max_candidate_papers === "number"
                ? Math.max(1, Math.min(5, Math.floor(args.max_candidate_papers)))
                : 3,
            wait_for_terminal_state:
              typeof args?.wait_for_terminal_state === "boolean"
                ? args.wait_for_terminal_state
                : true
          };
          if (!requestBody.problem_statement) {
            throw new Error("problem_statement is required");
          }
          try {
            const { endpoint, payload } = await requestJson(api, "/paper-pipelines/from-research-problem", {
              method: "POST",
              body: JSON.stringify(requestBody)
            });
            await appendAuditEvent({
              tool: "workflow_api_run_research_problem_pipeline",
              status: "ok",
              endpoint,
              chosen_paper_id: payload?.chosen_paper_id ?? null,
              next_action: payload?.next_action ?? null,
              run_id: payload?.pipeline?.run?.run_id ?? null,
              run_status: payload?.pipeline?.report_state?.run_status ?? null
            });
            return buildJsonResult({
              endpoint,
              request: requestBody,
              result: payload
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_run_research_problem_pipeline",
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
        name: "workflow_api_run_latest_research_problem_pipeline",
        description:
          "Run the bounded paper-to-artifact pipeline for the latest research problem already staged in workflow-api.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {}
        },
        async execute() {
          try {
            const { endpoint, payload } = await requestJson(
              api,
              "/paper-pipelines/from-latest-research-problem",
              {
                method: "POST",
                body: JSON.stringify({})
              }
            );
            await appendAuditEvent({
              tool: "workflow_api_run_latest_research_problem_pipeline",
              status: "ok",
              endpoint,
              chosen_paper_id: payload?.chosen_paper_id ?? null,
              next_action: payload?.next_action ?? null,
              run_id: payload?.pipeline?.run?.run_id ?? null,
              run_status: payload?.pipeline?.report_state?.run_status ?? null
            });
            return buildJsonResult({
              endpoint,
              result: payload
            });
          } catch (error) {
            await appendAuditEvent({
              tool: "workflow_api_run_latest_research_problem_pipeline",
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
            workflow_id: buildWorkflowIdProperty(knownWorkflowIds)
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

    for (const workflowId of knownWorkflowIds) {
      const toolName = buildWorkflowLookupToolName(workflowId);
      api.registerTool(
        {
          name: toolName,
          description: `Fetch the approved workflow family for exact workflow_id ${workflowId}. No arguments required.`,
          parameters: {
            type: "object",
            additionalProperties: false,
            properties: {}
          },
          async execute() {
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
              await appendAuditEvent({
                tool: toolName,
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
                tool: toolName,
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
  }
};

export default plugin;
