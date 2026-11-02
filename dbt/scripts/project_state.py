import hashlib
from pathlib import Path

IGNORED = {
    'data', 'evidence', 'target', 'dbt_packages', 'logs', '__pycache__',
    '.git', '.pytest_cache', '__MACOSX', '.mypy_cache', '.ruff_cache',
}
SUFFIXES = {'.py', '.sql', '.yml', '.yaml', '.json', '.csv', '.sh', '.toml', '.xml', '.txt'}
SPECIAL = {'Dockerfile', 'Dockerfile.screenshot', 'Makefile', '.sqlfluff',
           '.sqlfluffignore', '.dockerignore', '.gitignore'}


def project_files(root=Path('.')):
    root = Path(root)
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        if not path.is_file() or any(part in IGNORED for part in relative.parts):
            continue
        if path.name.startswith(('.env', '._')) or path.name == '.DS_Store':
            continue
        if path.suffix not in SUFFIXES and path.name not in SPECIAL:
            continue
        yield relative, path


def file_hashes(root=Path('.')):
    return {relative.as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for relative, path in project_files(root)}


def code_hash(root=Path('.')):
    digest = hashlib.sha256()
    for relative, path in project_files(root):
        digest.update(relative.as_posix().encode())
        digest.update(b'\0')
        digest.update(path.read_bytes())
    return digest.hexdigest()
