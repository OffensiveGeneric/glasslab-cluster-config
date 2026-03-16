const DEFAULT_TIMEOUT_SECONDS = 10;

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

const plugin = {
  id: "workflow-api-tool",
  name: "Workflow API Tool",
  description: "Read-only workflow-api helper for Glasslab v2 operator validation.",
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
          const baseUrl = resolveBaseUrl(api);
          const timeoutSeconds = resolveTimeoutSeconds(api);
          const endpoint = new URL("/workflow-families", baseUrl).toString();
          const response = await fetch(endpoint, {
            headers: {
              accept: "application/json"
            },
            signal: AbortSignal.timeout(timeoutSeconds * 1000)
          });

          if (!response.ok) {
            const detail = (await response.text()).slice(0, 2000);
            throw new Error(
              `workflow-api request failed (${response.status}): ${detail || response.statusText}`
            );
          }

          const payload = await response.json();

          return {
            content: [
              {
                type: "text",
                text: JSON.stringify(
                  {
                    endpoint,
                    workflow_families: payload
                  },
                  null,
                  2
                )
              }
            ]
          };
        }
      },
      { optional: true }
    );
  }
};

export default plugin;
