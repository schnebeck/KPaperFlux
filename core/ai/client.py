"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/ai/client.py
Version:        2.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Technical client for Google Gemini API interaction.
                Handles rate limiting, adaptive retries, and model metadata.
------------------------------------------------------------------------------
"""

import datetime
import random
import time
from typing import Any, List, Optional, Set, Tuple

from google import genai
from google.genai import types


class AIClient:
    """
    Low-level Gemini API client with robust error handling and rate limit management.
    """

    MAX_RETRIES: int = 5
    _cooldown_until: Optional[datetime.datetime] = None  # Shared cooldown state
    _adaptive_delay: float = 0.0  # Adaptive delay in seconds

    def __init__(self, api_key: str, model_name: str = "gemini-2.0-flash") -> None:
        """
        Initializes the AI client.

        Args:
            api_key: The Google GenAI API key.
            model_name: The target Gemini model name.
        """
        self.api_key: str = api_key
        self.model_name: str = model_name
        self.client: Optional[genai.Client] = None
        self.max_output_tokens: int = 65536

        if not self.api_key:
            print("[AIClient] Warning: Missing API key. Client will be inactive.")
        else:
            try:
                self.client = genai.Client(api_key=self.api_key)
                self._fetch_model_limits()
            except Exception as e:
                print(f"[AIClient] Error: Failed to initialize Gemini Client: {e}")
                self.client = None

    def _fetch_model_limits(self) -> None:
        """
        Queries the API for model limits and applies safety overrides.
        """
        if not self.client:
            return
        try:
            m = self.client.models.get(model=self.model_name)
            self.max_output_tokens = getattr(m, "output_token_limit", 8192)

            # Safety Override for Flash Models
            if "flash" in self.model_name.lower() and self.max_output_tokens < 65536:
                self.max_output_tokens = 65536
        except Exception as e:
            print(f"[AIClient] Warning: Could not fetch limits for {self.model_name}: {e}. Falling back to 64k.")
            self.max_output_tokens = 65536

    def list_models(self) -> List[str]:
        """
        Fetches available models supporting text generation.

        Returns:
            A sorted list of available model names.
        """
        if not self.client:
            return []
        models = []
        try:
            for m in self.client.models.list():
                if hasattr(m, "supported_actions") and "generateContent" in m.supported_actions:
                    name = m.name
                    if name.startswith("models/"):
                        name = name[7:]
                    models.append(name)
        except Exception as e:
            print(f"[AIClient] Error listing models: {e}")
        return sorted(models)

    def generate(self, contents: Any) -> Optional[Any]:
        """
        Executes content generation with robust 429 handling and adaptive delay.

        Args:
            contents: The contents to send (list or dict with config).

        Returns:
            The response object or None if all retries fail.
        """
        if not self.client:
            return None

        if type(self)._adaptive_delay > 0:
            time.sleep(type(self)._adaptive_delay)

        last_error = None
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

                # Success: Decrease adaptive delay
                if type(self)._adaptive_delay > 0:
                    type(self)._adaptive_delay = max(0.0, type(self)._adaptive_delay * 0.5)
                    if type(self)._adaptive_delay < 0.1:
                        type(self)._adaptive_delay = 0.0

                return response

            except Exception as e:
                last_error = e
                if self._is_rate_limit_error(e):
                    self._handle_rate_limit(attempt)
                    continue
                else:
                    print(f"[AIClient] Attempt {attempt+1} failed: {e}")
                    time.sleep(1)

        print(f"[AIClient] ABORT: Operation failed after {self.MAX_RETRIES} attempts. Last error: {last_error}")
        return None

    def generate_json(self, prompt: str, stage_label: str = "AI REQUEST", images: Optional[Any] = None) -> Optional[Any]:
        """
        High-level helper that handles API retries, logical JSON retries, and heuristic repair.
        
        Args:
            prompt: Proposals to the model.
            stage_label: Context label for logging.
            images: Optional vision data.
            
        Returns:
            Parsed JSON (dict/list) or None.
        """
        max_logical_retries = 3
        current_attempt = 1
        working_prompt = prompt

        while current_attempt <= max_logical_retries:
            res_json, error_msg = self._generate_json_raw(working_prompt, stage_label, images)
            if res_json is not None:
                return res_json

            print(f"[AIClient] Logical Retry {current_attempt}/{max_logical_retries} for {stage_label} due to: {error_msg}")
            
            # Strengthen prompt for retry
            working_prompt = prompt + f"\n\n### PREVIOUS ATTEMPT FAILED WITH ERROR:\n{error_msg}\n\nPLEASE FIX THE JSON STRUCTURE! Ensure all braces are closed, no trailing commas, and strictly follow the schema."
            
            current_attempt += 1
            time.sleep(1)

        return None

    def _generate_json_raw(self, prompt: str, stage_label: str = "AI REQUEST", images=None) -> Tuple[Optional[Any], Optional[str]]:
        """Internal helper to call Gemini and perform repair-based parsing."""
        import json
        import re

        contents = [prompt]
        if images:
            if isinstance(contents, list):
                contents.extend(images) if isinstance(images, list) else contents.append(images)
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

        response = self.generate(full_payload)
        if not response or not response.candidates:
            return None, "No response from API"

        candidate = response.candidates[0]
        is_truncated = candidate.finish_reason == "MAX_TOKENS"
        if is_truncated:
            print(f"⚠️ [AIClient] WARNING: Response for {stage_label} was TRUNCATED!")

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
                 print(f"[AIClient] Note: Repaired truncated JSON for {stage_label}, but data might be incomplete.")
            return res_json, None
            
        return None, "JSON parsing failed"

    def _is_rate_limit_error(self, e: Exception) -> bool:
        """Checks if the exception is a rate limit (429) error."""
        if hasattr(e, "code") and e.code == 429:
            return True
        if hasattr(e, "status") and "RESOURCE_EXHAUSTED" in str(e.status):
            return True
        return "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)

    def _handle_rate_limit(self, attempt: int) -> None:
        """Adjusts adaptive delay and cooldown based on rate limit encounter."""
        new_delay = max(2.0, type(self)._adaptive_delay * 2.0)
        type(self)._adaptive_delay = min(256.0, new_delay)

        backoff = 2 * (2 ** attempt) + random.uniform(0, 1)
        delay = max(backoff, type(self)._adaptive_delay)
        print(f"[AIClient] Rate Limit Hit. Backing off for {delay:.1f}s (New Delay: {type(self)._adaptive_delay:.1f}s)")
        
        type(self)._cooldown_until = datetime.datetime.now() + datetime.timedelta(seconds=delay)

    def _wait_for_cooldown(self) -> None:
        """Waits if a cooldown period is active."""
        if type(self)._cooldown_until:
            now = datetime.datetime.now()
            if type(self)._cooldown_until > now:
                wait_time = (type(self)._cooldown_until - now).total_seconds()
                if wait_time > 0:
                    print(f"[AIClient] Cooldown active. Waiting {wait_time:.1f}s...")
                    time.sleep(wait_time)
            type(self)._cooldown_until = None

    @classmethod
    def get_adaptive_delay(cls) -> float:
        """Returns the current adaptive delay."""
        return cls._adaptive_delay
