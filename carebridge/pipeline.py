"""케어브릿지 분석 파이프라인.

  원문 ─▶ ① 비식별 안전망(pii) ─▶ ② AI 번역·구조화(llm) ─▶ ③ 스키마 정리
       ─▶ ④ 근거 대조(환각 점검) ─▶ ⑤ 규칙 기반 위험 교차검증 ─▶ 담당자 검토

AI는 초안을 만들 뿐이고, 최종 판단과 기록은 담당자가 승인한다(사람 검토 전제).
"""
from __future__ import annotations

import json
import re
import unicodedata
from difflib import SequenceMatcher

from . import pii, rules
from .llm import LLMError, chat_json, resolve_provider
from .prompts import (CATEGORIES, DUES, LEVELS, OUTPUT_SCHEMA, OWNERS, REPLY_SYSTEM,
                      SYSTEM_PROMPT, URGENCY, user_prompt)

MAX_MEMO_CHARS = 3000
_TOKEN = re.compile(r"\[(이름|전화|주민번호|주소|이메일|생년월일)\d+\]")


def drop_unknown_tokens(result: dict, masked_text: str) -> list[str]:
    """원문에 없는 [이름N] 같은 토큰을 AI가 지어내면 지운다. 원문 근거 구절(evidence_original)은 건드리지 않는다."""
    known = {m.group(0) for m in _TOKEN.finditer(masked_text)}
    found: set[str] = set()

    def fix(v):
        if isinstance(v, str):
            def sub(m):
                if m.group(0) in known:
                    return m.group(0)
                found.add(m.group(0))
                return "어르신" if m.group(1) == "이름" else "(확인 필요)"
            out = _TOKEN.sub(sub, v)
            return re.sub(r"어르신\s*(어르신|할머니|할아버지)", r"\1", out)
        if isinstance(v, list):
            return [fix(x) for x in v]
        if isinstance(v, dict):
            return {k: (x if k == "evidence_original" else fix(x)) for k, x in v.items()}
        return v

    for k in list(result):
        result[k] = fix(result[k])
    return [f"원문에 없는 토큰 제거: {', '.join(sorted(found))}"] if found else []


_RANK = {"일반": 0, "관찰": 0, "주의": 1, "긴급": 2}
_URG_BY_RANK = {0: "일반", 1: "주의", 2: "긴급"}


# ---------- ④ 근거 대조 ----------
def _norm(s: str) -> tuple[str, list[int]]:
    """비교용 정규화 문자열과, 정규화 문자 -> 원문 위치 대응표."""
    out, idx = [], []
    for i, ch in enumerate(s):
        c = unicodedata.normalize("NFC", ch).lower()
        if c.isspace() or unicodedata.category(c).startswith("P"):
            continue
        out.append(c)
        idx.append(i)
    return "".join(out), idx


def locate_evidence(evidence: str, source: str) -> dict:
    """AI가 댄 근거 구절이 실제 원문에 있는지 확인한다.
    status: exact(그대로 있음) / partial(대부분 일치) / missing(원문에서 찾을 수 없음 → 환각 의심)"""
    ev = (evidence or "").strip()
    if not ev:
        return {"status": "missing", "score": 0.0, "start": None, "end": None}
    pos = source.find(ev)
    if pos >= 0:
        return {"status": "exact", "score": 1.0, "start": pos, "end": pos + len(ev)}
    nev, _ = _norm(ev)
    nsrc, idx = _norm(source)
    if not nev or not nsrc:
        return {"status": "missing", "score": 0.0, "start": None, "end": None}
    p = nsrc.find(nev)
    if p >= 0:
        return {"status": "exact", "score": 1.0, "start": idx[p], "end": idx[p + len(nev) - 1] + 1}
    # 슬라이딩 윈도우 유사도 (번역투로 살짝 바뀐 경우)
    L = len(nev)
    best, best_i = 0.0, 0
    step = max(1, L // 6)
    for i in range(0, max(1, len(nsrc) - L + 1), step):
        r = SequenceMatcher(None, nev, nsrc[i:i + L]).ratio()
        if r > best:
            best, best_i = r, i
    # 주변 미세 조정
    for i in range(max(0, best_i - step), min(len(nsrc) - L + 1, best_i + step) if len(nsrc) >= L else 1):
        r = SequenceMatcher(None, nev, nsrc[i:i + L]).ratio()
        if r > best:
            best, best_i = r, i
    if best >= 0.75 and len(nsrc) >= 1:
        end_i = min(best_i + L, len(nsrc)) - 1
        return {"status": "partial", "score": round(best, 2), "start": idx[best_i], "end": idx[end_i] + 1}
    return {"status": "missing", "score": round(best, 2), "start": None, "end": None}


# ---------- ③ 스키마 정리 ----------
def _pick(value, allowed: list[str], default: str) -> str:
    if isinstance(value, str):
        v = value.strip()
        if v in allowed:
            return v
        for a in allowed:  # '낙상 위험' -> '낙상' 같은 근사 매칭
            if a in v or v in a:
                return a
    return default


def _as_list(v) -> list:
    return v if isinstance(v, list) else []


def normalize(raw: dict) -> tuple[dict, list[str]]:
    """AI 출력을 스키마에 맞게 다듬고, 고친 내역을 돌려준다."""
    fixes: list[str] = []
    out: dict = {}
    for k in OUTPUT_SCHEMA["required"]:
        if k not in raw:
            fixes.append(f"누락 필드 보완: {k}")
    out["detected_language"] = str(raw.get("detected_language") or "other").lower()[:5]
    out["translation_ko"] = str(raw.get("translation_ko") or "")
    out["summary_ko"] = str(raw.get("summary_ko") or "")
    obs = []
    for o in _as_list(raw.get("observations")):
        if not isinstance(o, dict) or not o.get("content_ko"):
            continue
        obs.append({
            "category": _pick(o.get("category"), CATEGORIES, "기타"),
            "content_ko": str(o["content_ko"]),
            "evidence_original": str(o.get("evidence_original") or ""),
            "certainty": _pick(o.get("certainty"), ["확실", "추정"], "추정"),
        })
    out["observations"] = obs
    flags = []
    for f in _as_list(raw.get("risk_flags")):
        if not isinstance(f, dict):
            continue
        flags.append({
            "type": _pick(f.get("type"), rules.RISK_TYPES, "기타"),
            "level": _pick(f.get("level"), LEVELS, "주의"),
            "reason_ko": str(f.get("reason_ko") or ""),
            "evidence_original": str(f.get("evidence_original") or ""),
        })
    out["risk_flags"] = flags
    out["urgency"] = _pick(raw.get("urgency"), URGENCY, "일반")
    out["recommended_actions"] = [
        {"action_ko": str(a.get("action_ko")), "owner": _pick(a.get("owner"), OWNERS, "센터장·관리자"),
         "due": _pick(a.get("due"), DUES, "오늘 안")}
        for a in _as_list(raw.get("recommended_actions")) if isinstance(a, dict) and a.get("action_ko")
    ]
    out["missing_info"] = [str(x) for x in _as_list(raw.get("missing_info")) if x]
    out["followup_questions"] = [
        {"question_ko": str(q.get("question_ko")), "question_native": str(q.get("question_native") or "")}
        for q in _as_list(raw.get("followup_questions")) if isinstance(q, dict) and q.get("question_ko")
    ]
    out["terms"] = [
        {"original": str(t.get("original")), "standard_ko": str(t.get("standard_ko") or "")}
        for t in _as_list(raw.get("terms")) if isinstance(t, dict) and t.get("original")
    ]
    out["record_draft_ko"] = str(raw.get("record_draft_ko") or "")
    # 긴급도는 위험 신호 중 최고 단계와 일치해야 한다
    top = max([_RANK[f["level"]] for f in flags] or [0])
    if _RANK[out["urgency"]] < top:
        fixes.append(f"긴급도 보정: {out['urgency']} → {_URG_BY_RANK[top]} (위험 신호 단계와 맞춤)")
        out["urgency"] = _URG_BY_RANK[top]
    return out, fixes


# ---------- 데모 모드 (AI 키가 없을 때) ----------
_DEMO_ACTION = {
    "낙상": ("활력징후·외상 여부 즉시 확인, 낙상 보고서 작성", "간호(조무)사", "즉시"),
    "호흡 이상": ("산소포화도·호흡수 측정, 필요 시 의료기관 연계", "간호(조무)사", "즉시"),
    "피부손상·욕창": ("해당 부위 사진 기록, 체위 변경 주기 점검", "간호(조무)사", "오늘 안"),
    "식사·수분 저하": ("섭취량·배설량 기록 시작, 다음 끼니 재확인", "요양보호사", "오늘 안"),
    "투약 문제": ("투약 기록 대조, 누락·중복 여부 확인", "간호(조무)사", "즉시"),
    "인지·행동 변화": ("평소 상태와 비교 관찰, 보호자 공유 여부 결정", "사회복지사", "오늘 안"),
    "통증": ("통증 부위·정도 재확인", "간호(조무)사", "오늘 안"),
    "발열·감염 의심": ("체온 재측정, 감염관리 지침 확인", "간호(조무)사", "즉시"),
    "정서·안전 우려": ("면담 및 상황 확인", "사회복지사", "오늘 안"),
}
_CAT_OF = {"낙상": "이동·낙상", "호흡 이상": "신체·피부", "피부손상·욕창": "신체·피부", "식사·수분 저하": "식사·수분",
           "투약 문제": "투약", "인지·행동 변화": "인지·정서", "통증": "통증", "발열·감염 의심": "신체·피부",
           "정서·안전 우려": "인지·정서"}


def _demo_result(masked: str, hits: list[dict]) -> dict:
    lang = rules.guess_language(masked)
    flags, obs, acts, draft = [], [], [], []
    for h in hits:
        lvl = rules.DEFAULT_LEVEL.get(h["type"], "관찰")
        flags.append({"type": h["type"], "level": lvl,
                      "reason_ko": f"원문에서 '{h['match']}' 표현을 찾음 (규칙 사전 기준)",
                      "evidence_original": h["match"]})
        obs.append({"category": _CAT_OF.get(h["type"], "기타"), "content_ko": f"{h['type']} 관련 표현 확인",
                    "evidence_original": h["match"], "certainty": "추정"})
        if h["type"] in _DEMO_ACTION:
            a, o, d = _DEMO_ACTION[h["type"]]
            acts.append({"action_ko": a, "owner": o, "due": d})
        draft.append(f"- {h['type']} 관련 표현 확인(원문: {h['match']}) — 담당자 확인 필요")
    top = max([_RANK[f["level"]] for f in flags] or [0])
    return {
        "detected_language": lang,
        "translation_ko": "데모 모드에서는 AI 번역을 하지 않습니다. AI 키를 연결하면 원문 전체가 한국어로 옮겨집니다.",
        "summary_ko": (f"규칙 사전으로 위험 표현 {len(flags)}건을 찾았습니다." if flags
                       else "규칙 사전에 걸린 위험 표현이 없습니다."),
        "observations": obs, "risk_flags": flags, "urgency": _URG_BY_RANK[top],
        "recommended_actions": acts, "missing_info": ["데모 모드: AI 분석 결과 아님"],
        "followup_questions": [], "terms": [],
        "record_draft_ko": "\n".join(draft) or "- 특이사항 없음(규칙 기준)",
    }


# ---------- 메인 ----------
def analyze(memo: str, context: dict | None = None, extra_names: list[str] | None = None) -> dict:
    memo = (memo or "").strip()
    if not memo:
        raise ValueError("메모 내용을 입력해 주세요.")
    if len(memo) > MAX_MEMO_CHARS:
        raise ValueError(f"메모는 {MAX_MEMO_CHARS}자까지 분석할 수 있습니다. 나누어 입력해 주세요.")

    masked = pii.mask(memo, extra_names)
    hits = rules.scan(masked.text)
    provider, model = resolve_provider()

    fixes: list[str] = []
    if provider == "mock":
        result, _ = normalize(_demo_result(masked.text, hits))
        meta = {"provider": "mock", "model": "rule-based-demo", "latency_ms": 0, "tokens_in": 0, "tokens_out": 0}
    else:
        system = SYSTEM_PROMPT + "\nJSON 스키마:\n" + json.dumps(OUTPUT_SCHEMA, ensure_ascii=False)
        user = user_prompt(masked.text, context)
        try:
            raw, meta = chat_json(system, user, provider, model)
        except LLMError:
            # 한 번만 재시도 (일시 오류·JSON 깨짐 대응)
            raw, meta = chat_json(system, user + "\n\n반드시 유효한 JSON 객체 하나만 출력하세요.", provider, model)
            fixes.append("1회 재시도 후 성공")
        result, f2 = normalize(raw)
        fixes += f2
        fixes += drop_unknown_tokens(result, masked.text)

    # ④ 근거 대조
    for item in result["observations"] + result["risk_flags"]:
        item["evidence_check"] = locate_evidence(item["evidence_original"], masked.text)

    # ⑤ 규칙 교차검증: 규칙이 찾았는데 AI가 표시하지 않은 위험
    ai_types = {f["type"] for f in result["risk_flags"]}
    alerts = []
    for h in hits:
        if h["type"] not in ai_types:
            alerts.append({"type": h["type"], "match": h["match"], "start": h["start"], "end": h["end"],
                           "level": rules.DEFAULT_LEVEL.get(h["type"], "관찰"),
                           "message": f"원문의 '{h['match']}' 표현이 {h['type']} 신호일 수 있는데 AI 초안에 없습니다. 확인해 주세요."})
    ai_urgency = result["urgency"]
    alert_top = max([_RANK[a["level"]] for a in alerts] or [0])
    final_urgency = _URG_BY_RANK[max(_RANK[ai_urgency], alert_top)]

    verified = [i["evidence_check"]["status"] for i in result["observations"] + result["risk_flags"]]
    rule_lang = rules.guess_language(masked.text)
    return {
        "masked_memo": masked.text,
        "pii": {"entities": masked.entities, "counts": masked.counts},
        "result": result,
        "checks": {
            "rule_hits": hits,
            "cross_check_alerts": alerts,
            "ai_urgency": ai_urgency,
            "final_urgency": final_urgency,
            "urgency_raised_by_rule": final_urgency != ai_urgency,
            "evidence": {"total": len(verified), "exact": verified.count("exact"),
                         "partial": verified.count("partial"), "missing": verified.count("missing")},
            "language_rule_guess": rule_lang,
            "language_agrees": rule_lang in (result["detected_language"], "other") or provider == "mock",
            "schema_fixes": fixes,
        },
        "meta": {**meta, "mode": "demo" if provider == "mock" else "ai",
                 "language_name": rules.LANG_NAMES.get(result["detected_language"], result["detected_language"])},
    }


def translate_reply(message_ko: str, target_lang: str) -> dict:
    message_ko = (message_ko or "").strip()
    if not message_ko:
        raise ValueError("보낼 내용을 입력해 주세요.")
    if len(message_ko) > 800:
        raise ValueError("메시지는 800자까지 번역할 수 있습니다.")
    masked = pii.mask(message_ko)
    provider, model = resolve_provider()
    lang_name = rules.LANG_NAMES.get(target_lang, target_lang)
    if provider == "mock":
        return {"translation": "(데모 모드) AI 키를 연결하면 " + lang_name + "로 번역됩니다.",
                "back_translation_ko": masked.text, "meta": {"mode": "demo"}}
    data, meta = chat_json(REPLY_SYSTEM, f"대상 언어: {lang_name} ({target_lang})\n메시지:\n{masked.text}",
                           provider, model, max_tokens=1200)
    return {"translation": str(data.get("translation", "")),
            "back_translation_ko": str(data.get("back_translation_ko", "")),
            "meta": {**meta, "mode": "ai"}}
