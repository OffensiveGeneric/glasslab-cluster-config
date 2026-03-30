from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request
from uuid import uuid4

from .config import Settings
from .persistence import RunStore
from .registry import WorkflowRegistry
from .schemas import IntakeRecord, InterpretationRecord
from .stage_inference import build_interpretation_notes, normalize_unique_strings

LOGGER = logging.getLogger(__name__)


def validate_interpretation_agent_draft(
    draft: dict[str, Any],
    intake: IntakeRecord,
    registry: WorkflowRegistry,
) -> dict[str, Any]:
    _ = intake
    required_string_fields = ("source_type", "normalized_summary", "extracted_method_summary", "literature_state_summary")
    for field_name in required_string_fields:
        value = draft.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"interpretation agent draft missing valid {field_name}")

    normalized = {
        "source_type": draft["source_type"].strip(),
        "normalized_summary": " ".join(draft["normalized_summary"].split())[:500],
        "extracted_method_summary": " ".join(draft["extracted_method_summary"].split())[:500],
        "literature_state_summary": " ".join(draft["literature_state_summary"].split())[:500],
        "candidate_workflow_families": normalize_unique_strings(list(draft.get("candidate_workflow_families", []))),
        "dataset_hints": normalize_unique_strings(list(draft.get("dataset_hints", []))),
        "evaluation_targets": normalize_unique_strings(list(draft.get("evaluation_targets", []))),
        "extracted_claims": normalize_unique_strings(list(draft.get("extracted_claims", [])))[:3],
        "research_gaps": normalize_unique_strings(list(draft.get("research_gaps", [])))[:4],
        "bounded_experiment_ideas": normalize_unique_strings(list(draft.get("bounded_experiment_ideas", [])))[:3],
        "recommended_method_family": (
            " ".join(str(draft.get("recommended_method_family", "")).split())[:120] or None
        ),
        "recommended_datasets": normalize_unique_strings(list(draft.get("recommended_datasets", [])))[:4],
        "recommended_metrics": normalize_unique_strings(list(draft.get("recommended_metrics", [])))[:4],
        "recommended_baselines": normalize_unique_strings(list(draft.get("recommended_baselines", [])))[:4],
        "recommended_architectures": normalize_unique_strings(list(draft.get("recommended_architectures", [])))[:4],
        "recommended_python_packages": normalize_unique_strings(list(draft.get("recommended_python_packages", [])))[:6],
        "preferred_workflow_id": (
            " ".join(str(draft.get("preferred_workflow_id", "")).split())[:120] or None
        ),
        "preferred_resource_profile": (
            " ".join(str(draft.get("preferred_resource_profile", "")).split())[:120] or None
        ),
        "gpu_required": bool(draft.get("gpu_required", False)),
        "mutation_axes": normalize_unique_strings(list(draft.get("mutation_axes", [])))[:6],
        "unresolved_questions": normalize_unique_strings(list(draft.get("unresolved_questions", []))),
    }

    invalid_workflows = [
        workflow_id for workflow_id in normalized["candidate_workflow_families"]
        if registry.get_workflow(workflow_id) is None
    ]
    if invalid_workflows:
        raise ValueError(f'interpretation agent returned unapproved workflow ids: {", ".join(invalid_workflows)}')

    return normalized


def build_interpretation_record_from_agent_draft(
    intake: IntakeRecord,
    validated_draft: dict[str, Any],
) -> InterpretationRecord:
    now = datetime.now(timezone.utc)
    unresolved_questions = list(validated_draft["unresolved_questions"])
    return InterpretationRecord(
        interpretation_id=uuid4().hex,
        intake_id=intake.intake_id,
        created_at=now,
        updated_at=now,
        status="ready_for_assessment" if not unresolved_questions else "needs_review",
        source_type=validated_draft["source_type"],
        normalized_summary=validated_draft["normalized_summary"],
        extracted_method_summary=validated_draft["extracted_method_summary"],
        literature_state_summary=validated_draft["literature_state_summary"],
        candidate_workflow_families=validated_draft["candidate_workflow_families"],
        dataset_hints=validated_draft["dataset_hints"],
        evaluation_targets=validated_draft["evaluation_targets"],
        extracted_claims=validated_draft["extracted_claims"],
        research_gaps=validated_draft["research_gaps"],
        bounded_experiment_ideas=validated_draft["bounded_experiment_ideas"],
        recommended_method_family=validated_draft["recommended_method_family"],
        recommended_datasets=validated_draft["recommended_datasets"],
        recommended_metrics=validated_draft["recommended_metrics"],
        recommended_baselines=validated_draft["recommended_baselines"],
        recommended_architectures=validated_draft["recommended_architectures"],
        recommended_python_packages=validated_draft["recommended_python_packages"],
        preferred_workflow_id=validated_draft["preferred_workflow_id"],
        preferred_resource_profile=validated_draft["preferred_resource_profile"],
        gpu_required=validated_draft["gpu_required"],
        mutation_axes=validated_draft["mutation_axes"],
        unresolved_questions=unresolved_questions,
        submitted_by=intake.submitted_by,
        session_id=intake.session_id,
    )


def call_interpretation_agent(
    intake: IntakeRecord,
    settings: Settings,
    registry: WorkflowRegistry,
    store: RunStore,
) -> InterpretationRecord | None:
    if not settings.interpretation_agent_enabled:
        return None

    payload = {
        "request_id": intake.intake_id,
        "intake": {
            "intake_id": intake.intake_id,
            "source_type": intake.source_type,
            "source_refs": intake.source_refs,
            "document_refs": intake.document_refs,
            "raw_request": intake.raw_request,
            "normalized_summary": intake.normalized_summary,
            "workflow_family_candidates": intake.workflow_family_candidates,
            "notes": build_interpretation_notes(intake, store),
            "submitted_by": intake.submitted_by,
        },
    }
    request_obj = urllib_request.Request(
        settings.interpretation_agent_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib_request.urlopen(request_obj, timeout=settings.interpretation_agent_timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))
        draft = body.get("draft")
        if not isinstance(draft, dict):
            raise ValueError("interpretation agent response missing draft object")
        validated_draft = validate_interpretation_agent_draft(draft, intake, registry)
        return build_interpretation_record_from_agent_draft(intake, validated_draft)
    except (urllib_error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        LOGGER.warning("interpretation-agent fallback for intake %s: %s", intake.intake_id, exc)
        return None
