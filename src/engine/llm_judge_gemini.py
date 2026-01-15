# src/engine/llm_judge_gemini.py
from __future__ import annotations
import os
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from google import genai
from google.genai import types  # google-genai 

from .prompt_render import render_judge_prompt


@dataclass
class LLMJudgeResult:
    ok: bool
    raw_text: str
    parsed: Optional[Dict[str, Any]]
    error: str


class GeminiJudge:
    """
    Minimal Gemini judge.
    Env:
      - GEMINI_API_KEY  (Gemini Developer API)
      - HEPEX_GEMINI_MODEL (optional) e.g. "gemini-2.5-flash"
    """
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("Missing GEMINI_API_KEY or GOOGLE_API_KEY")
        self.client = genai.Client(api_key=api_key)
        self.model = model or os.getenv("HEPEX_GEMINI_MODEL", "gemini-2.5-flash")

    def _generate_with_retry(self, prompt: str, config: types.GenerateContentConfig, retries: int = 5) -> str:
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
                # Check for 429 in various forms
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

        template = spec["judge_prompt"]  # already loaded text
        prompt = render_judge_prompt(
            template,
            rubric=rubric,
            eval_ref=eval_ref,
            trace=trace,
            rule_signals=rule_signals,
            rule_issues=rule_issues,
        )

        # Try JSON mode (best effort). If provider rejects, we still parse from text.
        try:
            text = self._generate_with_retry(
                prompt,
                types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type="application/json",
                )
            )
        except Exception:
            # fallback: no mime type, still ask prompt to return JSON
            try:
                text = self._generate_with_retry(
                    prompt, 
                    types.GenerateContentConfig(temperature=0.0)
                )
            except Exception as e2:
                return LLMJudgeResult(False, "", None, f"Gemini call failed: {type(e2).__name__}: {e2}")

        # parse JSON - handle markdown code blocks
        import re
        def extract_json(txt: str) -> str:
            # Match ```json...``` or ```...``` blocks
            match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', txt)
            if match:
                return match.group(1).strip()
            # Try to find raw JSON object
            obj_match = re.search(r'(\{[\s\S]*\})', txt)
            if obj_match:
                return obj_match.group(1)
            return txt
        
        try:
            json_text = extract_json(text)
            obj = json.loads(json_text)
            if not isinstance(obj, dict):
                return LLMJudgeResult(False, text, None, "LLM output is not a JSON object")
            return LLMJudgeResult(True, text, obj, "")
        except Exception as e:
            return LLMJudgeResult(False, text, None, f"JSON parse failed: {type(e).__name__}: {e}")
