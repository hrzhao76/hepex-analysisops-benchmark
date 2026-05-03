import os
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Optional
import atlasopenmagic as atom


@dataclass
class DownloadResult:
    url: str
    local_path: str
    ok: bool
    skipped: bool
    expected_size: Optional[int]
    local_size: int
    error: Optional[str] = None


# -----------------------------
# Low-level HTTP helpers (urllib)
# -----------------------------
def _head_content_length(url: str, timeout: int = 30) -> Optional[int]:
    """
    Return Content-Length from HEAD if available, else None.
    """
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        cl = resp.headers.get("Content-Length")
        if cl is None:
            return None
        try:
            return int(cl)
        except ValueError:
            return None


def _download_to_file(url: str, dst_path: str, timeout: int = 60, chunk_size: int = 1024 * 1024) -> int:
    """
    Download url to dst_path (overwrite). Returns bytes written.
    Uses streaming read to avoid urlretrieve pitfalls.
    """
    req = urllib.request.Request(url, method="GET")
    written = 0
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        with open(dst_path, "wb") as f:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                written += len(chunk)
    return written


def _ensure_one_file(
    url: str,
    output_dir: str,
    timeout_head: int = 30,
    timeout_get: int = 120,
    max_retries: int = 2,
    verbose: bool = True,
) -> DownloadResult:
    """
    Ensure a single file is present and complete (by Content-Length if available).
    """
    filename = os.path.basename(url)
    local_path = os.path.join(output_dir, filename)
    part_path = local_path + ".part"

    # Local size (if any)
    local_size = os.path.getsize(local_path) if os.path.exists(local_path) else 0

    # Expected size from HEAD (best effort)
    expected_size: Optional[int] = None
    try:
        expected_size = _head_content_length(url, timeout=timeout_head)
    except Exception:
        expected_size = None  # server may not support HEAD / transient issues

    # If we can validate size and it matches -> skip
    if expected_size is not None and os.path.exists(local_path) and local_size == expected_size:
        return DownloadResult(
            url=url,
            local_path=local_path,
            ok=True,
            skipped=True,
            expected_size=expected_size,
            local_size=local_size,
        )

    # If expected_size unknown, but file exists and nonzero, you can choose to trust it.
    # For safety in benchmark context, we *do not* trust it; we re-download unless you want otherwise.
    # You can change this policy if desired.
    # if expected_size is None and os.path.exists(local_path) and local_size > 0:
    #     return DownloadResult(... skipped=True ...)

    # Download with retries
    last_err: Optional[str] = None
    for attempt in range(max_retries + 1):
        try:
            # clean stale part
            if os.path.exists(part_path):
                try:
                    os.remove(part_path)
                except OSError:
                    pass

            if verbose:
                msg = f"[download] {filename}"
                if expected_size is not None:
                    msg += f" (expected {expected_size} bytes)"
                if os.path.exists(local_path):
                    msg += f" [local {local_size} bytes -> redownload]"
                print(msg)

            written = _download_to_file(url, part_path, timeout=timeout_get)

            # Verify if we know expected_size
            if expected_size is not None and written != expected_size:
                raise RuntimeError(f"size mismatch: wrote {written}, expected {expected_size}")

            # Atomic move into place
            os.replace(part_path, local_path)

            final_size = os.path.getsize(local_path)
            return DownloadResult(
                url=url,
                local_path=local_path,
                ok=True,
                skipped=False,
                expected_size=expected_size,
                local_size=final_size,
            )

        except Exception as e:
            last_err = str(e)
            # backoff
            if attempt < max_retries:
                time.sleep(0.5 * (attempt + 1))
            continue

    # Failed
    final_size = os.path.getsize(local_path) if os.path.exists(local_path) else 0
    return DownloadResult(
        url=url,
        local_path=local_path,
        ok=False,
        skipped=False,
        expected_size=expected_size,
        local_size=final_size,
        error=last_err,
    )


def _strip_root_prefix(entry: str) -> str:
    return entry.split("::", 1)[1] if "::" in entry else entry


def _sample_id(name: str) -> str:
    text = name.lower()
    if text == "data":
        return "data"
    if "signal" in text:
        return "signal_mh125"
    if "zz" in text:
        return "background_zzstar"
    if "background" in text:
        return "background_z_ttbar_ttb_vvv"
    normalized = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return normalized or "sample"


def _sample_role(name: str, sample: dict[str, Any]) -> str:
    if isinstance(sample.get("role"), str) and sample["role"].strip():
        return sample["role"].strip()
    text = name.lower()
    if text == "data":
        return "data"
    if "signal" in text:
        return "signal"
    return "background"


def _extract_did(url: str, sample: dict[str, Any]) -> str | int | None:
    dids = sample.get("dids") or []
    if dids == ["data"] or dids == ("data",):
        return "data"
    match = re.search(r"_mc_(\d+)\.", os.path.basename(url))
    if match:
        return int(match.group(1))
    return None


def _entry_list(sample: Any) -> list[str]:
    if isinstance(sample, dict):
        entries = sample.get("list", [])
    else:
        entries = sample
    if not isinstance(entries, list):
        return []
    return [_strip_root_prefix(str(entry)) for entry in entries]


def _ensure_sample_files(
    urls: list[str],
    output_dir: str,
    *,
    workers: int,
    verbose: bool,
) -> list[DownloadResult]:
    results: list[DownloadResult] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futs = [ex.submit(_ensure_one_file, url, output_dir, verbose=verbose) for url in urls]
        for fut in as_completed(futs):
            r = fut.result()
            results.append(r)
            if verbose:
                if r.ok and r.skipped:
                    print(f"[ok][skip] {os.path.basename(r.local_path)} ({r.local_size} bytes)")
                elif r.ok:
                    print(f"[ok]      {os.path.basename(r.local_path)} ({r.local_size} bytes)")
                else:
                    print(f"[fail]    {os.path.basename(r.local_path)} err={r.error}")
    url_to_result = {result.url: result for result in results}
    return [url_to_result[url] for url in urls if url in url_to_result]


# -----------------------------
# High-level: get URL list via atlasopenmagic + multithread ensure
# -----------------------------
def ensure_atlas_open_data_downloaded(
    skim: str = "2muons",
    release: str = "2025e-13tev-beta",
    dataset: str = "data",
    protocol: str = "https",
    output_dir: str = "./atlas_data",
    max_files: int = 0,
    workers: int = 6,
    verbose: bool = True,
) -> dict[str, Any]:
    """
    Ensure ATLAS Open Data files are present locally & complete. Multi-threaded.

    Returns metadata including local_paths and per-file results.
    """
    atom.set_release(release)
    os.makedirs(output_dir, exist_ok=True)

    # Get URL list (no atlasopenmagic cache here)
    files_list = atom.get_urls(dataset, skim, protocol=protocol, cache=False)
    urls = []
    for entry in sorted(files_list):
        # atlasopenmagic returns "root::https://.../file.root"
        if "::" in entry:
            urls.append(entry.split("::", 1)[1])
        else:
            urls.append(entry)

    if max_files and max_files > 0:
        urls = urls[:max_files]

    results: list[DownloadResult] = []
    ok_paths: list[str] = []

    if verbose:
        print(f"[ensure] release={release} dataset={dataset} skim={skim} files={len(urls)} workers={workers}")
        print(f"[ensure] output_dir={os.path.abspath(output_dir)}")

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futs = [ex.submit(_ensure_one_file, url, output_dir, verbose=verbose) for url in urls]
        for fut in as_completed(futs):
            r = fut.result()
            results.append(r)
            if r.ok:
                ok_paths.append(r.local_path)
            if verbose:
                if r.ok and r.skipped:
                    print(f"[ok][skip] {os.path.basename(r.local_path)} ({r.local_size} bytes)")
                elif r.ok:
                    print(f"[ok]      {os.path.basename(r.local_path)} ({r.local_size} bytes)")
                else:
                    print(f"[fail]    {os.path.basename(r.local_path)} err={r.error}")

    # Keep stable order: same as urls
    url_to_path = {r.url: r.local_path for r in results if r.ok}
    local_paths_ordered = [url_to_path[u] for u in urls if u in url_to_path]

    n_ok = sum(1 for r in results if r.ok)
    n_fail = sum(1 for r in results if not r.ok)

    return {
        "release": release,
        "dataset": dataset,
        "skim": skim,
        "protocol": protocol,
        "output_dir": os.path.abspath(output_dir),
        "n_requested": len(urls),
        "n_ok": n_ok,
        "n_fail": n_fail,
        "local_paths": local_paths_ordered,
        "results": [r.__dict__ for r in results],  # JSON-friendly
        "raw_urls": urls,
    }


def ensure_atlas_open_data_samples_downloaded(
    *,
    samples: list[dict[str, Any]],
    skim: str = "exactly4lep",
    release: str = "2025e-13tev-beta",
    protocol: str = "https",
    output_dir: str = "./atlas_data",
    max_files_per_sample: int = 0,
    max_files_per_group: int | None = None,
    workers: int = 6,
    verbose: bool = True,
) -> dict[str, Any]:
    """Ensure ATLAS Open Data samples are present locally.

    This preserves HZZ-style sample roles: Data, backgrounds, and signal.
    ``max_files_per_sample`` caps each sample independently; 0 means no cap.
    """
    if max_files_per_group is not None:
        max_files_per_sample = max_files_per_group

    atom.set_release(release)
    os.makedirs(output_dir, exist_ok=True)

    defs: dict[str, dict[str, Any]] = {}
    normalized_samples: list[dict[str, Any]] = []
    for raw_sample in samples:
        if not isinstance(raw_sample, dict):
            continue
        name = str(raw_sample.get("name") or raw_sample.get("label") or raw_sample.get("id") or "").strip()
        if not name:
            continue
        dids = raw_sample.get("dids", [])
        group_def = {"dids": dids}
        if raw_sample.get("color"):
            group_def["color"] = raw_sample["color"]
        defs[name] = group_def
        normalized = dict(raw_sample)
        normalized.setdefault("id", _sample_id(name))
        normalized.setdefault("name", name)
        normalized.setdefault("role", _sample_role(name, normalized))
        normalized_samples.append(normalized)

    dataset_entries = atom.build_dataset(defs, skim=skim, protocol=protocol, cache=True)

    manifest_samples: list[dict[str, Any]] = []
    manifest_files: list[dict[str, Any]] = []
    all_results: list[dict[str, Any]] = []
    raw_urls: list[str] = []
    n_requested = 0
    n_ok = 0
    n_fail = 0

    for sample in normalized_samples:
        sample_id = str(sample["id"])
        name = str(sample["name"])
        role = str(sample["role"])
        cap = int(sample.get("max_files_per_sample", sample.get("max_files_per_group", max_files_per_sample)) or 0)
        urls = sorted(_entry_list(dataset_entries.get(name, {})))
        if cap > 0:
            urls = urls[:cap]

        sample_dir = os.path.join(output_dir, sample_id)
        os.makedirs(sample_dir, exist_ok=True)
        if verbose:
            print(f"[ensure-sample] {name} role={role} files={len(urls)} output_dir={os.path.abspath(sample_dir)}")

        ordered_results = _ensure_sample_files(urls, sample_dir, workers=workers, verbose=verbose)
        raw_urls.extend(urls)
        n_requested += len(urls)
        group_ok = sum(1 for result in ordered_results if result.ok)
        group_fail = sum(1 for result in ordered_results if not result.ok)
        n_ok += group_ok
        n_fail += group_fail
        all_results.extend({**result.__dict__, "sample_id": sample_id, "sample_name": name} for result in ordered_results)

        manifest_samples.append(
            {
                "id": sample_id,
                "name": name,
                "role": role,
                "dids": sample.get("dids", []),
                "color": sample.get("color"),
                "max_files_per_sample": cap,
                "n_requested": len(urls),
                "n_ok": group_ok,
                "n_fail": group_fail,
                "output_dir": os.path.abspath(sample_dir),
            }
        )
        for result in ordered_results:
            if not result.ok:
                continue
            did = _extract_did(result.url, sample)
            is_data = role == "data"
            entry = {
                "logical_name": os.path.basename(result.local_path),
                "path": result.local_path,
                "size_bytes": result.local_size,
                "format": "root",
                "source": result.url,
                "sample_id": sample_id,
                "sample_name": name,
                "sample_role": role,
                "did": did,
                "is_data": is_data,
                "is_mc": not is_data,
                "weight_policy": "unweighted" if is_data else "lumi_normalized_efficiency_weighted_mc",
                "metadata": {"dids": sample.get("dids", [])},
            }
            manifest_files.append(entry)

    input_manifest = {
        "release": release,
        "skim": skim,
        "protocol": protocol,
        "samples": manifest_samples,
        "files": manifest_files,
        "read_only_for_solver": True,
        "manifest_kind": "multi_sample",
    }

    return {
        "release": release,
        "skim": skim,
        "protocol": protocol,
        "output_dir": os.path.abspath(output_dir),
        "n_requested": n_requested,
        "n_ok": n_ok,
        "n_fail": n_fail,
        "n_samples": len(manifest_samples),
        "samples": manifest_samples,
        "local_paths": [entry["path"] for entry in manifest_files],
        "results": all_results,
        "raw_urls": raw_urls,
        "input_manifest": input_manifest,
    }


def ensure_atlas_open_data_sample_groups_downloaded(
    *,
    sample_groups: list[dict[str, Any]],
    **kwargs: Any,
) -> dict[str, Any]:
    """Backward-compatible alias for older callers that used sample_groups."""

    return ensure_atlas_open_data_samples_downloaded(samples=sample_groups, **kwargs)
