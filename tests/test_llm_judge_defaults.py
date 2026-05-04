from engine.llm_judge import DEFAULT_OPENAI_JUDGE_MODEL, OpenAIJudge, configured_judge_metadata, get_judge


def test_get_judge_defaults_to_openai(monkeypatch):
    monkeypatch.delenv("HEPEX_JUDGE_PROVIDER", raising=False)
    monkeypatch.delenv("HEPEX_OPENAI_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    judge = get_judge()

    assert isinstance(judge, OpenAIJudge)
    assert judge.model == DEFAULT_OPENAI_JUDGE_MODEL


def test_configured_judge_metadata_reports_default_gpt5(monkeypatch):
    monkeypatch.delenv("HEPEX_JUDGE_PROVIDER", raising=False)
    monkeypatch.delenv("HEPEX_OPENAI_MODEL", raising=False)

    metadata = configured_judge_metadata()

    assert metadata == {"provider": "openai", "model": "gpt-5"}
