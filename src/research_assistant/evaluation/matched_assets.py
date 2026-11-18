"""Public-only asset boundary for the matched study; never resolve private input paths."""

from pathlib import Path
import stat


def public_asset(value: str | Path) -> Path:
    """Reject escapes, secrets and reparse points before reading a named public asset."""
    root = Path.cwd().resolve()
    path = Path(value)
    if path.is_absolute():
        try:
            path = path.relative_to(root)
        except ValueError:
            raise ValueError('Matched public assets must belong to this checkout') from None
    if not path.parts or '..' in path.parts:
        raise ValueError('Invalid matched public path')
    name = path.as_posix()
    roots = ('src/research_assistant/', 'scripts/', 'tests/', 'manifests/',
             'runs/retrieval-v2/m5-5/', '.cache/models/', '.cache/rerankers/', '.cache/tiktoken/')
    if name not in {'uv.lock', 'pyproject.toml', 'compose.yaml', '.env.example'} and not name.startswith(roots):
        raise ValueError('Matched asset is outside the versioned public allowlist')
    if any(part == '.git' or part.startswith('.env') for part in path.parts) and name != '.env.example':
        raise ValueError('Secret/configuration files are not public freeze assets')
    for index in range(1, len(path.parts) + 1):
        component = root.joinpath(*path.parts[:index])
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400):
            raise ValueError('Matched public assets may not traverse symlinks/junctions')
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError('Matched public asset escapes the checkout')
    return resolved
