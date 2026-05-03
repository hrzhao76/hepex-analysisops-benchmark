from __future__ import annotations

from pathlib import Path
import json
from typing import Any, Dict, List

from utils import _safe_write_json, _safe_write_text


class SubmissionBundleError(RuntimeError):
    pass


MAX_BUNDLE_BYTES = 512 * 1024


JSON_PAYLOAD_TYPES = {"json", "table_json", "image_ref"}
TEXT_PAYLOAD_TYPES = {"markdown", "text"}


def declared_artifact_entries(contract: Dict[str, Any]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for section in ("required_outputs", "optional_outputs"):
        for entry in contract.get(section, []) or []:
            if isinstance(entry, dict) and "canonical_filename" in entry:
                entries.append(entry)
    return entries


def expected_artifact_names(contract: Dict[str, Any]) -> List[str]:
    return [
        entry["canonical_filename"]
        for entry in contract.get("required_outputs", []) or []
        if isinstance(entry, dict) and "canonical_filename" in entry
    ]


def declared_artifact_names(contract: Dict[str, Any]) -> List[str]:
    return [entry["canonical_filename"] for entry in declared_artifact_entries(contract)]


def parse_submission_bundle(bundle: Dict[str, Any], contract: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(bundle, dict):
        raise SubmissionBundleError("Submission bundle must be a JSON object.")
    bundle_size = len(json.dumps(bundle, ensure_ascii=False).encode("utf-8"))
    if bundle_size > MAX_BUNDLE_BYTES:
        raise SubmissionBundleError(
            f"Submission bundle is too large ({bundle_size} bytes); submission_bundle_v1 is for small structured outputs only."
        )

    artifacts = bundle.get("artifacts")
    if not isinstance(artifacts, dict):
        raise SubmissionBundleError("submission_bundle_v1 requires an 'artifacts' object.")

    expected = set(expected_artifact_names(contract))
    declared = set(declared_artifact_names(contract))
    unknown = sorted(set(artifacts) - declared)
    if unknown:
        raise SubmissionBundleError(f"Bundle contains unexpected artifact(s): {unknown}")

    missing = sorted(expected - set(artifacts))
    if missing:
        raise SubmissionBundleError(f"Bundle is missing required artifact(s): {missing}")

    return {
        "status": bundle.get("status", "ok"),
        "artifacts": artifacts,
    }


def materialize_submission_bundle(parsed_bundle: Dict[str, Any], contract: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
    artifacts = parsed_bundle["artifacts"]
    manifest_entries: List[Dict[str, Any]] = []
    for entry in declared_artifact_entries(contract):
        name = entry["canonical_filename"]
        if name not in artifacts:
            continue
        art_type = entry.get("type", "json")
        path = output_dir / name
        payload = artifacts[name]
        if art_type in TEXT_PAYLOAD_TYPES:
            if not isinstance(payload, str):
                raise SubmissionBundleError(f"Artifact {name} must be a string for {art_type} output.")
            _safe_write_text(path, payload)
        elif art_type in JSON_PAYLOAD_TYPES:
            if not isinstance(payload, dict):
                raise SubmissionBundleError(f"Artifact {name} must be a JSON object for {art_type} output.")
            _safe_write_json(path, payload)
        else:
            raise SubmissionBundleError(f"Unsupported artifact type for {name}: {art_type}")
        manifest_entries.append(
            {
                "name": entry.get("name", name),
                "canonical_filename": name,
                "type": art_type,
                "path": str(path),
            }
        )

    artifact_manifest = {"artifacts": manifest_entries}
    _safe_write_json(output_dir / "artifact_manifest.json", artifact_manifest)
    return artifact_manifest
