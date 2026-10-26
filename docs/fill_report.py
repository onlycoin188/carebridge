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
        para([("케어브릿지(CareBridge) — 근거 대조형 돌봄 관찰메모 구조화 AI", {"bold": True})]),
    ],
    "아이디어명": [
        para([("13번. 케어브릿지", {"bold": True}),
              (" (외국인 요양보호사 후보 및 돌봄인력의 비식별 관찰메모를 AI가 분석·번역, 한국어 구조화 초안으로 정리하여 돌봄인력 담당자의 의사결정을 보조하는 서비스)", {})]),
    ],
    "기술요약": [
        para("요양보호사·교육생(외국인 포함)이 한국어나 모국어로 쓴 짧은 관찰메모에서 개인정보부터 가린 뒤, 생성형 AI가 원문과 나란히 "
             "한국어 인수인계·업무보고 초안(관찰 내용, 보고가 필요한 변화, 다음 확인사항, 되묻기 질문)으로 정리하는 웹 서비스. "
             "메모에 없는 시점·양·복약 여부는 채우지 않고, 근거 구절은 원문과 자동 대조하며, 담당자가 검토·승인함"),
    ],
    "최종목표": [
        H("짧은 관찰메모를 1분 안에 원문 근거가 붙은 한국어 기록 초안으로 정리해 재질문·재작성 부담을 줄이고, 확인되지 않은 내용은 채우지 않으며 담당자 승인 뒤에만 공유되게 함"),
    ],
    "개발 내용": [
        H("탐구 개요"),
        I("참여인력: 개인 1인(기획·AI 파이프라인·웹 개발·평가 전담) / 결과물: 웹 서비스(https://carebridge-liart-sigma.vercel.app), 소스코드, 합성 평가셋"),
        I("계기·가설: 부산 재가센터 관계자 인터뷰에서 방문 후 업무수행일지 작성, 공단 입력·출력, 기관 내부 확인 절차를 듣고 기존 시스템을 대체하지 않는 메모 정리 방식을 구상함. "
          "짧고 비정형적인 메모나 빠진 정보 때문에 담당자가 다시 묻거나 기록을 새로 써야 할 수 있고, 외국인 인력에게는 직무 용어·기록 문장이 추가 부담이라는 가설(누락 사고 사례는 미확인)"),
        I("사용 환경: 교육기관(교육생이 합성 사례로 기록 연습, 강사 검토)과 자격·고용 조건을 갖춘 요양기관(작성자 메모, 기관 담당자 검토). 병원·요양병원·방문간호는 제외"),
        I("설계 원칙: 한국어 기록 지원 중심(번역은 선택 보조), 비식별 우선, 모든 항목에 원문 근거, 미확인 내용 비워 두기, 진단·처방·건강위험 판정 안 함, 담당자 승인 후 공유, 서버 무저장"),
        H("AI 접근방법 — 5단계 파이프라인 구현"),
        I("① 비식별 안전망: 한국 이름(성씨+호칭)·외국 이름(호칭 기반)·전화·주민번호·주소·이메일·생년월일과 기관 등록 이름을 [이름1] 같은 토큰으로 바꾼 뒤에만 외부 AI로 전송"),
        I("② LLM 구조화: JSON 스키마로 출력 형식을 고정(관찰 11범주, 보고가 필요한 변화 10유형×3단계, 권장 조치, 다음 확인사항, 쉬운 모국어 되묻기, 용어 표준화, 인수인계 초안). "
          "메모에 없는 시점·양·복약 여부 추정 금지, 본인 호소는 본인 표현으로, 메모 속 지시문 무시(프롬프트 주입 방어)를 지침에 넣음"),
        I("③ 형식 보정: 허용값 밖 응답을 가까운 값으로 바꾸고, 원문에 없는 [이름N] 토큰을 지우며, 보고 우선순위를 가장 높은 단계에 맞춤"),
        I("④ 근거 대조(환각 점검): AI가 인용한 구절을 정규화·유사도 매칭으로 원문에서 찾아 원문 확인/대부분 일치/못 찾음으로 구분. 화면에서 항목을 누르면 원문의 해당 부분에 형광펜이 칠해짐"),
        I("⑤ 규칙 교차검증: 7개 언어 주의표현 사전(재현율 우선)으로 따로 찾아, AI가 놓친 변화는 경고하고 보고 우선순위를 올림"),
        I("화면: 원문·결과 2단 구성, 다음 확인사항, 검토함(승인·보류, CSV 내보내기), 직접 쓴 메시지 번역(역번역 검수). 외부 패키지 없이 Python 표준 라이브러리만 사용"),
        H("결과 — 합성 관찰메모 30건(8개 언어, 정답 라벨 직접 구축), Gemini 3.5 Flash-Lite로 2회 실측"),
        I("보고 필요 변화 재현율: AI 단독 82.5~87.5%, 규칙 단독 92.5%, AI+규칙 교차검증 100%(2회 모두, 정밀도 95.2~97.6%)"),
        I("보고 우선순위 일치 96.7%(낮게 판단 3.3%), 근거 구절 원문 확인율 99.2~100%, 개인정보 가림 100%(12건), 언어 식별 100%, 처리시간 중앙값 6.6~10.8초"),
        I("해석: AI만 쓰면 보고가 필요한 변화를 6~8건 중 1건꼴로 놓쳤으나 교차검증이 모두 메움. 반대로 규칙 사전에 없는 타갈로그어 메모는 규칙이 3건을 모두 놓쳐 AI가 꼭 필요했음. "
          "사전질의 예시(‘점심 절반, 무릎 불편, 복약 미확인’)에서도 복약 여부를 채우지 않고 다음 확인사항으로 남김(단위 테스트 20건 통과)"),
    ],
    "애로점": [
        HL("데이터 확보:", "실제 관찰메모는 민감정보라 구할 수 없어 8개 언어 합성 메모와 정답 라벨을 직접 만듦. 원어민 검수는 하지 못했고, 규칙 사전도 같은 데이터를 보며 다듬어 규칙 수치는 높게 나옴(한계로 명시)"),
        HL("AI 환각:", "LLM이 근거 구절을 번역투로 바꿔 인용하거나, ‘Lola(할머니)’ 같은 호칭을 이름으로 보고 원문에 없는 [이름1]을 만듦. 원문 대조로 ‘못 찾음’을 드러내고, 지침 보완과 함께 원문에 없는 토큰을 자동으로 지우는 단계를 넣음"),
        HL("모델 가용성·속도:", "처음 고른 모델은 신규 API 키로 쓸 수 없었고 상위 모델은 1건에 100초 넘게 걸림. 경량 모델로 바꾸고 과부하 때 자동 재시도를 넣음. 응답 시간은 API 혼잡에 따라 1건 2~11초로 변동"),
        HL("다국어 규칙 충돌:", "언어 간 단어 충돌(인니어 sore=오후, 영어 sore=상처 등)로 오탐 발생. 언어별 표현을 좁히고 회귀 테스트로 고정함"),
    ],
    "기대효과": [
        HL("담당자·강사:", "메모를 다시 묻고 고쳐 쓰는 부담을 줄일 것으로 기대. 확인되지 않은 항목이 비어 있어 무엇을 물어야 할지 바로 보임"),
        HL("요양보호사·교육생:", "직무 용어와 기록 문장 작성을 도와 한국어 기록 연습·작성 부담을 덜 수 있음. 번역은 필요할 때만 쓰며 한국어 교육·자격을 대신하지 않음"),
        HL("한계와 검증 계획:", "현장 효과는 검증 전. 같은 합성 사례를 직접 작성/초안 보조 조건으로 나눠 전체 시간, 중요 사실 누락, 원문에 없는 사실 추가, 잘못된 보류 해제를 비교할 계획. "
           "실사용 전 개인정보 처리 근거·동의·보관 기간·외부 AI 전송 여부를 기관과 확정. 법정 기록지 대체·공단 자동 입력, 근무시간·급여 판단은 하지 않음"),
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
