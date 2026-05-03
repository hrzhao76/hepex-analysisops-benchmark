from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import yaml

from engine.input_access import resolve_input_access
from engine.rubric_scorer import score_submission
from tasks.task_spec import GreenConfig
from utils.atlas_download import DownloadResult, ensure_atlas_open_data_samples_downloaded


HZZ_SAMPLES = [
    {"name": "Data", "role": "data", "dids": ["data"]},
    {
        "name": r"Background $Z,t\bar{t},t\bar{t}+V,VVV$",
        "role": "background",
        "dids": [410470, 410155, 410218],
    },
    {"name": r"Background $ZZ^{*}$", "role": "background", "dids": [700600]},
    {"name": r"Signal ($m_H$ = 125 GeV)", "role": "signal", "dids": [345060, 346228]},
]


def write_json(path: Path, payload: object) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_hzz_sample_downloader_uses_build_dataset_and_caps_each_sample(monkeypatch, tmp_path):
    captured_defs = {}

    def fake_set_release(release):
        assert release == "2025e-13tev-beta"

    def fake_build_dataset(defs, *, skim, protocol, cache):
        captured_defs.update(defs)
        assert skim == "exactly4lep"
        assert protocol == "https"
        assert cache is True
        return {
            "Data": {"list": ["root::https://example.test/data_a.root", "root::https://example.test/data_b.root", "root::https://example.test/data_c.root"]},
            r"Background $Z,t\bar{t},t\bar{t}+V,VVV$": {
                "list": [
                    "root::https://example.test/mc_410470_a.root",
                    "root::https://example.test/mc_410155_a.root",
                    "root::https://example.test/mc_410218_a.root",
                ]
            },
            r"Background $ZZ^{*}$": {"list": ["root::https://example.test/mc_700600_a.root"]},
            r"Signal ($m_H$ = 125 GeV)": {
                "list": [
                    "root::https://example.test/mc_345060_a.root",
                    "root::https://example.test/mc_346228_a.root",
                    "root::https://example.test/mc_346310_a.root",
                ]
            },
        }

    def fake_ensure_one_file(url, output_dir, **_kwargs):
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        path = output / Path(url).name
        path.write_text("root", encoding="utf-8")
        return DownloadResult(url=url, local_path=str(path), ok=True, skipped=False, expected_size=None, local_size=4)

    monkeypatch.setattr("utils.atlas_download.atom.set_release", fake_set_release)
    monkeypatch.setattr("utils.atlas_download.atom.build_dataset", fake_build_dataset)
    monkeypatch.setattr("utils.atlas_download._ensure_one_file", fake_ensure_one_file)

    info = ensure_atlas_open_data_samples_downloaded(
        samples=HZZ_SAMPLES,
        skim="exactly4lep",
        release="2025e-13tev-beta",
        protocol="https",
        output_dir=str(tmp_path),
        max_files_per_sample=2,
        workers=2,
        verbose=False,
    )

    assert sorted(captured_defs) == [
        r"Background $Z,t\bar{t},t\bar{t}+V,VVV$",
        r"Background $ZZ^{*}$",
        "Data",
        r"Signal ($m_H$ = 125 GeV)",
    ]
    assert info["n_samples"] == 4
    assert info["n_requested"] == 7
    assert [sample["n_ok"] for sample in info["samples"]] == [2, 2, 1, 2]
    manifest = info["input_manifest"]
    assert {entry["sample_id"] for entry in manifest["files"]} == {
        "data",
        "background_z_ttbar_ttb_vvv",
        "background_zzstar",
        "signal_mh125",
    }
    assert {entry["sample_name"] for entry in manifest["files"]} == {
        "Data",
        r"Background $Z,t\bar{t},t\bar{t}+V,VVV$",
        r"Background $ZZ^{*}$",
        r"Signal ($m_H$ = 125 GeV)",
    }
    assert all("weight_policy" in entry for entry in manifest["files"])


def test_resolve_input_access_preserves_existing_multi_sample_manifest(tmp_path):
    shared_dir = tmp_path / "shared"
    shared_dir.mkdir()
    manifest_path = shared_dir / "input_manifest.json"
    manifest = {
        "task_id": "t005_hzz4l_l1",
        "samples": [{"id": "data", "name": "Data", "role": "data", "dids": ["data"]}],
        "files": [
            {
                "logical_name": "data.root",
                "path": str(shared_dir / "data" / "data.root"),
                "sample_id": "data",
                "sample_name": "Data",
                "sample_role": "data",
                "did": "data",
                "is_data": True,
                "is_mc": False,
                "weight_policy": "unweighted",
            }
        ],
        "sentinel": "do-not-overwrite",
    }
    write_json(manifest_path, manifest)
    task = SimpleNamespace(
        id="t005_hzz4l_l1",
        type="hzz4l_l1",
        level="l1",
        release="2025e-13tev-beta",
        dataset="data",
        skim="exactly4lep",
        protocol="https",
        requires_large_input_data=True,
        supports_local_shared_input=True,
        supports_scenario_shared_input=True,
        input_requirements={"samples": HZZ_SAMPLES},
        max_files=5,
    )
    cfg = GreenConfig(
        input_access_mode="local_shared_mount",
        shared_input_dir=str(shared_dir),
        input_manifest_path=str(manifest_path),
    )

    resolved = resolve_input_access(task, cfg)

    assert resolved == manifest
    assert "sentinel" in manifest_path.read_text(encoding="utf-8")


def test_hzz_sample_manifest_scorer_rejects_off_manifest_root_refs(tmp_path):
    task_dir = tmp_path / "task"
    submission_dir = tmp_path / "submission"
    task_dir.mkdir()
    submission_dir.mkdir()
    contract = {
        "version": 1,
        "level": "l1",
        "required_outputs": [
            {"name": "submission_trace", "canonical_filename": "submission_trace.json", "type": "json"},
            {"name": "interpretation", "canonical_filename": "interpretation.md", "type": "markdown"},
        ],
        "optional_outputs": [],
        "schemas": {
            "submission_trace.json": {"required_fields": ["input_samples_used"]},
            "interpretation.md": {"constraints": {"non_empty": True}},
        },
    }
    (task_dir / "submission_contract.yaml").write_text(yaml.safe_dump(contract, sort_keys=False), encoding="utf-8")
    manifest_files = []
    for idx, sample in enumerate(HZZ_SAMPLES):
        sample_id = {"Data": "data"}.get(sample["name"], f"sample_{idx}")
        filename = f"{sample_id}.root"
        manifest_files.append(
            {
                "logical_name": filename,
                "path": str(submission_dir / "inputs" / sample_id / filename),
                "source": f"https://example.test/{filename}",
                "sample_id": sample_id,
                "sample_name": sample["name"],
                "sample_role": sample["role"],
                "did": sample["dids"][0],
                "is_data": sample["role"] == "data",
                "is_mc": sample["role"] != "data",
                "weight_policy": "unweighted" if sample["role"] == "data" else "lumi_normalized_efficiency_weighted_mc",
            }
        )
    manifest_samples = [
        {"id": entry["sample_id"], "name": entry["sample_name"], "role": entry["sample_role"], "dids": [entry["did"]]}
        for entry in manifest_files
    ]
    write_json(submission_dir / "input_manifest.json", {"samples": manifest_samples, "files": manifest_files})
    trace = {
        "input_samples_used": [
            {"sample_name": entry["sample_name"], "sample_role": entry["sample_role"], "files_used": [entry["logical_name"]]}
            for entry in manifest_files
        ]
    }
    write_json(submission_dir / "submission_trace.json", trace)
    (submission_dir / "interpretation.md").write_text("HZZ trace fixture.", encoding="utf-8")
    rubric = {
        "version": 1,
        "weights": {"pipeline": 1.0},
        "checks": {
            "pipeline": [
                {
                    "id": "hzz_manifest",
                    "type": "structural",
                    "condition": {
                        "hzz_sample_manifest_coverage": {
                            "required_sample_names": [sample["name"] for sample in HZZ_SAMPLES],
                            "reject_off_manifest_root_refs": True,
                        }
                    },
                    "score": 1.0,
                }
            ]
        },
    }
    task = SimpleNamespace(id="t005_hzz4l_l1", type="hzz4l_l1", level="l1", spec_dir=str(task_dir), submission_contract_path="submission_contract.yaml")

    report = score_submission(task, submission_dir, rubric, {"status": "ok", "hard_checks_passed": True})
    assert report["check_results"][0]["passed"]

    trace["input_samples_used"][0]["files_used"].append("https://example.test/not_in_manifest.root")
    write_json(submission_dir / "submission_trace.json", trace)
    report = score_submission(task, submission_dir, rubric, {"status": "ok", "hard_checks_passed": True})
    assert not report["check_results"][0]["passed"]
    assert report["check_results"][0]["evidence"]["off_manifest_root_refs"] == ["https://example.test/not_in_manifest.root"]
