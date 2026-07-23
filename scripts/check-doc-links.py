#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlparse


MARKDOWN_LINK = re.compile(r'(?<!!)\[[^\]]+\]\(([^)]+)\)')
CURRENT_DOCS = [
    Path('README.md'),
    Path('CONTRIBUTING.md'),
    Path('docs/glasslab-v2/README.md'),
    Path('docs/glasslab-v2/current/README.md'),
    Path('docs/glasslab-v2/system-map-2026-07.md'),
    Path('docs/glasslab-v2/ci-policy-2026-07.md'),
    Path('docs/glasslab-v2/learning-task-flow.md'),
    Path('docs/glasslab-v2/investigation-api-v1.md'),
    Path('docs/glasslab-v2/local-model-command-surface.md'),
    Path('docs/glasslab-v2/deprecated-api-surface-2026-07.md'),
]
SKIP_PREFIXES = (
    'http://',
    'https://',
    'mailto:',
    '#',
)


def iter_markdown_files() -> list[Path]:
    return [path for path in CURRENT_DOCS if path.exists()]


def normalize_target(raw_target: str) -> str:
    target = raw_target.strip()
    if not target or target.startswith(SKIP_PREFIXES):
        return ''
    if '://' in target:
        return ''
    parsed = urlparse(target)
    return unquote(parsed.path)


def main() -> int:
    failures: list[str] = []

    for path in iter_markdown_files():
        text = path.read_text(errors='ignore')
        for match in MARKDOWN_LINK.finditer(text):
            raw_target = match.group(1)
            target = normalize_target(raw_target)
            if not target:
                continue
            if target.startswith('/'):
                candidate = Path(target.lstrip('/'))
            else:
                candidate = path.parent / target
            if not candidate.exists():
                failures.append(f'{path}: missing link target {raw_target}')

    if failures:
        print('Markdown link errors:')
        for failure in failures:
            print(f'  - {failure}')
        return 1

    print('Markdown links resolved successfully.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
