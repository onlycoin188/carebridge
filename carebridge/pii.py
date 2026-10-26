"""1단계: 비식별 안전망 (LLM 호출 전, 서버 안에서만 실행).

관찰메모는 원칙적으로 비식별 상태로 들어오지만, 현장에서는 이름·전화번호가
섞여 들어오는 일이 잦다. 외부 AI로 보내기 전에 규칙 기반으로 한 번 더 가린다.
가린 원문은 [이름1] 같은 토큰으로 바뀌며, 원래 값은 응답에 포함하지 않는다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# 한국 성씨 (복성 포함). 이름 오탐을 줄이기 위해 "성씨 + 2글자 + 호칭" 형태만 잡는다.
_SURNAMES_2 = ["남궁", "황보", "제갈", "선우", "독고", "사공", "서문"]
_SURNAMES_1 = (
    "김이박최정강조윤장임한오서신권황안송류유전홍고문양손배백허남심노하곽성차주"
    "우구민진지엄채원천방공현함변염여추도소석선설마길연위표명기반라왕금옥육인맹제모탁국어은편용예경봉"
)
_HONORIFIC = r"(?:어르신|할머니|할아버지|님|씨|보호자|선생님|요양보호사|간호사|팀장|센터장|여사|옹)"
# 이름 끝 글자로 잘 쓰이지 않는 조사형 글자 (예: '오전에 할머니'의 '오전에' 오탐 방지)
_BAD_LAST = set("에는를을께서와과의도로")
_STOP_WORDS = {"오늘은", "오전에", "오후에", "이번에", "이분은", "저녁에", "아침에", "점심에",
               "어제는", "우리집", "옆방의", "담당자", "조금씩", "이번주", "주말에"}

_NAME_RE = re.compile(
    r"(?P<name>(?:%s)[가-힣]{2}|[%s][가-힣]{2})(?=\s?%s)"
    % ("|".join(_SURNAMES_2), _SURNAMES_1, _HONORIFIC)
)
# 라틴 문자 이름: 호칭/관계어가 앞뒤에 붙은 경우만 (Mr. Tran, Bà Lan, Ibu Sari, Kim Soon-ja halmoni 등)
_LATIN_NAME_RE = re.compile(
    r"(?:(?<![A-Za-zÀ-ỹ])(?i:Mr|Mrs|Ms|Miss|Mdm|Lola|Lolo|Ibu|Bu|Bapak|Pak|Nenek|Kakek|Ông|Bà|Cụ|Chị|Anh)\.?\s+)"
    r"(?P<name>[A-ZÀ-Ỹ][a-zà-ỹ]+(?:[\s-][A-ZÀ-Ỹ][a-zà-ỹ]+){0,2})"
)

_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("주민번호", re.compile(r"(?<!\d)\d{6}\s?-\s?[1-8]\d{6}(?!\d)")),
    ("전화", re.compile(r"(?<!\d)(?:\+82[\s-]?)?0?1[016789][\s.-]?\d{3,4}[\s.-]?\d{4}(?!\d)")),
    ("전화", re.compile(r"(?<!\d)0(?:2|[3-6][1-5])[\s.-]?\d{3,4}[\s.-]?\d{4}(?!\d)")),
    ("이메일", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("생년월일", re.compile(r"(?:19|20)\d{2}\s?[년./-]\s?\d{1,2}\s?[월./-]\s?\d{1,2}\s?일?\s?(?:생|출생)")),
    ("주소", re.compile(
        r"[가-힣]{2,6}(?:시|도)\s?[가-힣]{1,6}(?:구|군|시)\s?(?:[가-힣0-9]{1,10}(?:로|길|동|읍|면))"
        r"(?:\s?\d{1,4}(?:-\d{1,4})?(?:번길)?)?(?:\s?\d{1,4}(?:-\d{1,4})?)?")),
    ("주소", re.compile(r"[가-힣A-Za-z0-9]{2,15}아파트\s?\d{1,4}동\s?\d{1,4}호")),
]


@dataclass
class MaskResult:
    text: str
    entities: list[dict] = field(default_factory=list)  # {"type","token","start","end"} (masked 텍스트 기준)

    @property
    def counts(self) -> dict:
        out: dict[str, int] = {}
        for e in self.entities:
            out[e["type"]] = out.get(e["type"], 0) + 1
        return out


def _find_spans(text: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    for kind, pat in _PATTERNS:
        for m in pat.finditer(text):
            spans.append((m.start(), m.end(), kind))
    for m in _NAME_RE.finditer(text):
        name = m.group("name")
        if name[-1] in _BAD_LAST or name in _STOP_WORDS:
            continue
        spans.append((m.start("name"), m.end("name"), "이름"))
    for m in _LATIN_NAME_RE.finditer(text):
        # 정규식 범위(À-Ỹ)에 소문자 악센트 글자가 섞이므로, 대문자로 시작하는 단어까지만 이름으로 본다
        name = m.group("name")
        keep = 0
        for tok in re.finditer(r"[^\s-]+", name):
            if not tok.group(0)[0].isupper():
                break
            keep = tok.end()
        if keep:
            spans.append((m.start("name"), m.start("name") + keep, "이름"))
    # 겹치는 구간 정리: 시작이 빠르고 긴 것 우선
    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    merged: list[tuple[int, int, str]] = []
    for s in spans:
        if merged and s[0] < merged[-1][1]:
            continue
        merged.append(s)
    return merged


def mask(text: str, extra_names: list[str] | None = None) -> MaskResult:
    """원문을 가려서 돌려준다. extra_names: 기관이 등록한 이름 목록(선택)."""
    if extra_names:
        for n in sorted({n.strip() for n in extra_names if n and n.strip()}, key=len, reverse=True):
            text = text.replace(n, "\u0000NAME:" + n + "\u0000")
        # 등록 이름은 아래에서 일반 이름과 같은 방식으로 토큰화
    spans = _find_spans(text)
    # 등록 이름 표시 구간 추가
    for m in re.finditer(r"\u0000NAME:(.+?)\u0000", text):
        spans.append((m.start(), m.end(), "이름"))
    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    clean: list[tuple[int, int, str]] = []
    for s in spans:
        if clean and s[0] < clean[-1][1]:
            continue
        clean.append(s)

    counters: dict[str, int] = {}
    seen: dict[tuple[str, str], str] = {}
    out_parts: list[str] = []
    entities: list[dict] = []
    cursor = 0
    pos = 0
    for start, end, kind in clean:
        out_parts.append(text[cursor:start])
        pos += start - cursor
        raw = text[start:end].replace("\u0000NAME:", "").replace("\u0000", "")
        key = (kind, re.sub(r"\s", "", raw))
        if key not in seen:
            counters[kind] = counters.get(kind, 0) + 1
            seen[key] = f"[{kind}{counters[kind]}]"
        token = seen[key]
        out_parts.append(token)
        entities.append({"type": kind, "token": token, "start": pos, "end": pos + len(token)})
        pos += len(token)
        cursor = end
    out_parts.append(text[cursor:])
    masked = "".join(out_parts).replace("\u0000", "")
    return MaskResult(text=masked, entities=entities)
