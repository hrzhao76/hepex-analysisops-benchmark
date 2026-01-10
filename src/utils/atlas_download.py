from __future__ import annotations

from typing import Any, Protocol

import atlasopenmagic as atom


class DataTaskLike(Protocol):
    dataset: str
    skim: str
    protocol: str
    cache: bool
    max_files: int


def _get_local_paths_from_urls(urls: list[str]) -> list[str]:
    """
    atlasopenmagic get_urls may return strings like:
      "https::/path/to/local/file.root"
    Extract local paths robustly.
    """
    local_paths: list[str] = []
    for u in urls:
        if "::" in u:
            local_paths.append(u.split("::", 1)[1])
        else:
            local_paths.append(u)
    return local_paths


def ensure_data_downloaded(cfg: Any, task: DataTaskLike) -> dict[str, Any]:
    """
    Download (cache) files using atlasopenmagic, return metadata for later steps.

    - cfg must provide: cfg.release
    - task must provide: dataset, skim, protocol, cache, max_files
    """
    atom.set_release(cfg.release)

    urls = atom.get_urls(
        task.dataset,
        task.skim,
        protocol=task.protocol,
        cache=task.cache,
    )

    urls_sorted = sorted(urls)
    if getattr(task, "max_files", 0) and task.max_files > 0:
        urls_sorted = urls_sorted[: task.max_files]

    local_paths = _get_local_paths_from_urls(urls_sorted)

    return {
        "release": cfg.release,
        "dataset": task.dataset,
        "skim": task.skim,
        "protocol": task.protocol,
        "cache": task.cache,
        "n_files": len(local_paths),
        "local_paths": local_paths,
        "raw_urls": urls_sorted,
    }
