import json
import re
import logging
from typing import Optional, Dict, Any, Type, TypeVar, AsyncGenerator
import httpx
from pydantic import BaseModel
from app.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

try:
    import json_repair
except ImportError:
    json_repair = None

def extract_json_from_response(text: str) -> Dict[str, Any]:
    """Extracts JSON dictionary or list from LLM output, handling markdown code blocks, raw JSON, and slightly malformed LLM syntax."""
    cleaned = text.strip()
    
    # 1. Check for markdown code blocks ```json ... ```
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if json_match:
        cleaned_block = json_match.group(1).strip()
        try:
            return json.loads(cleaned_block)
        except Exception:
            if json_repair:
                try:
                    res = json_repair.loads(cleaned_block)
                    if isinstance(res, (dict, list)):
                        return res
                except Exception:
                    pass

    # 2. Try direct json.loads
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    # 3. Try json_repair on full text
    if json_repair:
        try:
            res = json_repair.loads(cleaned)
            if isinstance(res, (dict, list)):
                return res
        except Exception:
            pass

    # 4. Find the outermost { ... } or [ ... ]
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        snippet = cleaned[first_brace:last_brace + 1]
        try:
            return json.loads(snippet)
        except Exception:
            if json_repair:
                try:
                    res = json_repair.loads(snippet)
                    if isinstance(res, (dict, list)):
                        return res
                except Exception:
                    pass

    first_bracket = cleaned.find("[")
    last_bracket = cleaned.rfind("]")
    if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
        snippet = cleaned[first_bracket:last_bracket + 1]
        try:
            return json.loads(snippet)
        except Exception:
            if json_repair:
                try:
                    res = json_repair.loads(snippet)
                    if isinstance(res, (dict, list)):
                        return res
                except Exception:
                    pass

    logger.error(f"Failed to parse valid JSON from LLM text:\n{text}")
    raise ValueError(f"Failed to parse valid JSON from text: {text[:200]}...")


class LLMClient:
    def __init__(self):
        self.provider = settings.LLM_PROVIDER
        self.ollama_base_url = settings.OLLAMA_BASE_URL
        self.ollama_model = settings.OLLAMA_MODEL
        self.gemini_api_key = settings.GEMINI_API_KEY
        self.openai_api_key = settings.OPENAI_API_KEY

    async def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate unstructured text from selected LLM provider."""
        if self.provider == "gemini" and self.gemini_api_key:
            return await self._generate_gemini(prompt, system_prompt)
        elif self.provider == "openai" and self.openai_api_key:
            return await self._generate_openai(prompt, system_prompt)
        elif self.provider == "lmstudio":
            return await self._generate_openai_compatible(
                base_url=settings.LMSTUDIO_BASE_URL,
                model=settings.LMSTUDIO_MODEL,
                prompt=prompt,
                system_prompt=system_prompt
            )
        else:
            return await self._generate_ollama(prompt, system_prompt)

    async def generate_json(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Generate structured JSON response."""
        json_sys_prompt = (
            (system_prompt or "") + 
            "\nIMPORTANT: Respond ONLY with a valid JSON object. Do not include extra conversational text or markdown formatting outside the JSON."
        )
        raw_text = await self.generate_text(prompt, json_sys_prompt)
        return extract_json_from_response(raw_text)

    async def _generate_ollama(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Call local Ollama server."""
        url = f"{self.ollama_base_url}/api/chat"
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.ollama_model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_ctx": 8192
            }
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("message", {}).get("content", "")
                else:
                    raise RuntimeError(f"Ollama returned error status {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.error(f"Error calling Ollama: {e}")
            raise

    async def _generate_gemini(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Call Google Gemini API."""
        from google import genai
        client = genai.Client(api_key=self.gemini_api_key)
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=full_prompt,
        )
        return response.text

    async def _generate_openai(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Call OpenAI API."""
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=self.openai_api_key)
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.1
        )
        return response.choices[0].message.content or ""

    async def _generate_openai_compatible(self, base_url: str, model: str = "local-model", prompt: str = "", system_prompt: Optional[str] = None) -> str:
        """Call LM Studio or other local OpenAI-compatible server."""
        from openai import AsyncOpenAI
        client = AsyncOpenAI(base_url=base_url, api_key="not-needed")
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await client.chat.completions.create(
            model=model or "local-model",
            messages=messages,
            temperature=0.1,
            max_tokens=4096
        )
        return response.choices[0].message.content or ""
