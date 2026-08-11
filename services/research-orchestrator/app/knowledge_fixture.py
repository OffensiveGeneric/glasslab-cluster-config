"""Checked-in retrieval quality fixture.

Each entry pairs a retrieval query with a list of source documents and the
canonical URI of the source that must appear in a scoped retrieval for that
query. The documents are deliberately topically distinct so lexical and hybrid
ranking have a signal to separate. This fixture is used to compare ranking
quality without a live model or vector service.

The agent + turn_kind per entry is part of the fixture: queries 1-3 and 5 are
Honeydew protocol drafts, query 4 is Beaker implementation planning, so the
same matrix also exercises role/turn scoping (e.g. implementation files are
visible to Beaker but excluded from Honeydew protocol drafts).
"""

from __future__ import annotations

from typing import Any

from .schemas import SourceType


QUERY_RELEVANCE_FIXTURE: list[dict[str, Any]] = [
    {
        'query': 'embedding cosine similarity accuracy latency metric-search',
        'turn_kind': 'protocol_draft',
        'agent': 'honeydew',
        'relevant_uri': 'file:///fixture/metric-search.md',
        'documents': [
            {
                'source_type': SourceType.RUN_PROTOCOL,
                'uri': 'file:///fixture/metric-search.md',
                'title': 'Metric-search protocol',
                'text': (
                    'The metric-search protocol evaluates embedding cosine '
                    'similarity over GPU worker feature vectors. Primary metric '
                    'is top-1 accuracy and latency is a guardrail. Results are '
                    'reported with a fixed seed and verified metrics only.'
                ),
            },
            {
                'source_type': SourceType.TECHNIQUE_CARD,
                'uri': 'file:///fixture/technique-card.md',
                'title': 'GPU scheduling technique',
                'text': (
                    'Technique card: schedule GPU worker jobs with static '
                    'affinity and pin memory to avoid host transfer stalls.'
                ),
            },
            {
                'source_type': SourceType.EVALUATION_CONTRACT,
                'uri': 'file:///fixture/evaluation-contract.md',
                'title': 'Evaluation contract',
                'text': (
                    'The evaluation contract requires artifact integrity, a '
                    'bounded wallclock budget, and guardrails on resource use.'
                ),
            },
            {
                'source_type': SourceType.DOCUMENTATION,
                'uri': 'file:///fixture/cafeteria.md',
                'title': 'Cafeteria menu',
                'text': (
                    'The cafeteria menu lists sandwiches, soup, and coffee '
                    'specials for the week.'
                ),
            },
        ],
    },
    {
        'query': 'GPU worker scheduling affinity pinned memory jobs',
        'turn_kind': 'protocol_draft',
        'agent': 'honeydew',
        'relevant_uri': 'file:///fixture/technique-card.md',
        'documents': [
            {
                'source_type': SourceType.TECHNIQUE_CARD,
                'uri': 'file:///fixture/technique-card.md',
                'title': 'GPU scheduling technique',
                'text': (
                    'Technique card: schedule GPU worker jobs with static '
                    'affinity and pin memory to avoid host transfer stalls.'
                ),
            },
            {
                'source_type': SourceType.IMPLEMENTATION_FILE,
                'uri': 'file:///fixture/implementation.md',
                'title': 'Implementation guide',
                'text': (
                    'Implementation guide: the trainer entry point is train.py '
                    'and the model is defined in model.py with optimizer '
                    'settings in config.'
                ),
            },
            {
                'source_type': SourceType.EVALUATION_CONTRACT,
                'uri': 'file:///fixture/evaluation-contract.md',
                'title': 'Evaluation contract',
                'text': (
                    'The evaluation contract requires artifact integrity, a '
                    'bounded wallclock budget, and guardrails on resource use.'
                ),
            },
            {
                'source_type': SourceType.DOCUMENTATION,
                'uri': 'file:///fixture/cafeteria.md',
                'title': 'Cafeteria menu',
                'text': (
                    'The cafeteria menu lists sandwiches, soup, and coffee '
                    'specials for the week.'
                ),
            },
        ],
    },
    {
        'query': 'evaluation rubric guardrails wallclock artifact integrity',
        'turn_kind': 'protocol_draft',
        'agent': 'honeydew',
        'relevant_uri': 'file:///fixture/evaluation-contract.md',
        'documents': [
            {
                'source_type': SourceType.EVALUATION_CONTRACT,
                'uri': 'file:///fixture/evaluation-contract.md',
                'title': 'Evaluation contract',
                'text': (
                    'The evaluation contract requires artifact integrity, a '
                    'bounded wallclock budget, and guardrails on resource use.'
                ),
            },
            {
                'source_type': SourceType.RUN_PROTOCOL,
                'uri': 'file:///fixture/metric-search.md',
                'title': 'Metric-search protocol',
                'text': (
                    'The metric-search protocol evaluates embedding cosine '
                    'similarity over GPU worker feature vectors. Primary metric '
                    'is top-1 accuracy and latency is a guardrail.'
                ),
            },
            {
                'source_type': SourceType.DOCUMENTATION,
                'uri': 'file:///fixture/cafeteria.md',
                'title': 'Cafeteria menu',
                'text': (
                    'The cafeteria menu lists sandwiches, soup, and coffee '
                    'specials for the week.'
                ),
            },
        ],
    },
    {
        'query': 'trainer entry point train.py model.py optimizer config',
        'turn_kind': 'implementation_plan',
        'agent': 'beaker',
        'relevant_uri': 'file:///fixture/implementation.md',
        'documents': [
            {
                'source_type': SourceType.IMPLEMENTATION_FILE,
                'uri': 'file:///fixture/implementation.md',
                'title': 'Implementation guide',
                'text': (
                    'Implementation guide: the trainer entry point is train.py '
                    'and the model is defined in model.py with optimizer '
                    'settings in config.'
                ),
            },
            {
                'source_type': SourceType.TECHNIQUE_CARD,
                'uri': 'file:///fixture/technique-card.md',
                'title': 'GPU scheduling technique',
                'text': (
                    'Technique card: schedule GPU worker jobs with static '
                    'affinity and pin memory to avoid host transfer stalls.'
                ),
            },
            {
                'source_type': SourceType.DOCUMENTATION,
                'uri': 'file:///fixture/cafeteria.md',
                'title': 'Cafeteria menu',
                'text': (
                    'The cafeteria menu lists sandwiches, soup, and coffee '
                    'specials for the week.'
                ),
            },
        ],
    },
    {
        'query': 'lunch sandwich soup coffee menu',
        'turn_kind': 'protocol_draft',
        'agent': 'honeydew',
        'relevant_uri': 'file:///fixture/cafeteria.md',
        'documents': [
            {
                'source_type': SourceType.DOCUMENTATION,
                'uri': 'file:///fixture/cafeteria.md',
                'title': 'Cafeteria menu',
                'text': (
                    'The cafeteria menu lists sandwiches, soup, and coffee '
                    'specials for the week.'
                ),
            },
            {
                'source_type': SourceType.RUN_PROTOCOL,
                'uri': 'file:///fixture/metric-search.md',
                'title': 'Metric-search protocol',
                'text': (
                    'The metric-search protocol evaluates embedding cosine '
                    'similarity over GPU worker feature vectors.'
                ),
            },
            {
                'source_type': SourceType.DOCUMENTATION,
                'uri': 'file:///fixture/other-doc.md',
                'title': 'Glasslab notes',
                'text': (
                    'Glasslab maintains a bounded research pipeline with '
                    'isolated agent runtimes and immutable contracts.'
                ),
            },
        ],
    },
]
