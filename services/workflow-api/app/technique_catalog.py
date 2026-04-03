from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, status

from .persistence import RunStore
from .schemas import (
    IntakeRecord,
    TechniqueCatalogImportCard,
    TechniqueCatalogImportRequest,
    TechniqueCatalogRecord,
    TechniqueKnowledgeRecord,
)


def normalize_unique_strings(items: Iterable[str]) -> list[str]:
    cleaned = [' '.join(item.split()).strip() for item in items if isinstance(item, str) and item.strip()]
    return list(dict.fromkeys(cleaned))


def build_technique_catalog_record(
    card: TechniqueCatalogImportCard,
    *,
    import_source: str,
    existing: TechniqueCatalogRecord | None = None,
) -> TechniqueCatalogRecord:
    now = datetime.now(timezone.utc)
    created_at = existing.created_at if existing is not None else now
    technique_id = existing.technique_id if existing is not None else uuid4().hex
    return TechniqueCatalogRecord(
        technique_id=technique_id,
        created_at=created_at,
        updated_at=now,
        name=card.name.strip(),
        aliases=normalize_unique_strings(card.aliases),
        summary=card.summary,
        problem_types=normalize_unique_strings(card.problem_types),
        algorithm_family=card.algorithm_family.strip() if isinstance(card.algorithm_family, str) and card.algorithm_family.strip() else None,
        specific_algorithms=normalize_unique_strings(card.specific_algorithms),
        automl_frameworks=normalize_unique_strings(card.automl_frameworks),
        preprocessing_steps=normalize_unique_strings(card.preprocessing_steps),
        loss_functions=normalize_unique_strings(card.loss_functions),
        optimizers=normalize_unique_strings(card.optimizers),
        hyperparameter_optimization=normalize_unique_strings(card.hyperparameter_optimization),
        validation_strategies=normalize_unique_strings(card.validation_strategies),
        primary_metrics=normalize_unique_strings(card.primary_metrics),
        uncertainty_quantification=normalize_unique_strings(card.uncertainty_quantification),
        python_packages=normalize_unique_strings(card.python_packages),
        gpu_required=card.gpu_required,
        resource_profile=card.resource_profile.strip() if isinstance(card.resource_profile, str) and card.resource_profile.strip() else None,
        workflow_ids=normalize_unique_strings(card.workflow_ids),
        template_compatibility=normalize_unique_strings(card.template_compatibility),
        common_failure_modes=normalize_unique_strings(card.common_failure_modes),
        source_refs=normalize_unique_strings(card.source_refs),
        import_source=import_source.strip() or 'notebooklm-manual-export',
        notes=normalize_unique_strings(card.notes),
    )


def import_technique_catalog(
    store: RunStore,
    request: TechniqueCatalogImportRequest,
) -> list[TechniqueCatalogRecord]:
    existing_by_name = {
        record.name.lower(): record
        for record in store.list_technique_catalog_records()
    }
    imported: list[TechniqueCatalogRecord] = []
    for card in request.cards:
        existing = existing_by_name.get(card.name.lower()) if request.replace_existing else None
        record = build_technique_catalog_record(card, import_source=request.import_source, existing=existing)
        store.save_technique_catalog_record(record)
        imported.append(record)
    return imported


def search_technique_catalog(store: RunStore, query: str | None = None) -> list[TechniqueCatalogRecord]:
    records = store.list_technique_catalog_records()
    if not query:
        return records
    lowered = query.lower()
    matched: list[TechniqueCatalogRecord] = []
    for record in records:
        haystacks = [
            record.name,
            *record.aliases,
            *record.problem_types,
            *record.specific_algorithms,
            *( [record.algorithm_family] if record.algorithm_family else [] ),
            *record.python_packages,
            *record.workflow_ids,
        ]
        if any(lowered in item.lower() for item in haystacks):
            matched.append(record)
    return matched


def match_catalog_records_for_intake(intake: IntakeRecord, store: RunStore) -> list[TechniqueCatalogRecord]:
    text = ' '.join([intake.raw_request, intake.normalized_summary, *intake.notes, *intake.source_refs]).lower()
    matches: list[tuple[int, TechniqueCatalogRecord]] = []
    for record in store.list_technique_catalog_records():
        score = 0
        phrases = [
            record.name,
            *record.aliases,
            *record.specific_algorithms,
            *record.python_packages,
            *record.problem_types,
        ]
        if record.algorithm_family:
            phrases.append(record.algorithm_family)
        for phrase in phrases:
            phrase = phrase.strip()
            if len(phrase) < 3:
                continue
            if phrase.lower() in text:
                score += 3 if phrase.lower() == record.name.lower() else 1
        if score:
            matches.append((score, record))
    matches.sort(key=lambda item: (-item[0], item[1].name.lower()))
    return [record for _, record in matches[:6]]


def enrich_technique_knowledge_from_catalog(
    technique_knowledge: TechniqueKnowledgeRecord,
    matched_records: list[TechniqueCatalogRecord],
) -> TechniqueKnowledgeRecord:
    if not matched_records:
        return technique_knowledge
    model_families = normalize_unique_strings(
        [
            *technique_knowledge.model_families,
            *[record.algorithm_family for record in matched_records if record.algorithm_family],
            *[algorithm for record in matched_records for algorithm in record.specific_algorithms],
        ]
    )
    metrics = normalize_unique_strings(
        [*technique_knowledge.metrics, *[metric for record in matched_records for metric in record.primary_metrics]]
    )
    losses = normalize_unique_strings(
        [*technique_knowledge.losses_or_distances, *[loss for record in matched_records for loss in record.loss_functions]]
    )
    split_strategies = normalize_unique_strings(
        [*technique_knowledge.split_strategies, *[split for record in matched_records for split in record.validation_strategies]]
    )
    python_packages = normalize_unique_strings(
        [*technique_knowledge.python_packages, *[pkg for record in matched_records for pkg in record.python_packages]]
    )
    failure_modes = normalize_unique_strings(
        [*technique_knowledge.failure_modes, *[mode for record in matched_records for mode in record.common_failure_modes]]
    )
    catalog_ids = normalize_unique_strings(
        [*technique_knowledge.catalog_technique_ids, *[record.technique_id for record in matched_records]]
    )
    return technique_knowledge.model_copy(
        update={
            'model_families': model_families,
            'metrics': metrics,
            'losses_or_distances': losses,
            'split_strategies': split_strategies,
            'python_packages': python_packages,
            'failure_modes': failure_modes,
            'catalog_technique_ids': catalog_ids,
        }
    )


def register_technique_catalog_routes(app: FastAPI, *, store: RunStore) -> None:
    @app.post('/technique-catalog/import', response_model=list[TechniqueCatalogRecord], status_code=status.HTTP_201_CREATED)
    def import_technique_catalog_records(request: TechniqueCatalogImportRequest) -> list[TechniqueCatalogRecord]:
        return import_technique_catalog(store, request)

    @app.get('/technique-catalog', response_model=list[TechniqueCatalogRecord])
    def list_technique_catalog_records(q: str | None = Query(default=None, alias='query')) -> list[TechniqueCatalogRecord]:
        return search_technique_catalog(store, q)

    @app.get('/technique-catalog/{technique_id}', response_model=TechniqueCatalogRecord)
    def get_technique_catalog_record(technique_id: str) -> TechniqueCatalogRecord:
        record = store.get_technique_catalog_record(technique_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='technique catalog record not found')
        return record
