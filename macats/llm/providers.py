import json, os
from typing import Any, Dict
import aiohttp

class LLMConfig:
    provider: str = os.getenv("LLM_PROVIDER", "ollama")
    model: str = os.getenv("LLM_MODEL", "llama3:8b")
    base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    timeout: int = int(os.getenv("LLM_TIMEOUT_SECS", "30"))

async def _post_json(url: str, payload: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as s:
        async with s.post(url, json=payload) as r:
            r.raise_for_status()
            return await r.json()

def _force_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").replace("json","",1).strip()
    i, j = text.find("{"), text.rfind("}")
    return json.loads(text[i:j+1] if i >= 0 and j > i else text)

class OllamaClient:
    def __init__(self, cfg: LLMConfig): self.cfg = cfg
    async def chat_json(self, system: str, user: str) -> Dict[str, Any]:
        url = f"{self.cfg.base_url}/api/chat"
        payload = {"model": self.cfg.model, "messages": [
            {"role":"system","content":system},
            {"role":"user","content":user},
        ], "stream": False, "format": "json"}
        data = await _post_json(url, payload, self.cfg.timeout)
        return _force_json(data.get("message",{}).get("content",""))

async def get_llm():
    cfg = LLMConfig()
    if cfg.provider.lower() == "ollama":
        return OllamaClient(cfg)
    raise NotImplementedError("Only Ollama implemented here.")