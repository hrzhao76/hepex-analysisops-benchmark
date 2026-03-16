# tests/test_contract_validator.py
"""
Unit tests for contract_validator.
No network, LLM, or Docker required.

NOTE: contract_validator is for public-safe validation only and is not
intended to replace private rubric-based scoring.
"""
import sys
import pytest

sys.path.insert(0, "src")

from engine.contract_validator import validate_contract, _check_required_keys


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeTask:
    def __init__(self, spec_dir: str, task_id: str = "t001_zpeak_fit", task_type: str = "zpeak_fit"):
        self.spec_dir = spec_dir
        self.id = task_id
        self.type = task_type


VALID_TRACE = {
    "task_id": "t001_zpeak_fit",
    "status": "ok",
    "fit_result": {
        "mu": 91.18,
        "sigma": 2.5,
        "gof": {
            "p_value": 0.42,
            "chi2_ndof": 1.1,
        },
    },
    "fit_method": {
        "model": "gaussian",
        "fit_range": [70, 110],
        "binned_or_unbinned": "binned",
        "optimizer": "scipy.curve_fit",
        "initial_params": {"mu0": 91.2, "sigma0": 2.5, "A": 1000},
        "uncertainties_method": "covariance",
    },
    "comments": "Fit converged cleanly.",
}


# ---------------------------------------------------------------------------
# _check_required_keys unit tests
# ---------------------------------------------------------------------------

def test_check_keys_passes_on_valid_flat_dict():
    schema = {"a": None, "b": None}
    errs = _check_required_keys({"a": 1, "b": 2, "c": 3}, schema, "")
    assert errs == []


def test_check_keys_reports_missing_key():
    schema = {"a": None, "b": None}
    errs = _check_required_keys({"a": 1}, schema, "")
    assert any("b" in e for e in errs)


def test_check_keys_nested_object():
    schema = {
        "fit_result": {
            "type": "object",
            "required_keys": {"mu": None, "sigma": None},
        }
    }
    errs = _check_required_keys({"fit_result": {"mu": 91.2}}, schema, "")
    assert any("sigma" in e for e in errs)


def test_check_keys_fully_nested_valid():
    schema = {
        "fit_result": {
            "type": "object",
            "required_keys": {
                "mu": None,
                "sigma": None,
                "gof": {
                    "type": "object",
                    "required_keys": {"p_value": None, "chi2_ndof": None},
                },
            },
        }
    }
    errs = _check_required_keys(VALID_TRACE, schema, "")
    assert errs == []


def test_check_keys_non_dict_obj():
    errs = _check_required_keys("not a dict", {"a": None}, "root")
    assert len(errs) == 1
    assert "expected object" in errs[0]


# ---------------------------------------------------------------------------
# validate_contract integration tests (uses real submission_contract.yaml)
# ---------------------------------------------------------------------------

REAL_CONTRACT_DIR = "tasks_public/t001_zpeak_fit"


def test_validate_contract_valid_trace():
    task = FakeTask(spec_dir=REAL_CONTRACT_DIR)
    report = validate_contract(task, VALID_TRACE)

    assert report["status"] == "ok", f"Expected ok, got: {report}"
    assert report["hard_checks_passed"] is True
    assert report["schema_errors"] == []
    assert report["final"]["total_score"] == 1.0
    assert report["final"]["normalized_score"] == 1.0


def test_validate_contract_missing_fit_result():
    task = FakeTask(spec_dir=REAL_CONTRACT_DIR)
    trace = {k: v for k, v in VALID_TRACE.items() if k != "fit_result"}
    report = validate_contract(task, trace)

    assert report["hard_checks_passed"] is False
    assert any("fit_result" in e for e in report["schema_errors"])


def test_validate_contract_missing_status():
    task = FakeTask(spec_dir=REAL_CONTRACT_DIR)
    trace = {k: v for k, v in VALID_TRACE.items() if k != "status"}
    report = validate_contract(task, trace)

    assert report["hard_checks_passed"] is False
    assert any("status" in e for e in report["schema_errors"])


def test_validate_contract_missing_gof_subkey():
    task = FakeTask(spec_dir=REAL_CONTRACT_DIR)
    trace_bad = {
        **VALID_TRACE,
        "fit_result": {
            "mu": 91.2,
            "sigma": 2.5,
            "gof": {"p_value": 0.3},  # chi2_ndof missing
        },
    }
    report = validate_contract(task, trace_bad)

    assert report["hard_checks_passed"] is False
    assert any("chi2_ndof" in e for e in report["schema_errors"])


def test_validate_contract_no_spec_dir():
    class NoSpecDir:
        id = "t001_zpeak_fit"
        type = "zpeak_fit"
        spec_dir = None

    report = validate_contract(NoSpecDir(), VALID_TRACE)
    assert report["status"] == "error"
    assert "spec_dir" in report["error"]


def test_validate_contract_report_has_final_fields():
    task = FakeTask(spec_dir=REAL_CONTRACT_DIR)
    report = validate_contract(task, VALID_TRACE)

    final = report.get("final", {})
    for key in ("total_score", "max_score", "normalized_score"):
        assert key in final, f"final.{key} missing"
    assert 0.0 <= final["normalized_score"] <= 1.0
