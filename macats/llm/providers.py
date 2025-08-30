# macats/llm/providers.py
import json, os, asyncio
from typing import List, Dict, Any, Optional
import aiohttp

class LLMConfig:
    provider: str = os.getenv("LLM_PROVIDER", "ollama").lower()
    model: str = os.getenv("LLM_MODEL", "llama3:8b")
    ollama_base: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    timeout: int = int(os.getenv("LLM_TIMEOUT_SECS", "30"))

async def _post_json(url: str, payload: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    t = aiohttp.ClientTimeout(total=timeout)
    async with aiohttp.ClientSession(timeout=t) as sess:
        async with sess.post(url, json=payload) as resp:
            resp.raise_for_status()
            return await resp.json()

def _force_json(text: str) -> Dict[str, Any]:
    # Try to extract JSON object from text
    text = text.strip()
    if text.startswith("```"):
        # handle fenced blocks
        text = text.strip("`")
        # remove "json" hint if present
        text = text.replace("json", "", 1).strip()
    # find first { ... } block
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end+1]
    return json.loads(text)

class OllamaClient:
    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg

    async def chat_json(self, system: str, user: str) -> Dict[str, Any]:
        """
        Calls Ollama /api/chat with format=json and returns parsed JSON.
        """
        url = f"{self.cfg.ollama_base}/api/chat"
        payload = {
            "model": self.cfg.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "format": "json",
        }
        data = await _post_json(url, payload, self.cfg.timeout)
        content = data.get("message", {}).get("content", "")
        return _force_json(content)

async def get_llm() -> Any:
    cfg = LLMConfig()
    if cfg.provider == "ollama":
        return OllamaClient(cfg)
    raise NotImplementedError(f"LLM_PROVIDER {cfg.provider} not implemented yet.")