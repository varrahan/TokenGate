"""Resolve maintained RTL while keeping frozen bundles' flat source names."""
from pathlib import Path


def source_path(root, relative):
    root, relative = Path(root), Path(relative)
    path = root / relative
    if relative.parent == Path('rtl') and relative.suffix == '.v' and not path.exists():
        matches = list((root / 'rtl').rglob(relative.name))
        if len(matches) > 1:
            raise ValueError(f'Ambiguous RTL source: {relative.name}')
        if matches:
            return matches[0]
    return path


def source_relative(path, root):
    relative = Path(path).relative_to(root)
    if relative.parts and relative.parts[0] == 'rtl' and relative.suffix == '.v':
        return Path('rtl') / relative.name
    return relative
