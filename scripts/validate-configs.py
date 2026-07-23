#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

import yaml


EXCLUDED_PARTS = {
    '.git',
    '.mypy_cache',
    '.pytest_cache',
    '__pycache__',
    'node_modules',
}

EXCLUDED_SUFFIXES = {
    '.bak',
    '.bak2',
    '.bak3',
}


def should_skip(path: Path) -> bool:
    if any(part in EXCLUDED_PARTS for part in path.parts):
        return True
    return any(path.name.endswith(suffix) for suffix in EXCLUDED_SUFFIXES)


def main() -> int:
    yaml_errors: list[tuple[str, str]] = []
    json_errors: list[tuple[str, str]] = []

    for path in sorted(Path('.').rglob('*')):
        if should_skip(path) or path.is_dir():
            continue

        suffix = path.suffix.lower()
        if suffix in {'.yaml', '.yml'}:
            try:
                with path.open() as fh:
                    list(yaml.safe_load_all(fh))
            except Exception as exc:
                yaml_errors.append((str(path), str(exc)))
        elif suffix == '.json':
            try:
                with path.open() as fh:
                    json.load(fh)
            except Exception as exc:
                json_errors.append((str(path), str(exc)))

    if yaml_errors:
        print('YAML errors:')
        for path, exc in yaml_errors:
            print(f'  - {path}: {exc}')
    if json_errors:
        print('JSON errors:')
        for path, exc in json_errors:
            print(f'  - {path}: {exc}')

    if yaml_errors or json_errors:
        return 1

    print('All current YAML and JSON files parsed successfully.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
