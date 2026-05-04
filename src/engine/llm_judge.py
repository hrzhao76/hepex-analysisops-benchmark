# src/engine/llm_judge.py
from __future__ import annotations

import os
import json
import re
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from .prompt_render import render_judge_prompt

DEFAULT_JUDGE_PROVIDER = "openai"
DEFAULT_OPENAI_JUDGE_MODEL = "gpt-5"
DEFAULT_GEMINI_JUDGE_MODEL = "gemini-2.5-flash"
DEFAULT_OLLAMA_JUDGE_MODEL = "gpt-oss"
DEFAULT_ANTHROPIC_JUDGE_MODEL = "claude-3-5-sonnet-20241022"

@dataclass
class LLMJudgeResult:
    ok: bool
    raw_text: str
    parsed: Optional[Dict[str, Any]]
    error: str

class BaseJudge:
    def judge(self, spec: Dict[str, Any], trace: Dict[str, Any], rule_signals: Dict[str, Any], rule_issues: list[dict[str, Any]]) -> LLMJudgeResult:
        raise NotImplementedError("Subclasses must implement judge()")

    def _extract_json(self, txt: str) -> str:
        """Helper to extract JSON from text, handling markdown blocks."""
        match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', txt)
        if match:
            return match.group(1).strip()
        obj_match = re.search(r'(\{[\s\S]*\})', txt)
        if obj_match:
            return obj_match.group(1)
        return txt


def configured_judge_metadata(env_overrides: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Return configured judge provider/model without requiring API credentials."""
    env = dict(os.environ)
    if env_overrides:
        env.update(env_overrides)
    provider = env.get("HEPEX_JUDGE_PROVIDER", DEFAULT_JUDGE_PROVIDER).lower()
    if provider == "gemini":
        model = env.get("HEPEX_GEMINI_MODEL", DEFAULT_GEMINI_JUDGE_MODEL)
    elif provider == "ollama":
        model = env.get("HEPEX_OLLAMA_MODEL", DEFAULT_OLLAMA_JUDGE_MODEL)
    elif provider == "anthropic":
        model = env.get("HEPEX_ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_JUDGE_MODEL)
    else:
        model = env.get("HEPEX_OPENAI_MODEL", DEFAULT_OPENAI_JUDGE_MODEL)
    return {"provider": provider, "model": model}


def judge_runtime_metadata(
    judge: Optional[BaseJudge],
    *,
    configured: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    metadata = {
        "configured": configured or configured_judge_metadata(),
        "runtime": {
            "available": judge is not None,
        },
    }
    if judge is not None:
        metadata["runtime"].update(
            {
                "provider": getattr(judge, "provider", judge.__class__.__name__),
                "model": getattr(judge, "model", None),
            }
        )
    return metadata

class GeminiJudge(BaseJudge):
    provider = "gemini"
    """
    Minimal Gemini judge.
    Env:
      - GOOGLE_API_KEY  (Gemini Developer API; non-default provider)
      - HEPEX_GEMINI_MODEL (optional) e.g. "gemini-2.5-flash"
    """
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("Missing GOOGLE_API_KEY")
            
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise RuntimeError("The 'google-genai' python package is required for GeminiJudge")
            
        self.client = genai.Client(api_key=api_key)
        self.genai_types = types
        self.model = model or os.getenv("HEPEX_GEMINI_MODEL", DEFAULT_GEMINI_JUDGE_MODEL)

    def _generate_with_retry(self, prompt: str, config: Any, retries: int = 5) -> str:
        import time
        from google.genai import errors as genai_errors
        
        delay = 2.0
        last_exception = None
        
        for i in range(retries):
            try:
                resp = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config,
                )
                return (resp.text or "").strip()
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    print(f"Gemini API rate limit (429). Retrying {i+1}/{retries} in {delay}s...")
                    time.sleep(delay)
                    delay = min(delay * 2, 30.0)
                    last_exception = e
                else:
                    raise e
                    
        raise last_exception or RuntimeError("Gemini retry failed")

    def judge(self, spec: Dict[str, Any], trace: Dict[str, Any], rule_signals: Dict[str, Any], rule_issues: list[dict[str, Any]]) -> LLMJudgeResult:
        rubric = spec["rubric"]
        eval_ref = spec.get("eval_ref", {}) or {}

        template = spec["judge_prompt"]
        prompt = render_judge_prompt(
            template,
            rubric=rubric,
            eval_ref=eval_ref,
            trace=trace,
            rule_signals=rule_signals,
            rule_issues=rule_issues,
        )

        try:
            text = self._generate_with_retry(
                prompt,
                self.genai_types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type="application/json",
                )
            )
        except Exception:
            try:
                text = self._generate_with_retry(
                    prompt, 
                    self.genai_types.GenerateContentConfig(temperature=0.0)
                )
            except Exception as e2:
                return LLMJudgeResult(False, "", None, f"Gemini call failed: {type(e2).__name__}: {e2}")
        
        try:
            json_text = self._extract_json(text)
            obj = json.loads(json_text)
            if not isinstance(obj, dict):
                return LLMJudgeResult(False, text, None, "LLM output is not a JSON object")
            return LLMJudgeResult(True, text, obj, "")
        except Exception as e:
            return LLMJudgeResult(False, text, None, f"JSON parse failed: {type(e).__name__}: {e}")

class OllamaJudge(BaseJudge):
    provider = "ollama"

    def __init__(self, host: Optional[str] = None, model: Optional[str] = None):
        self.host = (host or os.getenv("OLLAMA_HOST", "http://localhost:11434")).rstrip("/")
        self.model = model or os.getenv("HEPEX_OLLAMA_MODEL", DEFAULT_OLLAMA_JUDGE_MODEL)
        self.endpoint = f"{self.host}/api/generate"

    def _generate(self, prompt: str) -> str:
        data = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.0
            }
        }
        
        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                result = json.loads(response.read().decode("utf-8"))
                return result.get("response", "").strip()
        except urllib.error.URLError as e:
            raise RuntimeError(f"Ollama connection failed: {e}")

    def judge(self, spec: Dict[str, Any], trace: Dict[str, Any], rule_signals: Dict[str, Any], rule_issues: list[dict[str, Any]]) -> LLMJudgeResult:
        rubric = spec["rubric"]
        eval_ref = spec.get("eval_ref", {}) or {}

        template = spec["judge_prompt"]
        prompt = render_judge_prompt(
            template,
            rubric=rubric,
            eval_ref=eval_ref,
            trace=trace,
            rule_signals=rule_signals,
            rule_issues=rule_issues,
        )

        try:
            text = self._generate(prompt)
        except Exception as e:
            return LLMJudgeResult(False, "", None, f"Ollama call failed: {type(e).__name__}: {e}")

        try:
            json_text = self._extract_json(text)
            obj = json.loads(json_text)
            if not isinstance(obj, dict):
                return LLMJudgeResult(False, text, None, "LLM output is not a JSON object")
            return LLMJudgeResult(True, text, obj, "")
        except Exception as e:
            return LLMJudgeResult(False, text, None, f"JSON parse failed: {type(e).__name__}: {e}")

class OpenAIJudge(BaseJudge):
    provider = "openai"

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("Missing OPENAI_API_KEY")
            
        try:
            from openai import OpenAI
        except ImportError:
            raise RuntimeError("The 'openai' python package is required for OpenAIJudge")
            
        self.client = OpenAI(api_key=self.api_key)
        self.model = model or os.getenv("HEPEX_OPENAI_MODEL", DEFAULT_OPENAI_JUDGE_MODEL)

    def _generate(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return (response.choices[0].message.content or "").strip()

    def judge(self, spec: Dict[str, Any], trace: Dict[str, Any], rule_signals: Dict[str, Any], rule_issues: list[dict[str, Any]]) -> LLMJudgeResult:
        rubric = spec["rubric"]
        eval_ref = spec.get("eval_ref", {}) or {}

        template = spec["judge_prompt"]
        prompt = render_judge_prompt(
            template,
            rubric=rubric,
            eval_ref=eval_ref,
            trace=trace,
            rule_signals=rule_signals,
            rule_issues=rule_issues,
        )

        try:
            text = self._generate(prompt)
        except Exception as e:
            return LLMJudgeResult(False, "", None, f"OpenAI call failed: {type(e).__name__}: {e}")

        try:
            json_text = self._extract_json(text)
            obj = json.loads(json_text)
            if not isinstance(obj, dict):
                return LLMJudgeResult(False, text, None, "LLM output is not a JSON object")
            return LLMJudgeResult(True, text, obj, "")
        except Exception as e:
            return LLMJudgeResult(False, text, None, f"JSON parse failed: {type(e).__name__}: {e}")

class AnthropicJudge(BaseJudge):
    provider = "anthropic"

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise RuntimeError("Missing ANTHROPIC_API_KEY")
            
        try:
            from anthropic import Anthropic
        except ImportError:
            raise RuntimeError("The 'anthropic' python package is required for AnthropicJudge")
            
        self.client = Anthropic(api_key=self.api_key)
        self.model = model or os.getenv("HEPEX_ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_JUDGE_MODEL)

    def _generate(self, prompt: str) -> str:
        system_prompt = "You are an automated grading judge. Please return only a valid JSON object."
        
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            temperature=0.0,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}]
        )
        return (response.content[0].text or "").strip()

    def judge(self, spec: Dict[str, Any], trace: Dict[str, Any], rule_signals: Dict[str, Any], rule_issues: list[dict[str, Any]]) -> LLMJudgeResult:
        rubric = spec["rubric"]
        eval_ref = spec.get("eval_ref", {}) or {}

        template = spec["judge_prompt"]
        prompt = render_judge_prompt(
            template,
            rubric=rubric,
            eval_ref=eval_ref,
            trace=trace,
            rule_signals=rule_signals,
            rule_issues=rule_issues,
        )

        try:
            text = self._generate(prompt)
        except Exception as e:
            return LLMJudgeResult(False, "", None, f"Anthropic call failed: {type(e).__name__}: {e}")

        try:
            json_text = self._extract_json(text)
            obj = json.loads(json_text)
            if not isinstance(obj, dict):
                return LLMJudgeResult(False, text, None, "LLM output is not a JSON object")
            return LLMJudgeResult(True, text, obj, "")
        except Exception as e:
            return LLMJudgeResult(False, text, None, f"JSON parse failed: {type(e).__name__}: {e}")

def get_judge() -> BaseJudge:
    """Factory to instantiate the correct judge based on HEPEX_JUDGE_PROVIDER."""
    provider = os.getenv("HEPEX_JUDGE_PROVIDER", DEFAULT_JUDGE_PROVIDER).lower()
    
    if provider == "gemini":
        return GeminiJudge()
    elif provider == "ollama":
        return OllamaJudge()
    elif provider == "openai":
        return OpenAIJudge()
    elif provider == "anthropic":
        return AnthropicJudge()
    else:
        raise ValueError(f"Unknown judger provider: {provider}")
