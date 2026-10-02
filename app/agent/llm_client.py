import json
import re
import io
import base64
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Type, TypeVar, AsyncGenerator, List, Union
import httpx
from pydantic import BaseModel
from app.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

try:
    import json_repair
except ImportError:
    json_repair = None

try:
    from PIL import Image
except ImportError:
    Image = None

def encode_image_to_base64(image_input: Union[str, Path, bytes], max_dim: Optional[int] = None) -> str:
    """Encodes an image path or bytes to a base64 string preserving full native resolution."""
    if isinstance(image_input, (str, Path)):
        p = Path(image_input)
        if not p.exists():
            # If it's already a base64 string
            if isinstance(image_input, str) and len(image_input) > 200 and not image_input.startswith("/"):
                return image_input
            raise FileNotFoundError(f"Image not found at path: {image_input}")
        with open(p, "rb") as f:
            raw_bytes = f.read()
    elif isinstance(image_input, bytes):
        raw_bytes = image_input
    else:
        raise ValueError(f"Unsupported image input type: {type(image_input)}")

    # If max_dim is specified and > 0, resize. Otherwise preserve 100% full original native resolution.
    if max_dim and max_dim > 0 and Image is not None:
        try:
            with Image.open(io.BytesIO(raw_bytes)) as img:
                img = img.convert("RGB")
                w, h = img.size
                if max(w, h) > max_dim:
                    ratio = max_dim / max(w, h)
                    new_w = max(1, int(w * ratio))
                    new_h = max(1, int(h * ratio))
                    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=95)
                return base64.b64encode(buf.getvalue()).decode("utf-8")
        except Exception as e:
            logger.debug(f"Pillow resize error, falling back to raw base64: {e}")

    # Full native original quality
    return base64.b64encode(raw_bytes).decode("utf-8")


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
        self.lmstudio_base_url = settings.LMSTUDIO_BASE_URL
        self.lmstudio_model = settings.LMSTUDIO_MODEL
        self.gemini_api_key = settings.GEMINI_API_KEY
        self.openai_api_key = settings.OPENAI_API_KEY

    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        images: Optional[List[Union[str, Path]]] = None
    ) -> str:
        """Generate text from selected LLM provider, optionally passing images for multimodal reasoning."""
        if self.provider == "gemini" and self.gemini_api_key:
            return await self._generate_gemini(prompt, system_prompt, images)
        elif self.provider == "openai" and self.openai_api_key:
            return await self._generate_openai(prompt, system_prompt, images)
        elif self.provider == "lmstudio":
            return await self._generate_openai_compatible(
                base_url=self.lmstudio_base_url,
                model=self.lmstudio_model,
                prompt=prompt,
                system_prompt=system_prompt,
                images=images
            )
        else:
            return await self._generate_ollama(prompt, system_prompt, images)

    async def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        images: Optional[List[Union[str, Path]]] = None
    ) -> Dict[str, Any]:
        """Generate structured JSON response, optionally passing images for multimodal reasoning."""
        json_sys_prompt = (
            (system_prompt or "") + 
            "\nIMPORTANT: Respond ONLY with a valid JSON object. Do not include extra conversational text or markdown formatting outside the JSON."
        )
        raw_text = await self.generate_text(prompt, json_sys_prompt, images=images)
        return extract_json_from_response(raw_text)

    async def _generate_ollama(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        images: Optional[List[Union[str, Path]]] = None
    ) -> str:
        """Call local Ollama server with optional multimodal images."""
        url = f"{self.ollama_base_url}/api/chat"
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        user_msg: Dict[str, Any] = {"role": "user", "content": prompt}
        if images:
            encoded_images = []
            for img in images:
                try:
                    encoded_images.append(encode_image_to_base64(img, max_dim=settings.MULTIMODAL_FRAME_MAX_DIM))
                except Exception as e:
                    logger.warning(f"Failed to encode image {img} for Ollama: {e}")
            if encoded_images:
                user_msg["images"] = encoded_images
        
        messages.append(user_msg)

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
            async with httpx.AsyncClient(timeout=180.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("message", {}).get("content", "")
                else:
                    raise RuntimeError(f"Ollama returned error status {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.error(f"Error calling Ollama: {e}")
            raise

    async def _generate_gemini(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        images: Optional[List[Union[str, Path]]] = None
    ) -> str:
        """Call Google Gemini API with multimodal support."""
        from google import genai
        client = genai.Client(api_key=self.gemini_api_key)
        contents = []
        if system_prompt:
            contents.append(f"System: {system_prompt}\n\n")
        
        if images and Image is not None:
            for img_path in images:
                try:
                    p = Path(img_path)
                    if p.exists():
                        contents.append(Image.open(p))
                except Exception as e:
                    logger.warning(f"Error loading image for Gemini: {e}")

        contents.append(prompt)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
        )
        return response.text

    async def _generate_openai(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        images: Optional[List[Union[str, Path]]] = None
    ) -> str:
        """Call OpenAI API with optional multimodal images."""
        return await self._generate_openai_compatible(
            base_url="https://api.openai.com/v1",
            api_key=self.openai_api_key,
            model="gpt-4o-mini",
            prompt=prompt,
            system_prompt=system_prompt,
            images=images
        )

    async def _generate_openai_compatible(
        self,
        base_url: str,
        model: str = "gemma-4",
        api_key: str = "not-needed",
        prompt: str = "",
        system_prompt: Optional[str] = None,
        images: Optional[List[Union[str, Path]]] = None
    ) -> str:
        """Call LM Studio or other local OpenAI-compatible server with standard multimodal payload format."""
        from openai import AsyncOpenAI
        client = AsyncOpenAI(base_url=base_url, api_key=api_key or "not-needed")
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        if images:
            # Construct standard OpenAI vision content array
            user_content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
            for img in images:
                try:
                    b64 = encode_image_to_base64(img, max_dim=settings.MULTIMODAL_FRAME_MAX_DIM)
                    user_content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64}"
                        }
                    })
                except Exception as e:
                    logger.warning(f"Failed to process image {img} for LM Studio: {e}")
            messages.append({"role": "user", "content": user_content})
        else:
            messages.append({"role": "user", "content": prompt})

        response = await client.chat.completions.create(
            model=model or "gemma-4",
            messages=messages,
            temperature=0.1,
            max_tokens=4096
        )
        return response.choices[0].message.content or ""

