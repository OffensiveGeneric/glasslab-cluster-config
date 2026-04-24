# Autoresearch Orchestration Refactoring — Summary for GitHub

## Problem Statement

The autoresearch loop (`session → campaign → draft → launch → decide`) is currently **tightly coupled to chat/command interfaces**. This creates brittle dependencies that limit:
- Batch execution
- CI/CD integration  
- Parallel experimentation
- Orchestration flexibility

## Root Cause

The infrastructure assumes chat-first interaction:
```
chat message → command router → workflow-api → session context → autoresearch campaign
```

Key issues:
- Campaign creation requires `session_id`
- "Latest" assumptions break with parallel work
- No standalone orchestration endpoints
- 10 hardcoded chat commands with no batch support

## Proposed Solution

### 1. Decouple Sessions from Chat Semantics

```python
# New: Campaigns can be standalone
class AutoresearchCampaignCreateRequest(BaseModel):
    name: str  # NEW: Discoverable label
    description: str | None = None
    session_id: str | None = None  # Optional
    seed_methodology_draft_id: str
```

### 2. Add Orchestration Endpoints

```bash
# Direct campaign launch (new)
POST /autoresearch/campaigns/{campaign_id}/launch-next
POST /autoresearch/campaigns/{campaign_id}/launch-batch

# Batch launch with explicit parameters
POST /autoresearch/campaigns/{campaign_id}/launch-batch
{
  "methodology_draft_ids": ["draft-1", "draft-2", "draft-3"],
  "run_priority": "user|autonomous"
}

# Explicit decision on specific iteration
POST /autoresearch/campaigns/{campaign_id}/decide-iteration/{iteration_id}
```

### 3. Update Schema to Support Parallel Work

```python
# Campaigns list instead of "latest"
class ResearchSessionRecord(BaseModel):
    campaign_ids: list[str] = Field(default_factory=list)
    
class AutoresearchCampaignRecord(BaseModel):
    status: Literal["drafting", "running", "completed", "paused"]
    iteration_ids: list[str] = Field(default_factory=list)  # Not just latest
    decision_ids: list[str] = Field(default_factory=list)
```

## Benefits

1. **Chat-agnostic orchestration**: Python SDK, CI/CD, batch jobs
2. **Explicit state**: No "latest" assumptions
3. **Discoverable campaigns**: Named campaigns
4. **Flexible run control**: Per-batch priority and resource override
5. **Clean separation**: Session vs Campaign concerns

## Example Usage

### Chat (Still Supported)
```bash
!new Train contrastive learner on CIFAR-100
!add dataset: cifar100-unseen-classes
!plan
!run
!next
!decide keep
```

### Programmatic (New)
```python
campaign = client.create_autoresearch_campaign(
    name="cifar100-contrastive-ablation",
    seed_methodology_draft_id="seed-abc123"
)

campaign.launch_batch(
    methodology_draft_ids=["draft-1", "draft-2", "draft-3"],
    run_priority="autonomous"
)
```

### CI/CD (New)
```yaml
- name: Launch ablation study
  run: |
    glasslab autoresearch launch \
      --name "test-contrastive-v0" \
      --seed-draft draft-abc123 \
      --batch draft-1 draft-2 draft-3
```

## Migration Plan

| Phase | Action | Breaking? |
|-------|--------|-----------|
| 1 | Add `name`, `description` fields | No |
| 2 | Add new orchestration endpoints | No |
| 3 | Deprecate chat-only endpoints | Yes (docs only) |
| 4 | Update command router | No |
| 5 | Remove legacy endpoints | Yes (v3) |

## Documentation

Full technical specification:  
[docs/glasslab-v2/autoresearch-orchestration-plan.md](docs/glasslab-v2/autoresearch-orchestration-plan.md)

## Questions for Decision

1. Should sessions remain primary, or introduce "projects"?
2. Keep `!next` / `!decide` or replace with `!campaign` commands?
3. Support parallel execution groups?
4. Separate permissions for autonomous system?
5. Add `campaign_status` to runs?

---

**Status**: Proposed — Not Implemented  
**Last Updated**: 2026-04-24
