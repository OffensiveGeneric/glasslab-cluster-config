from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import hashlib
import html
import mimetypes
import re
from pathlib import Path
from urllib import request as urllib_request
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status

from .config import Settings
from .persistence import RunStore
from .schemas import SourceDocumentRecord

HTML_TAG_RE = re.compile(r'<[^>]+>')
TITLE_WORD_RE = re.compile(r"[A-Za-z0-9]+")
TITLE_NORMALIZE_RE = re.compile(r'[^a-z0-9]+')
COMMON_TITLE_WORDS = {
    'the', 'and', 'for', 'with', 'from', 'using', 'into', 'towards', 'through',
    'over', 'under', 'based', 'study', 'learning', 'vision', 'method', 'methods',
    'approach', 'approaches', 'analysis', 'data', 'model', 'models', 'paper',
}
METHOD_KEYWORDS = [
    'vision transformer',
    'transformer',
    'cnn',
    'convolutional neural network',
    'resnet',
    'vit',
    'focal loss',
    'cross entropy',
    'contrastive learning',
    'diffusion',
    'gan',
]
LOSS_KEYWORDS = [
    'cross entropy',
    'focal loss',
    'triplet loss',
    'contrastive loss',
    'hinge loss',
    'dice loss',
    'l1 loss',
    'l2 loss',
    'mean squared error',
    'binary cross entropy',
]
ARCHITECTURE_KEYWORDS = [
    'vision transformer',
    'transformer',
    'cnn',
    'convolutional neural network',
    'resnet',
    'unet',
    'u-net',
    'efficientnet',
    'clip',
    'bert',
    'lstm',
    'graph neural network',
    'gnn',
    'autoencoder',
    'gan',
]
BASELINE_KEYWORDS = [
    'baseline',
    'random forest',
    'logistic regression',
    'linear probe',
    'svm',
    'xgboost',
    'catboost',
    'ablation',
]
METRIC_KEYWORDS = [
    'accuracy',
    'f1 score',
    'precision',
    'recall',
    'auc',
    'roc auc',
    'mean average precision',
    'mse',
    'rmse',
    'bleu',
    'iou',
    'intersection over union',
]
DATASET_KEYWORDS = [
    'cifar',
    'imagenet',
    'mnist',
    'coco',
    'laion',
    'artbench',
    'wikiart',
    'kaggle',
    'openml',
    'titanic',
]
DOMAIN_TASK_KEYWORDS = [
    'object detection',
    'image classification',
    'segmentation',
    'forgery detection',
    'anomaly detection',
    'retrieval',
    'generation',
    'captioning',
    'time series forecasting',
    'tabular classification',
    'benchmarking',
]
PYTHON_LIBRARY_KEYWORDS = [
    'torch',
    'torchvision',
    'pytorch lightning',
    'lightning',
    'transformers',
    'diffusers',
    'accelerate',
    'timm',
    'scikit-learn',
    'sklearn',
    'xgboost',
    'catboost',
    'tensorflow',
    'keras',
    'jax',
    'flax',
]


def derive_arxiv_pdf_url(source_url: str | None) -> str | None:
    if not source_url:
        return None
    normalized = source_url.strip()
    if not normalized:
        return None
    if 'arxiv.org/pdf/' in normalized:
        return normalized
    match = re.search(r'arxiv\.org/abs/([^?#/]+)', normalized)
    if match:
        return f'https://arxiv.org/pdf/{match.group(1)}.pdf'
    return None


def build_source_fetch_candidates(official_page: str | None, pdf_url: str | None) -> list[str]:
    candidates: list[str] = []

    derived_pdf = derive_arxiv_pdf_url(pdf_url) or derive_arxiv_pdf_url(official_page)
    if derived_pdf:
        candidates.append(derived_pdf)
    if pdf_url and pdf_url.strip():
        candidates.append(pdf_url.strip())
    if official_page and official_page.strip():
        candidates.append(official_page.strip())

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        deduped.append(candidate)
        seen.add(candidate)
    return deduped


def guess_document_title(source_url: str) -> str:
    parsed = source_url.rstrip('/').rsplit('/', 1)[-1]
    return parsed or 'source-document'


def _title_terms(value: str | None) -> list[str]:
    if not value:
        return []
    terms: list[str] = []
    for match in TITLE_WORD_RE.findall(value.lower()):
        if len(match) < 4 or match in COMMON_TITLE_WORDS:
            continue
        terms.append(match)
    return list(dict.fromkeys(terms))


def _normalize_title(value: str | None) -> str:
    if not value:
        return ''
    return TITLE_NORMALIZE_RE.sub(' ', value.lower()).strip()


def validate_document_identity(
    *,
    expected_title: str | None,
    fetched_title: str | None,
    text_excerpt: str | None,
) -> tuple[str, list[str]]:
    if not expected_title:
        return 'unknown', []

    expected_terms = _title_terms(expected_title)
    if not expected_terms:
        return 'unknown', ['expected title had no distinctive validation terms']

    normalized_expected = _normalize_title(expected_title)
    normalized_fetched = _normalize_title(fetched_title)
    if normalized_expected and normalized_fetched and normalized_expected == normalized_fetched:
        return 'matched', ['fetched title exactly matched the expected paper title']

    haystack = ' '.join(part for part in [fetched_title or '', text_excerpt or '']).lower()
    matched_terms = [term for term in expected_terms if term in haystack]
    if len(matched_terms) >= min(2, len(expected_terms)):
        return 'matched', [f"matched title terms: {', '.join(matched_terms[:4])}"]

    if not text_excerpt and (not fetched_title or re.fullmatch(r'[\w.-]+(?:\.pdf|\.html)?', fetched_title)):
        return 'mismatch', ['fetched document did not expose a usable title or extracted text for validation']

    return 'mismatch', [f"expected title terms not found: {', '.join(expected_terms[:4])}"]


def _truncate_text(value: str | None, limit: int = 1200) -> str | None:
    if not value:
        return None
    normalized = ' '.join(value.split()).strip()
    if not normalized:
        return None
    return normalized[:limit]


def extract_document_metadata(
    *,
    source_url: str,
    guessed_title: str | None,
    text_excerpt: str | None,
) -> dict[str, object]:
    excerpt = text_excerpt or ''
    normalized = ' '.join(excerpt.split())

    extracted_title = guessed_title
    authors: list[str] = []
    abstract_excerpt = None

    arxiv_match = re.search(
        r'Title:\s*(.*?)\s+Authors:\s*(.*?)\s+View PDF\s+HTML.*?Abstract:\s*(.*?)\s+Subjects:',
        normalized,
        flags=re.IGNORECASE,
    )
    if arxiv_match:
        extracted_title = _truncate_text(arxiv_match.group(1), 300) or extracted_title
        authors = [
            author.strip()
            for author in re.split(r',| and ', arxiv_match.group(2))
            if author.strip()
        ][:8]
        abstract_excerpt = _truncate_text(arxiv_match.group(3), 1500)
    else:
        abstract_match = re.search(
            r'Abstract[:\s]+(.*?)(?:\s+(?:Index Terms|Keywords|Introduction|I\.\s+INTRODUCTION)\b)',
            normalized,
            flags=re.IGNORECASE,
        )
        if abstract_match:
            abstract_excerpt = _truncate_text(abstract_match.group(1), 1500)

        # For PDFs, a coarse first-line title guess is still better than the filename.
        if guessed_title and re.fullmatch(r'[\w.-]+(?:\.pdf|\.html)?', guessed_title):
            lines = [line.strip() for line in excerpt.splitlines() if line.strip()]
            if lines:
                extracted_title = _truncate_text(lines[0], 300) or guessed_title

    haystack = f'{normalized} {(abstract_excerpt or "")}'.lower()
    method_hints = [keyword for keyword in METHOD_KEYWORDS if keyword in haystack]
    dataset_hints = [keyword for keyword in DATASET_KEYWORDS if keyword in haystack]
    loss_hints = [keyword for keyword in LOSS_KEYWORDS if keyword in haystack]
    architecture_hints = [keyword for keyword in ARCHITECTURE_KEYWORDS if keyword in haystack]
    baseline_hints = [keyword for keyword in BASELINE_KEYWORDS if keyword in haystack]
    metric_hints = [keyword for keyword in METRIC_KEYWORDS if keyword in haystack]
    domain_task_hints = [keyword for keyword in DOMAIN_TASK_KEYWORDS if keyword in haystack]
    python_library_hints = [keyword for keyword in PYTHON_LIBRARY_KEYWORDS if keyword in haystack]

    return {
        'title': extracted_title,
        'authors': list(dict.fromkeys(authors)),
        'abstract_excerpt': abstract_excerpt,
        'method_hints': list(dict.fromkeys(method_hints)),
        'dataset_hints': list(dict.fromkeys(dataset_hints)),
        'loss_hints': list(dict.fromkeys(loss_hints)),
        'architecture_hints': list(dict.fromkeys(architecture_hints)),
        'baseline_hints': list(dict.fromkeys(baseline_hints)),
        'metric_hints': list(dict.fromkeys(metric_hints)),
        'domain_task_hints': list(dict.fromkeys(domain_task_hints)),
        'python_library_hints': list(dict.fromkeys(python_library_hints)),
    }


def extract_text_excerpt(content: bytes, content_type: str | None, source_url: str) -> str | None:
    media_type = (content_type or '').split(';', 1)[0].strip().lower()
    try:
        if media_type in {'text/html', 'application/xhtml+xml'} or source_url.lower().endswith(('.html', '.htm')):
            decoded = content.decode('utf-8', errors='ignore')
            stripped = HTML_TAG_RE.sub(' ', decoded)
            normalized = ' '.join(html.unescape(stripped).split())
            return normalized[:4000] or None
        if media_type == 'text/plain':
            normalized = ' '.join(content.decode('utf-8', errors='ignore').split())
            return normalized[:4000] or None
        if media_type == 'application/pdf' or source_url.lower().endswith('.pdf'):
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(content))
            parts: list[str] = []
            for page in reader.pages[:5]:
                text = page.extract_text() or ''
                text = ' '.join(text.split())
                if text:
                    parts.append(text)
            joined = ' '.join(parts)
            return joined[:4000] or None
    except Exception:
        return None
    return None


def fetch_source_document_bytes(source_url: str) -> tuple[bytes, str | None]:
    request_obj = urllib_request.Request(
        source_url,
        headers={
            'User-Agent': 'glasslab-workflow-api/0.1.0',
            'Accept': 'text/html,application/pdf,application/xhtml+xml;q=0.9,*/*;q=0.8',
        },
        method='GET',
    )
    with urllib_request.urlopen(request_obj, timeout=30.0) as response:
        content = response.read()
        content_type = response.headers.get('Content-Type')
    return content, content_type


def persist_source_document_bytes(
    *,
    document_id: str,
    source_url: str,
    content: bytes,
    content_type: str | None,
    settings: Settings,
) -> str:
    guessed_ext = mimetypes.guess_extension((content_type or '').split(';', 1)[0].strip()) or ''
    if not guessed_ext:
        if source_url.lower().endswith('.pdf'):
            guessed_ext = '.pdf'
        elif source_url.lower().endswith(('.html', '.htm')):
            guessed_ext = '.html'
    key_name = f'{document_id}/source{guessed_ext}'

    if settings.source_document_storage_mode == 'minio':
        try:
            from minio import Minio
        except ImportError as exc:
            raise RuntimeError('minio package is required for source_document_storage_mode=minio') from exc

        if not settings.minio_access_key or not settings.minio_secret_key:
            raise RuntimeError('minio credentials are required for source_document_storage_mode=minio')

        client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        bucket = settings.source_document_bucket
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
        client.put_object(
            bucket,
            key_name,
            BytesIO(content),
            length=len(content),
            content_type=(content_type or 'application/octet-stream'),
        )
        return f's3://{bucket}/{key_name}'

    base_dir = Path(settings.source_document_storage_dir)
    target = base_dir / document_id / f'source{guessed_ext}'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return target.as_uri()


def ingest_source_document(
    source_url: str,
    submitted_by: str,
    settings: Settings,
    store: RunStore,
    session_id: str | None = None,
    expected_title: str | None = None,
) -> SourceDocumentRecord:
    now = datetime.now(timezone.utc)
    document_id = uuid4().hex
    try:
        content, content_type = fetch_source_document_bytes(source_url)
        fetched_title = guess_document_title(source_url)
        text_excerpt = extract_text_excerpt(content, content_type, source_url)
        metadata = extract_document_metadata(
            source_url=source_url,
            guessed_title=fetched_title,
            text_excerpt=text_excerpt,
        )
        fetched_title = str(metadata.get('title') or fetched_title)
        validation_status, validation_notes = validate_document_identity(
            expected_title=expected_title,
            fetched_title=fetched_title,
            text_excerpt=text_excerpt,
        )
        storage_uri = persist_source_document_bytes(
            document_id=document_id,
            source_url=source_url,
            content=content,
            content_type=content_type,
            settings=settings,
        )
        record = SourceDocumentRecord(
            document_id=document_id,
            created_at=now,
            updated_at=now,
            status='fetched',
            source_url=source_url,
            submitted_by=submitted_by,
            storage_uri=storage_uri,
            content_type=content_type,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            title=fetched_title,
            text_excerpt=text_excerpt,
            authors=list(metadata.get('authors') or []),
            abstract_excerpt=metadata.get('abstract_excerpt'),
            method_hints=list(metadata.get('method_hints') or []),
            dataset_hints=list(metadata.get('dataset_hints') or []),
            loss_hints=list(metadata.get('loss_hints') or []),
            architecture_hints=list(metadata.get('architecture_hints') or []),
            baseline_hints=list(metadata.get('baseline_hints') or []),
            metric_hints=list(metadata.get('metric_hints') or []),
            domain_task_hints=list(metadata.get('domain_task_hints') or []),
            python_library_hints=list(metadata.get('python_library_hints') or []),
            expected_title=expected_title,
            validation_status=validation_status,
            validation_notes=validation_notes,
            session_id=session_id,
        )
    except Exception as exc:
        record = SourceDocumentRecord(
            document_id=document_id,
            created_at=now,
            updated_at=now,
            status='fetch-failed',
            source_url=source_url,
            submitted_by=submitted_by,
            fetch_error=str(exc),
            title=guess_document_title(source_url),
            expected_title=expected_title,
            session_id=session_id,
        )
    store.save_source_document(record)
    return record


def register_source_document_routes(app: FastAPI, *, store: RunStore) -> None:
    @app.get('/source-documents', response_model=list[SourceDocumentRecord])
    def list_source_documents() -> list[SourceDocumentRecord]:
        return store.list_source_documents()

    @app.get('/source-documents/latest', response_model=SourceDocumentRecord)
    def get_latest_source_document() -> SourceDocumentRecord:
        record = store.get_latest_source_document()
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='source document not found')
        return record

    @app.get('/source-documents/{document_id}', response_model=SourceDocumentRecord)
    def get_source_document(document_id: str) -> SourceDocumentRecord:
        record = store.get_source_document(document_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='source document not found')
        return record
