"""AI 제공사 연결부. 표준 라이브러리(urllib)만 사용해 의존성이 없다.

환경변수
  LLM_PROVIDER  gemini | openai | anthropic | mock   (비우면 키가 있는 제공사를 자동 선택)
  LLM_MODEL     모델 이름 (비우면 제공사별 기본값)
  GEMINI_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

DEFAULT_MODELS = {
    "gemini": "gemini-3.5-flash-lite",
    "openai": "gpt-4.1-mini",
    "anthropic": "claude-sonnet-5-5",
}
KEY_ENV = {"gemini": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}


class LLMError(RuntimeError):
    pass


def resolve_provider() -> tuple[str, str]:
    prov = (os.environ.get("LLM_PROVIDER") or "").strip().lower()
    if not prov:
        for p in ("gemini", "openai", "anthropic"):
            if os.environ.get(KEY_ENV[p]):
                prov = p
                break
        else:
            prov = "mock"
    if prov != "mock" and not os.environ.get(KEY_ENV.get(prov, "")):
        prov = "mock"
    model = os.environ.get("LLM_MODEL") or DEFAULT_MODELS.get(prov, "rule-based-demo")
    return prov, model


TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "45"))
RETRY_CODES = {429, 500, 502, 503, 504}  # 과부하·일시 오류는 잠깐 쉬었다가 다시 시도


def _post(url: str, payload: dict, headers: dict, timeout: float = TIMEOUT, attempts: int = 3) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **headers}, method="POST")
    for i in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:500]
            if e.code in RETRY_CODES and i < attempts - 1:
                time.sleep(1.5 * (i + 1))
                continue
            raise LLMError(f"AI 서버 응답 오류 {e.code}: {body}") from e
        except urllib.error.URLError as e:
            raise LLMError(f"AI 서버에 연결하지 못했습니다: {e.reason}") from e
        except (TimeoutError, OSError) as e:  # 응답 대기 시간 초과 등 (URLError로 감싸지지 않음)
            raise LLMError(f"AI 서버 응답이 {timeout:.0f}초 안에 오지 않았습니다: {e}") from e
    raise LLMError("AI 서버 재시도 횟수를 넘었습니다")


def extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


def chat_json(system: str, user: str, provider: str, model: str, temperature: float = 0.1,
              max_tokens: int = 4096) -> tuple[dict, dict]:
    """AI에게 JSON 응답을 요청한다. 반환: (파싱된 JSON, 메타정보)"""
    t0 = time.time()
    if provider == "gemini":
        key = os.environ["GEMINI_API_KEY"]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens,
                                 "responseMimeType": "application/json"},
        }
        res = _post(url, payload, {"x-goog-api-key": key})
        try:
            text = "".join(p.get("text", "") for p in res["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError) as e:
            raise LLMError(f"Gemini 응답 형식이 예상과 다릅니다: {str(res)[:300]}") from e
        usage = res.get("usageMetadata", {})
        tokens = (usage.get("promptTokenCount", 0), usage.get("candidatesTokenCount", 0))
    elif provider == "openai":
        key = os.environ["OPENAI_API_KEY"]
        base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        payload = {
            "model": model, "temperature": temperature, "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        res = _post(f"{base}/chat/completions", payload, {"Authorization": f"Bearer {key}"})
        text = res["choices"][0]["message"]["content"]
        usage = res.get("usage", {})
        tokens = (usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))
    elif provider == "anthropic":
        key = os.environ["ANTHROPIC_API_KEY"]
        payload = {
            "model": model, "max_tokens": max_tokens, "temperature": temperature,
            "system": system, "messages": [{"role": "user", "content": user}],
        }
        res = _post("https://api.anthropic.com/v1/messages", payload,
                    {"x-api-key": key, "anthropic-version": "2023-06-01"})
        text = "".join(b.get("text", "") for b in res.get("content", []) if b.get("type") == "text")
        usage = res.get("usage", {})
        tokens = (usage.get("input_tokens", 0), usage.get("output_tokens", 0))
    else:
        raise LLMError(f"알 수 없는 제공사: {provider}")
    try:
        data = extract_json(text)
    except json.JSONDecodeError as e:
        raise LLMError("AI 응답을 JSON으로 읽지 못했습니다") from e
    return data, {"provider": provider, "model": model, "latency_ms": int((time.time() - t0) * 1000),
                  "tokens_in": tokens[0], "tokens_out": tokens[1]}
