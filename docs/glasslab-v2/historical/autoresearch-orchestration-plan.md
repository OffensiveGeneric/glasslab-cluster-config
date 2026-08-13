# Glasslab Autoresearch Orchestration Refactoring Plan

**Date**: 2026-04-24  
**Status**: Proposed — Not Implemented  
**Author**: Glasslab Team  

---

## Executive Summary

The autoresearch loop (`session → campaign → draft → launch → decide`) is currently **tightly coupled to chat/command interfaces** through the command router and workflow-api. This creates brittle dependencies that limit scalability, batch execution, and orchestration.

This document proposes a refactoring to decouple sessions from chat semantics while maintaining backward compatibility.

---

## Current Problem

### Chat-Centric Architecture

The current flow assumes chat-first interaction:

```
chat message → research-command-router → workflow-api → session context → autoresearch campaign
```

This couples:
- Chat surface (`!next`, `!decide`) → control plane
- Session state → campaign state  
- Turn-based interaction → orchestration

### Evidence of Coupling

1. **Command Router** has 10 hardcoded commands with no orchestration entry points
2. **Autoresearch Campaigns** require `session_id` in create request
3. **Schemas** assume "latest" iteration/decision from chat context
4. **No batch launch** capability — only sequential `!next` through chat
5. **No standalone orchestration** — every operation must go through session

### Code Evidence

```python
# autoresearch_routes.py — Current
def create_autoresearch_campaign(request: AutoresearchCampaignCreateRequest) -> AutoresearchCampaignRecord:
    campaign, _seed = build_campaign_and_seed(store, registry, request)
    return campaign

# AutoresearchCampaignCreateRequest requires session_id
class AutoresearchCampaignCreateRequest(BaseModel):
    session_id: str  # Required! No way to create standalone campaigns
    seed_methodology_draft_id: str
```

```python
# schemas.py — Current
class ResearchSessionRecord(BaseModel):
    latest_autoresearch_campaign_id: str | None = None
    latest_autoresearch_iteration_id: str | None = None
    latest_autoresearch_decision_id: str | None = None
    # Implies single "latest" campaign per session
```

---

## Proposed Architecture

### 1. Session → Campaign Relationship

**Current:**
```python
# AutoresearchCampaignCreateRequest requires session_id
{
  "session_id": "abc123",
  "seed_methodology_draft_id": "def456"
}
```

**New:**
```python
# Campaign can exist independently OR attach to session
class AutoresearchCampaignCreateRequest(BaseModel):
    # Option 1: Standalone (new)
    name: str | None = None
    description: str | None = None
    
    # Option 2: Session-bound (existing)
    session_id: str | None = None  # Optional
    
    seed_methodology_draft_id: str
    methodology_space_id: str | None = None
    resource_profile: str = "gpu-medium"
```

**Migration Path:**
- Add `name` and `description` fields (non-breaking)
- Make `session_id` optional
- Existing chat flow continues to work

---

### 2. Campaign Launch Patterns

**Current (chat-only):**
```bash
# Must go through session
POST /research-sessions/{session_id}/transitions/advance-autoresearch
```

**New (orchestration-friendly):**
```bash
# Direct campaign launch (new)
POST /autoresearch/campaigns/{campaign_id}/launch-next
POST /autoresearch/campaigns/{campaign_id}/launch-batch
POST /autoresearch/campaigns/{campaign_id}/resume

# Batch launch with explicit parameters (new)
POST /autoresearch/campaigns/{campaign_id}/launch-batch
{
  "methodology_draft_ids": ["draft-1", "draft-2", "draft-3"],
  "run_priority": "user|autonomous",
  "resource_override": "gpu-large"
}
```

**Implementation:**
```python
# autoresearch_routes.py: Add new endpoints

@app.post("/autoresearch/campaigns/{campaign_id}/launch-next")
def launch_next_methodology(
    campaign_id: str,
    run_priority: str = "user",
    resource_override: str | None = None
) -> AutoresearchLaunchBatchResponse:
    """Launch next methodology draft for a campaign (chat or programmatic)"""
    campaign = get_required_campaign(store, campaign_id)
    # ... existing launch logic

@app.post("/autoresearch/campaigns/{campaign_id}/launch-batch")
def launch_batch_methodologies(
    campaign_id: str,
    batch_request: AutoresearchLaunchBatchRequest  # New schema
) -> AutoresearchLaunchBatchResponse:
    """Launch multiple methodologies in batch (orchestration)"""
    # ... new batch orchestration
```

---

### 3. Decision Without Session Context

**Current:**
```bash
POST /autoresearch/campaigns/{campaign_id}/decide-latest
# Assumes "latest" iteration from session context
```

**New:**
```bash
# Explicit decision on specific iteration (new)
POST /autoresearch/campaigns/{campaign_id}/decide-iteration/{iteration_id}

# Decision without campaign context (new)
POST /autoresearch/decisions
{
  "iteration_id": "iter-123",
  "decision_type": "keep|discard|escalate_for_review",
  "rationale": "Top-1 accuracy improved by 2.3%"
}
```

**Schema:**
```python
class AutoresearchDecisionCreateRequest(BaseModel):
    iteration_id: str  # Required, no "latest" assumption
    decision_type: Literal["keep", "discard", "escalate_for_review"]
    rationale: str
    evidence_refs: list[str] = []
```

---

### 4. Session ↔ Campaign Decoupling

**New Session Schema:**
```python
class ResearchSessionRecord(BaseModel):
    # ... existing fields ...
    
    # Campaigns are now a list (not just "latest")
    campaign_ids: list[str] = Field(default_factory=list)
    
    # Remove "latest_autoresearch_*" fields that assume chat flow
    # Instead use explicit references for chat users
    latest_autoresearch_campaign_id: str | None = None  # Keep for backward compat
    latest_autoresearch_iteration_id: str | None = None
    latest_autoresearch_decision_id: str | None = None
```

**New Campaign Schema:**
```python
class AutoresearchCampaignRecord(BaseModel):
    campaign_id: str
    name: str  # NEW: Discoverable label
    description: str | None = None
    
    # Session binding is optional
    session_id: str | None = None  # Optional
    
    seed_methodology_draft_id: str
    methodology_space_id: str | None = None
    
    status: Literal["drafting", "running", "completed", "paused"] = "drafting"
    
    # Iterations list (not just latest)
    iteration_ids: list[str] = Field(default_factory=list)
    
    # Decisions list
    decision_ids: list[str] = Field(default_factory=list)
    
    # Resource control
    resource_profile: str = "gpu-medium"
    run_priority: Literal["user", "autonomous"] = "user"
    
    # Metadata
    created_at: datetime
    updated_at: datetime
    created_by: str  # NEW: Who initiated (human or system)
    submitted_by: str  # NEW: Who owns the runs
```

---

### 5. Orchestration Entry Points

**New Endpoints (no session required):**
```bash
# Create campaign (standalone)
POST /autoresearch/campaigns
{
  "name": "cifar100-contrastive-v0",
  "description": "Contrastive learning ablation study",
  "seed_methodology_draft_id": "seed-abc123",
  "resource_profile": "gpu-medium",
  "run_priority": "autonomous"
}

# Launch batch without chat
POST /autoresearch/campaigns/camp-123/launch-batch
{
  "methodology_draft_ids": ["draft-1", "draft-2", "draft-3"],
  "run_priority": "autonomous"
}

# Query campaigns (new)
GET /autoresearch/campaigns?status=running&created_by=system
GET /autoresearch/campaigns/{campaign_id}
GET /autoresearch/campaigns/{campaign_id}/status
GET /autoresearch/campaigns/{campaign_id}/iterations
GET /autoresearch/campaigns/{campaign_id}/decisions

# Decision (explicit iteration)
POST /autoresearch/campaigns/{campaign_id}/decide-iteration/{iteration_id}
POST /autoresearch/decisions  # Create decision without campaign context
```

---

### 6. Backward Compatibility Layer

**Keep existing chat endpoints:**
```python
# Keep current /research-sessions/{session_id}/transitions/... endpoints
# Mark as DEPRECATED in docs
# Route to new /autoresearch/* endpoints internally
```

**Migration Path:**
```python
# In autoresearch_routes.py
def _legacy_session_transition_to_new_campaign(
    session_id: str,
    transition_type: str
) -> Response:
    """Migrate chat-based transitions to use new campaign endpoints"""
    session = store.get_research_session(session_id)
    campaign_id = session.latest_autoresearch_campaign_id
    
    if transition_type == "advance":
        return launch_next_methodology(campaign_id, run_priority="user")
    elif transition_type == "decide":
        # ... mapping logic
```

---

## Benefits

1. **Chat-agnostic orchestration**: Python SDK, CI/CD, batch jobs can trigger autoresearch
2. **Explicit state**: No more "latest" assumptions that break with parallel work
3. **Discoverable campaigns**: Named campaigns instead of implicit session context
4. **Flexible run control**: Per-batch priority and resource override
5. **Clean separation**: Session (workspace) vs Campaign (experiment) concerns

---

## Example Usage

### Chat (Existing, Still Supported)
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
# Launch autoresearch from Python
campaign = client.create_autoresearch_campaign(
    name="cifar100-contrastive-ablation",
    seed_methodology_draft_id="seed-abc123",
    resource_profile="gpu-large"
)

# Launch batch
campaign.launch_batch(
    methodology_draft_ids=["draft-1", "draft-2", "draft-3"],
    run_priority="autonomous"
)

# Decision
iteration = campaign.get_iteration("iter-456")
iteration.decide("keep", rationale="Top-1 +2.3%")
```

### CI/CD (New)
```yaml
# .github/workflows/autoresearch.yml
- name: Launch ablation study
  run: |
    glasslab autoresearch launch \
      --name "test-contrastive-v0" \
      --seed-draft draft-abc123 \
      --batch draft-1 draft-2 draft-3 \
      --priority autonomous
```

---

## Migration Steps

### Phase 1: Add New Schema Fields (Non-Breaking)
```python
# Add to AutoresearchCampaignRecord
name: str  # NEW: Discoverable label
description: str | None = None

# Make session_id optional
session_id: str | None = None

# Add campaign_ids to session
campaign_ids: list[str] = Field(default_factory=list)
```

### Phase 2: Add New Endpoints (Parallel to Old)
```python
@app.post("/autoresearch/campaigns/{campaign_id}/launch-next")
@app.post("/autoresearch/campaigns/{campaign_id}/launch-batch")
@app.post("/autoresearch/decisions")
```

### Phase 3: Deprecate Chat-Only Endpoints (Docs Only)
- Mark `/research-sessions/{session_id}/transitions/...` as DEPRECATED
- Add redirect to new `/autoresearch/campaigns/{campaign_id}/...` endpoints

### Phase 4: Update research-command-router Internally
- Route chat commands to new campaign endpoints
- Remove dependency on "latest" session state

### Phase 5: Remove Legacy Endpoints (Optional, Future)
- Remove `/research-sessions/{session_id}/transitions/...` in v3
- Keep backward compatibility layer

---

## Questions for Decision

1. **Should sessions remain the primary unit?**  
   - Option A: Keep sessions as primary, add campaigns as first-class  
   - Option B: Introduce "projects" as higher-level abstraction  
   - **Recommendation**: Option A (minimal change, backward compatible)

2. **Should we keep `!next` / `!decide` chat commands?**  
   - Option A: Keep existing commands, deprecate in docs  
   - Option B: Replace with `!campaign launch` / `!campaign decide`  
   - **Recommendation**: Option A (low risk, maintain chat familiarity)

3. **Should campaigns support parallel execution groups?**  
   - Option A: Sequential only (current)  
   - Option B: Parallel groups (e.g., launch 3 methodologies simultaneously)  
   - **Recommendation**: Option A for v1, Option B as future enhancement

4. **Should the "system" (auto-decider) have different permissions?**  
   - Option A: Same permissions as human users  
   - Option B: Separate "autonomous" role with limited scope  
   - **Recommendation**: Option B (security best practice)

5. **Should runs include `campaign_status` field?**  
   - Option A: Yes, query all runs from active campaigns  
   - Option B: No, campaign state is separate concern  
   - **Recommendation**: Option A (enables orchestration workflows)

---

## Appendix: Current Code Structure

### Files Analyzed

| File | Purpose | Current Coupling |
|------|---------|------------------|
| `services/workflow-api/app/autoresearch_routes.py` | Autoresearch endpoints | Requires session_id |
| `services/workflow-api/app/schemas.py` | Data models | Assumes "latest" state |
| `services/research-command-router/app/main.py` | Chat command router | 10 hardcoded commands |
| `docs/glasslab-v2/autoresearch-lane.md` | Autoresearch spec | Chat-first narrative |
| `docs/glasslab-v2/router-and-backend-contract.md` | Router contract | Command-oriented |

### Key Pain Points

1. **No standalone campaign creation** — must have session context
2. **No batch launch** — only sequential `!next` through chat
3. **No parallel work** — "latest" assumptions break with concurrent campaigns
4. **No orchestration** — cannot integrate with CI/CD or external systems

---

## Conclusion

This refactoring preserves the existing chat experience while enabling:
- Programmatic orchestration
- CI/CD integration
- Batch execution
- Parallel experimentation

The migration is designed to be backward compatible, with chat commands continuing to work through the new orchestration layer.

**Next Step**: Implement Phase 1 (non-breaking schema changes) and Phase 2 (new endpoints) in parallel with current chat flow.
