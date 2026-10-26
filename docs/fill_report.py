"""성과보고서 양식(첨부 docx)의 1번 표 오른쪽 칸들을 채운다."""
import re
import sys
from xml.sax.saxutils import escape

SRC = "un/word/document.xml"
s = open(SRC, encoding="utf-8").read()

SZ = 19  # 9.5pt


def run(text, bold=False, hl=False, color=None, sz=SZ):
    rpr = '<w:rFonts w:hint="eastAsia"/>'
    if bold:
        rpr += "<w:b/><w:bCs/>"
    if color:
        rpr += f'<w:color w:val="{color}"/>'
    rpr += f'<w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/>'
    if hl:
        rpr += '<w:highlight w:val="yellow"/>'
    return f'<w:r><w:rPr>{rpr}</w:rPr><w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def para(parts, kind="body", jc=None):
    """parts: str 또는 [(text, opts)] / kind: head(ㅇ), item(-), body"""
    ind = ""
    if kind == "item":
        ind = '<w:ind w:left="300" w:hanging="150"/>'
    elif kind == "sub":
        ind = '<w:ind w:left="450" w:hanging="150"/>'
    sp = '<w:spacing w:before="40" w:after="0" w:line="264" w:lineRule="auto"/>' if kind == "head" else \
         '<w:spacing w:after="0" w:line="264" w:lineRule="auto"/>'
    j = f'<w:jc w:val="{jc}"/>' if jc else ""
    if isinstance(parts, str):
        parts = [(parts, {})]
    runs = "".join(run(t, bold=(o.get("bold", kind == "head")), hl=o.get("hl", False), color=o.get("color")) for t, o in parts)
    return f"<w:p><w:pPr><w:wordWrap/>{sp}{ind}{j}</w:pPr>{runs}</w:p>"


H = lambda t: para("ㅇ " + t, "head")  # noqa: E731
I = lambda *p: para([("- ", {})] + [(x, {}) if isinstance(x, str) else x for x in p], "item")  # noqa: E731
S = lambda t: para("· " + t, "sub")  # noqa: E731
HL = lambda lab, t: para([("ㅇ " + lab, {"bold": True}), (" " + t, {"bold": False})], "head")  # noqa: E731
FILL = lambda t: (t, {"hl": True})  # noqa: E731  (사용자가 채울 자리)

cells = {
    "AI 기술명": [
        para([("케어브릿지(CareBridge) — 근거 대조형 다국어 돌봄 관찰메모 구조화 AI", {"bold": True})]),
    ],
    "아이디어명": [
        para([("13번. 케어브릿지", {"bold": True}),
              (" (외국인 요양보호사 후보 및 돌봄인력의 비식별 관찰메모를 AI가 분석·번역, 한국어 구조화 초안으로 정리하여 돌봄인력 담당자의 의사결정을 보조하는 서비스)", {})]),
    ],
    "기술요약": [
        para("외국인 요양보호사가 모국어·서툰 한국어로 쓴 관찰메모에서 ① 개인정보를 먼저 가린 뒤 ② 생성형 AI(LLM)가 번역·구조화해 "
             "위험 신호·관찰 내용·권장 조치·급여제공기록 초안·작성자 언어 되묻기 질문을 만들고, ③ AI가 댄 근거 구절을 원문과 자동 대조하며 "
             "④ 7개 언어 위험표현 사전으로 AI의 누락을 교차검증하여, 담당자는 검토·승인만 하면 되는 웹 서비스"),
    ],
    "최종목표": [
        H("다국어 관찰메모 1건을 1분 안에 ‘근거가 확인된’ 한국어 기록 초안으로 바꿔, 언어 장벽 때문에 낙상·섭취 저하·투약 문제 같은 위험 신호가 늦게 전달되는 일을 줄임"),
        I("AI 단독이 아닌 AI+규칙 이중 확인으로 위험 신호 미탐을 최소화하고, 최종 판단은 담당자가 하는 사람 검토 구조를 갖춤"),
    ],
    "개발 내용": [
        H("탐구 개요"),
        I("참여인력: ", FILL("개인 1인(기획·AI 파이프라인·웹 개발·평가 전담)"), " / 결과물: 웹 서비스(", FILL("테스트 URL 기입"), "), 소스코드, 합성 평가셋"),
        I("문제 정의: 외국인 돌봄인력이 늘면서 현장 메모의 언어는 다양해졌지만 급여제공기록·인수인계는 한국어로 이뤄짐. "
          "담당자가 번역기로 메모를 해석하는 동안 위험 신호가 지연·누락되고, 작성자는 다시 묻는 질문을 이해하기 어려움"),
        I("설계 원칙: 비식별 우선, 모든 판단에 원문 근거 제시, 진단 금지(관찰 중심 서술), 사람 최종 승인, 서버 무저장"),
        H("AI 접근방법 — 5단계 파이프라인 구현"),
        I("① 비식별 안전망: 한국 이름(성씨+호칭)·외국 이름(호칭 기반)·전화·주민번호·주소·이메일·생년월일 + 기관 등록 이름을 [이름1] 같은 토큰으로 바꾼 뒤에만 외부 AI로 전송"),
        I("② LLM 구조화: JSON 스키마 강제(관찰 11범주, 위험 10유형×긴급/주의/관찰, 권장 조치의 담당·기한, 누락 정보, 쉬운 모국어 되묻기, 용어 표준화, 기록지 특이사항 초안). "
          "‘근거 없으면 항목 생성 금지’, 메모 속 지시문 무시(프롬프트 주입 방어) 지침 포함. Gemini·OpenAI·Claude 교체 가능"),
        I("③ 스키마 보정: 허용값 밖 응답을 근사 매핑하고, 긴급도가 위험 신호 최고 단계보다 낮으면 자동 상향"),
        I("④ 근거 대조(환각 점검): AI가 인용한 원문 구절을 정규화·유사도 매칭으로 원문에서 찾아 ‘원문 확인/대부분 일치/못 찾음’을 표시. 화면에서 항목을 누르면 원문 해당 부분에 형광펜 표시"),
        I("⑤ 규칙 교차검증: 베트남어·인니어·네팔어·영어·중국어·우즈베크어·한국어 위험표현 사전(재현율 우선)으로 따로 찾아, AI가 놓친 위험을 경고하고 긴급도를 올림"),
        I("담당자 화면: 원문-결과 2단 화면, 권장 조치 체크, 검토함(승인·보류, CSV 내보내기), 직접 쓴 메시지 번역(역번역으로 검수). 외부 패키지 없는 Python 서버로 배포 단순화"),
        H("결과 해석 — 합성 관찰메모 30건(8개 언어, 정답 라벨 직접 구축)"),
        I("비식별 재현율 100%(개인정보 12건 모두 가림), 규칙 단독 위험 신호 재현율 92.5%·정밀도 100%, 긴급도 일치 86.7%"),
        I("AI+규칙: 위험 신호 재현율 ", FILL("○○%"), "·정밀도 ", FILL("○○%"), ", 긴급도 일치 ", FILL("○○%"),
          ", 근거 구절 원문 확인율 ", FILL("○○%"), ", 처리시간 중앙값 ", FILL("○초"), " (", FILL("사용 모델명"), ")"),
        I("해석: 규칙 사전에 없는 타갈로그어 메모에서 규칙은 위험 3건을 모두 놓쳐 AI의 다국어 이해가 필수임을 확인. 반대로 AI가 투약 거부를 빠뜨린 응답을 넣은 시험에서 "
          "교차검증이 경고를 띄워, 두 방식이 서로의 빈틈을 메우는 구조가 동작함을 확인(단위 테스트 19건 통과)"),
    ],
    "애로점": [
        HL("데이터 확보:", "실제 관찰메모는 민감정보라 확보할 수 없어 8개 언어 합성 메모와 정답 라벨을 직접 만듦. 원어민 검수는 하지 못했고, 규칙 사전도 같은 데이터를 보며 다듬어 규칙 수치는 높게 나옴(한계로 명시)"),
        HL("AI 환각:", "LLM이 근거 구절을 번역투로 바꿔 인용하거나 없는 내용을 덧붙이는 문제 → 원문 대조 단계를 두어 ‘못 찾음’을 화면에 드러내고 담당자가 확인하게 함"),
        HL("다국어 규칙 충돌:", "언어 간 단어 충돌(인니어 sore=오후 ↔ 영어 sore=상처 등)로 오탐 발생 → 언어별 표현을 정밀화하고 회귀 테스트로 고정. 호칭 없는 외국 이름은 탐지가 어려워 ‘가릴 이름 등록’ 기능으로 보완"),
    ],
    "기대효과": [
        HL("담당자:", "메모 해석·기록 작성 시간을 줄이고, 낙상·탈수·투약 오류 같은 위험 신호를 근무 중에 바로 인지"),
        HL("외국인 요양보호사·어르신:", "모국어로 정확히 보고하고 쉬운 모국어 질문을 받아 소통 부담이 줄어 현장 정착에 도움. 어르신은 언어 장벽으로 인한 돌봄 공백이 줄어듦"),
        HL("한계와 개선 방안:", "기관 협약을 통한 실제 메모 검증과 원어민 검수, 이름 인식 모델 결합, 기관 내부 설치형(온프레미스) AI 옵션, 장기요양 기록 시스템·인수인계·보호자 알림 연동"),
    ],
}

# 1번 표만 대상으로
t_start = s.find("<w:tbl>")
t_end = s.find("</w:tbl>", t_start) + len("</w:tbl>")
tbl = s[t_start:t_end]
rows = re.findall(r"<w:tr[ >].*?</w:tr>", tbl, flags=re.S)
new_tbl = tbl
for row in rows:
    tcs = re.findall(r"<w:tc>.*?</w:tc>", row, flags=re.S)
    if len(tcs) != 2:
        continue
    label = "".join(re.findall(r"<w:t(?: [^>]*)?>([^<]*)</w:t>", tcs[0])).replace(" ", "")
    key = next((k for k in cells if k.replace(" ", "") in label), None)
    if not key:
        print("건너뜀:", label, file=sys.stderr)
        continue
    tc = tcs[1]
    tcpr = re.search(r"<w:tcPr>.*?</w:tcPr>", tc, flags=re.S).group(0)
    new_tc = "<w:tc>" + tcpr + "".join(cells[key]) + "</w:tc>"
    new_row = row.replace(tc, new_tc)
    new_tbl = new_tbl.replace(row, new_row)
    print("채움:", key, file=sys.stderr)

s = s[:t_start] + new_tbl + s[t_end:]
# 참가신청서는 새 쪽에서 시작
after = s.find("<w:p", t_start + len(new_tbl))
pend = s.find("</w:p>", after)
seg = s[after:pend]
if "pageBreakBefore" not in seg:
    if "<w:pPr>" in seg:
        seg2 = seg.replace("<w:pPr>", "<w:pPr><w:pageBreakBefore/>", 1)
    else:
        seg2 = re.sub(r"(<w:p[^>]*>)", r"\1<w:pPr><w:pageBreakBefore/></w:pPr>", seg, count=1)
    s = s[:after] + seg2 + s[pend:]
open(SRC, "w", encoding="utf-8").write(s)
