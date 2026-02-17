
import datetime
import random
import time
import logging
from typing import Any, List, Optional, Set, Tuple

from google import genai
from google.genai import types

from core.ai.base import AIProvider
from core.logger import get_logger, log_ai_interaction

logger = get_logger("ai.gemini")

class GeminiProvider(AIProvider):
    """Low-level Gemini API client (Cloud AI)."""

    MAX_RETRIES: int = 5
    _cooldown_until: Optional[datetime.datetime] = None
    _adaptive_delay: float = 0.0

    def __init__(self, api_key: str, model_name: str = "gemini-2.0-flash") -> None:
        self.api_key: str = api_key
        self.model_name: str = model_name
        self.client: Optional[genai.Client] = None
        self.max_output_tokens: int = 65536

        if not self.api_key:
            logger.warning("Missing API key. Gemini Provider will be inactive.")
        else:
            try:
                self.client = genai.Client(api_key=self.api_key)
                self._fetch_model_limits()
            except Exception as e:
                logger.error(f"Failed to initialize Gemini Client: {e}")
                self.client = None

    def _fetch_model_limits(self) -> None:
        if not self.client: return
        try:
            m = self.client.models.get(model=self.model_name)
            self.max_output_tokens = getattr(m, "output_token_limit", 65536)
            if "flash" in self.model_name.lower() and self.max_output_tokens < 65536:
                self.max_output_tokens = 65536
        except Exception:
            self.max_output_tokens = 65536

    def list_models(self) -> List[str]:
        if not self.client: return []
        models = []
        try:
            for m in self.client.models.list():
                if hasattr(m, "supported_actions") and "generateContent" in m.supported_actions:
                    name = m.name
                    if name.startswith("models/"): name = name[7:]
                    models.append(name)
        except Exception as e:
            logger.error(f"Error listing models: {e}")
        return sorted(models)

    def generate_json(self, prompt: str, stage_label: str = "AI REQUEST", images: Optional[Any] = None) -> Optional[Any]:
        """Gemini specific implementation with repair-based parsing logic."""
        # This contains the complex balance/repair logic from the original client
        max_logical_retries = 3
        current_attempt = 1
        working_prompt = prompt

        while current_attempt <= max_logical_retries:
            res_json, error_msg = self._generate_json_raw(working_prompt, stage_label, images)
            if res_json is not None:
                # High-fidelity logging for technical debugging
                log_ai_interaction(working_prompt, str(res_json), res_json)
                return res_json

            logger.info(f"Logical Retry {current_attempt}/{max_logical_retries} for {stage_label} due to: {error_msg}")
            working_prompt = prompt + f"\n\n### PREVIOUS ATTEMPT FAILED WITH ERROR:\n{error_msg}\n\nPLEASE FIX THE JSON STRUCTURE!"
            current_attempt += 1
            time.sleep(1)
        return None

    def _generate_json_raw(self, prompt: str, stage_label: str = "AI REQUEST", images=None) -> Tuple[Optional[Any], Optional[str]]:
        """Internal helper to call Gemini and perform repair-based parsing."""
        import json
        import re

        if not self.client:
            return None, "Client inactive"

        contents = [prompt]
        if images:
            if isinstance(images, list):
                contents.extend(images)
            else:
                contents.append(images)

        # Force JSON via API
        full_payload = {
            'contents': contents,
            'config': types.GenerateContentConfig(
                response_mime_type='application/json',
                max_output_tokens=self.max_output_tokens,
                temperature=0.1
            )
        }

        response = self._execute_generate(full_payload)
        if not response or not response.candidates:
            return None, "No response from API"

        candidate = response.candidates[0]
        is_truncated = candidate.finish_reason == "MAX_TOKENS"
        if is_truncated:
            logger.warning(f"Response for {stage_label} was TRUNCATED!")

        try:
            txt = response.text
        except Exception as e:
            return None, f"Response text inaccessible: {e}"

        if not txt:
            return None, "Empty response"

        txt = txt.replace("\x00", "") 
        start = txt.find('{')
        if start == -1:
            return None, "No JSON object found (missing '{')"

        def attempt_repair(s: str) -> str:
            """Heuristic JSON repair for common AI mistakes."""
            s = re.sub(r',\s*([\]}])', r'\1', s)  # Remove trailing commas
            s = re.sub(r'}\s*\n\s*"', r'},\n"', s)  # Missing commas between objects
            s = re.sub(r'\]\s*\n\s*"', r'],\n"', s) # Missing commas between arrays and items
            return s

        res_json = None
        current_json = None
        
        # Tiered Parse Attempt
        for step in range(4):
            try:
                if step == 0:
                    # Attempt 0: Find last '}'
                    end = txt.rfind('}')
                    if end == -1: continue
                    current_json = txt[start:end+1]
                elif step == 1:
                    # Attempt 1: Balanced Braces
                    depth = 0
                    balanced_end = -1
                    for idx, char in enumerate(txt[start:]):
                        if char == '{': depth += 1
                        elif char == '}': 
                            depth -= 1
                            if depth == 0:
                                balanced_end = start + idx
                                break
                    if balanced_end != -1:
                        current_json = txt[start:balanced_end+1]
                    else: continue
                elif step == 2:
                    # Attempt 2: Heuristic Repair
                    if not current_json: continue
                    current_json = attempt_repair(current_json)
                elif step == 3:
                    # Attempt 3: Truncated JSON fix
                    if not current_json: continue
                    depth = 0
                    for char in current_json:
                        if char == '{': depth += 1
                        elif char == '}': depth -= 1
                    if depth > 0:
                         current_json += ("}" * depth)
                    else: continue

                if not current_json: continue
                res_json = json.loads(current_json, strict=False)
                break 
            except json.JSONDecodeError:
                if step < 3: continue 
                return None, "JSON Syntax Error after repair attempts"

        if res_json is not None:
            if is_truncated:
                 logger.info(f"Repaired truncated JSON for {stage_label}, but data might be incomplete.")
            return res_json, None
            
        return None, "JSON parsing failed"

    def _execute_generate(self, contents: Any) -> Optional[Any]:
        if not self.client: return None
        if GeminiProvider._adaptive_delay > 0:
            time.sleep(GeminiProvider._adaptive_delay)

        for attempt in range(self.MAX_RETRIES):
            self._wait_for_cooldown()
            try:
                req_config = None
                call_contents = contents
                if isinstance(contents, dict) and "config" in contents:
                    req_config = contents["config"]
                    call_contents = contents["contents"]

                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=call_contents,
                    config=req_config
                )
                if GeminiProvider._adaptive_delay > 0:
                    GeminiProvider._adaptive_delay *= 0.5
                    if GeminiProvider._adaptive_delay < 0.2:
                        GeminiProvider._adaptive_delay = 0.0
                return response
            except Exception as e:
                if self._is_rate_limit_error(e):
                    self._handle_rate_limit(attempt)
                    continue
                time.sleep(1)
        return None

    def _is_rate_limit_error(self, e: Exception) -> bool:
        return hasattr(e, "code") and e.code == 429 or "RESOURCE_EXHAUSTED" in str(e)

    def _handle_rate_limit(self, attempt: int) -> None:
        new_delay = max(2.0, GeminiProvider._adaptive_delay * 2.0)
        GeminiProvider._adaptive_delay = min(256.0, new_delay)
        delay = max(2 * (2 ** attempt) + random.uniform(0, 1), GeminiProvider._adaptive_delay)
        GeminiProvider._cooldown_until = datetime.datetime.now() + datetime.timedelta(seconds=delay)

    def _wait_for_cooldown(self) -> None:
        if GeminiProvider._cooldown_until and GeminiProvider._cooldown_until > datetime.datetime.now():
            wait_time = (GeminiProvider._cooldown_until - datetime.datetime.now()).total_seconds()
            if wait_time > 0: time.sleep(wait_time)
        GeminiProvider._cooldown_until = None

    @classmethod
    def get_adaptive_delay(cls) -> float:
        return GeminiProvider._adaptive_delay
