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
) -> SourceDocumentRecord:
    now = datetime.now(timezone.utc)
    document_id = uuid4().hex
    try:
        content, content_type = fetch_source_document_bytes(source_url)
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
            title=guess_document_title(source_url),
            text_excerpt=extract_text_excerpt(content, content_type, source_url),
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
