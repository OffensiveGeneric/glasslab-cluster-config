"""Contract candidate sealing, integrity verification, and promotion.

Covers the full seal -> promote -> resolve lifecycle, digest-based tamper
rejection, and the unsupported-input rules (no checksums, no symlinks) that
keep a sealed bundle byte-exact and safe to promote to the trusted catalog.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.contract_candidates import (
    ContractCandidateError,
    ContractCandidateManager,
)
from app.contracts import ContractIntegrityError, EvaluationContractResolver


def _write_candidate(root: Path) -> None:
    # A complete candidate bundle mirroring what Beaker's agent would produce:
    # descriptor plus wrapper, evaluator, and both JSON schemas.
    root.mkdir(parents=True)
    descriptor = {
        'contract_id': 'candidate-v1',
        'version': '1.0.0',
        'manifest': {
            'primary_metric': 'score',
            'primary_metric_direction': 'maximize',
        },
        'execution_wrapper': 'run_contract.py',
        'evaluation_entry_point': 'evaluator.py',
        'expected_input_schema': 'input.schema.json',
        'expected_output_schema': 'output.schema.json',
        'required_artifacts': ['metrics.json', 'evaluation.json'],
        'resource_constraints': {
            'cpu': 1,
            'memory_gib': 1,
            'gpus': 0,
            'wallclock_minutes': 5,
        },
        'container_image_digest': None,
    }
    (root / 'contract.json').write_text(json.dumps(descriptor))
    (root / 'run_contract.py').write_text('print("wrapper")\n')
    (root / 'evaluator.py').write_text('print("evaluate")\n')
    (root / 'input.schema.json').write_text(
        json.dumps({'type': 'object'})
    )
    (root / 'output.schema.json').write_text(
        json.dumps({'type': 'object'})
    )


def test_candidate_is_sealed_verified_and_promoted(tmp_path: Path) -> None:
    source = tmp_path / 'source'
    _write_candidate(source)
    manager = ContractCandidateManager(
        sealed_root=str(tmp_path / 'sealed'),
        promoted_root=str(tmp_path / 'shared' / 'bundles'),
        catalog_path=str(tmp_path / 'shared' / 'catalog.json'),
        shared_mount_root=str(tmp_path),
    )

    sealed = manager.seal(
        source=source,
        contract_id='candidate-v1',
        version='1.0.0',
    )
    promoted = manager.promote(
        sealed_path=sealed.sealed_path,
        expected_digest=sealed.digest,
    )

    resolved = EvaluationContractResolver(
        str(tmp_path / 'shared' / 'bundles')
    ).resolve('candidate-v1', '1.0.0')
    assert promoted == Path(resolved.root_path)
    assert resolved.digest == sealed.digest
    catalog = json.loads(
        (tmp_path / 'shared' / 'catalog.json').read_text()
    )
    assert catalog['candidate-v1@1.0.0']['digest'] == sealed.digest


def test_sealed_candidate_tampering_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / 'source'
    _write_candidate(source)
    manager = ContractCandidateManager(
        sealed_root=str(tmp_path / 'sealed'),
        promoted_root=str(tmp_path / 'shared' / 'bundles'),
        catalog_path=str(tmp_path / 'shared' / 'catalog.json'),
        shared_mount_root=str(tmp_path),
    )
    sealed = manager.seal(
        source=source,
        contract_id='candidate-v1',
        version='1.0.0',
    )
    evaluator = sealed.sealed_path / 'evaluator.py'
    evaluator.chmod(0o644)
    evaluator.write_text('print("replaced")\n')

    with pytest.raises(ContractIntegrityError, match='digest mismatch'):
        manager.promote(
            sealed_path=sealed.sealed_path,
            expected_digest=sealed.digest,
        )


def test_candidate_cannot_supply_checksum_or_symlink(tmp_path: Path) -> None:
    source = tmp_path / 'source'
    _write_candidate(source)
    (source / 'contract.sha256').write_text('0' * 64)
    manager = ContractCandidateManager(
        sealed_root=str(tmp_path / 'sealed'),
        promoted_root=str(tmp_path / 'shared' / 'bundles'),
        catalog_path=str(tmp_path / 'shared' / 'catalog.json'),
        shared_mount_root=str(tmp_path),
    )
    with pytest.raises(ContractCandidateError, match='unsupported'):
        manager.seal(
            source=source,
            contract_id='candidate-v1',
            version='1.0.0',
        )

    (source / 'contract.sha256').unlink()
    (source / 'linked.py').symlink_to(source / 'evaluator.py')
    with pytest.raises(ContractCandidateError, match='symlinks'):
        manager.seal(
            source=source,
            contract_id='candidate-v1',
            version='1.0.0',
        )
