import os
import urllib.request
import atlasopenmagic as atom

# -----------------------------
# Helper: atlasopenmagic download
# -----------------------------
def _get_local_paths_from_atlasopenmagic_urls(urls: list[str]) -> list[str]:
    """
    atlasopenmagic get_urls sometimes returns strings like:
      "https::/path/to/local/file.root" (based on your earlier snippet using split('::')[1])
    This helper extracts the local path part robustly.
    """
    local_paths: list[str] = []
    for u in urls:
        if "::" in u:
            local_paths.append(u.split("::", 1)[1])
        else:
            # Fallback: keep as-is (could already be local)
            local_paths.append(u)
    return local_paths


def ensure_data_downloaded(cfg: GreenConfig, task: ZPeakTaskSpec) -> dict[str, Any]:
    """
    Download (cache) files using atlasopenmagic, return metadata for later steps.
    """
    import atlasopenmagic as atom  # installed per user

    atom.set_release(cfg.release)

    # cache=True makes files copied locally rather than streamed.
    urls = atom.get_urls(task.dataset, task.skim, protocol=task.protocol, cache=task.cache)

    urls_sorted = sorted(urls)
    if task.max_files and task.max_files > 0:
        urls_sorted = urls_sorted[: task.max_files]

    local_paths = _get_local_paths_from_atlasopenmagic_urls(urls_sorted)

    return {
        "release": cfg.release,
        "dataset": task.dataset,
        "skim": task.skim,
        "protocol": task.protocol,
        "cache": task.cache,
        "n_files": len(local_paths),
        "local_paths": local_paths,
        # keep raw urls too in case you want to debug
        "raw_urls": urls_sorted,
    }


def download_atlas_open_data(
    skim: str = "2muons",
    release: str = "2025e-13tev-beta",
    output_dir: str = "./atlas_data",
    verbose: bool = True,
):
    """
    Download ATLAS Open Data files using urllib.request.

    Parameters
    ----------
    skim : str
        Skim name, e.g. "2muons"
    release : str
        ATLAS Open Data release tag
    output_dir : str
        Local directory to store downloaded files
    verbose : bool
        Whether to print download progress

    Returns
    -------
    list[str]
        List of local file paths
    """

    # Set release
    atom.set_release(release)

    # Get URLs (do NOT cache via atlasopenmagic)
    files_list = atom.get_urls(
        "data",
        skim,
        protocol="https",
        cache=False,
    )

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    local_files = []

    for file_entry in sorted(files_list):
        # atlasopenmagic returns strings like:
        #   "root::https://.../file.root"
        url = file_entry.split("::", 1)[1]
        filename = os.path.basename(url)
        local_path = os.path.join(output_dir, filename)

        if verbose:
            print(f"Downloading {filename}")

        urllib.request.urlretrieve(url, local_path)
        local_files.append(local_path)

    return local_files
