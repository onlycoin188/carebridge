# CareBridge — Claude Code 작업 안내

## 무엇을 만드는가
2026 AI 라이프 솔루션 챌린지(산업통상부/KEIT) 출품작. 아이디어 챌린지 후보작 「케어브릿지」 구현(가점 5점 대상).
외국인 요양보호사의 다국어 비식별 관찰메모 → 한국어 구조화 초안(위험 신호·관찰·권장 조치·기록지 초안·되묻기 질문) → 담당자 검토·승인.

## 마감과 제출물 (2026-10-31 토 24:00, relations2@keit.re.kr, 주말엔 문의 답변 없음)
1. 성과보고서(양식 준수, 2장 이내) — `docs/케어브릿지_성과보고서_참가신청서.docx` (노란 칸 미완성)
2. 참가신청서(같은 docx 3쪽, 인적사항·서명은 사용자가 직접)
3. 테스트 URL — Vercel 배포 예정 (아직 안 함)
4. 데모 영상 2~5분 — 대본 `docs/demo_script.md`
선택: GitHub 링크, 샘플 결과물

## 구조
- `carebridge/pii.py` 비식별 안전망(정규식, AI 호출 전 실행)
- `carebridge/rules.py` 7개 언어 위험표현 사전 + 언어 추정 (AI 교차검증용)
- `carebridge/prompts.py` 시스템 프롬프트, JSON 출력 스키마
- `carebridge/llm.py` Gemini/OpenAI/Anthropic 호출 (urllib), 키 없으면 mock(데모 모드)
- `carebridge/pipeline.py` 마스킹 → LLM → normalize → 근거 대조(locate_evidence) → 규칙 교차검증
- `carebridge/web.py` WSGI 앱 (API + public/ 정적 파일)
- `server.py` 로컬/Render/Docker 실행, `api/*.py` Vercel 서버리스 함수(같은 web.app 사용)
- `public/` 화면(HTML/CSS/JS, 빌드 없음), `public/samples.json` 예시 메모 9건
- `eval/dataset.jsonl` 합성 메모 30건(8개 언어) + 정답, `eval/run_eval.py` 평가
- `tests/` unittest 19건 (`tests/fixtures/ai_raw_vi02.json`: 투약 위험을 일부러 뺀 AI 응답)

## 규칙
- **외부 패키지 추가 금지.** 표준 라이브러리만 쓴다(Vercel/Render 배포를 설정 없이 하기 위함).
- 응답·UI 문구는 한국어. 진단하지 않고 관찰 중심으로 서술. 서버는 메모를 저장·로그하지 않는다.
- 변경 후 `python -m unittest discover tests` 통과 확인.
- API 키는 `.env`(gitignore됨)나 환경변수로만. 커밋 금지.

## 명령
```bash
export GEMINI_API_KEY=...            # 또는 OPENAI_API_KEY / ANTHROPIC_API_KEY
python server.py                     # http://localhost:7860
python -m unittest discover tests
python eval/run_eval.py              # → eval/results.md (보고서 수치 출처)
LLM_PROVIDER=mock python eval/run_eval.py   # 규칙만 기준선
```

## 현재 상태
- 완료: 파이프라인, 화면, 합성 평가셋, 테스트, Vercel/Render/Docker 구성, 보고서 초안, 데모 대본
- 2026-10-26 실제 Gemini로 첫 실행 완료. gemini-2.5-flash는 신규 키에 404, 3.8-flash는 100초 이상·503 과부하가 잦아
  기본값을 gemini-3.5-flash-lite로 바꿈(2~7초). 결과: `eval/results.md` (지침 개정 후 2회: AI+규칙 재현율 100%, 긴급도 일치 96.7%, 근거 확인 99.2~100%, 중앙값 6.6~10.8초)
- 규칙 기준선(mock): 비식별 재현율 100%(12/12), 위험 재현율 92.5%/정밀도 100%, 긴급도 일치 86.7%
  (규칙 사전을 같은 데이터로 다듬어 과대추정 — 보고서에 한계로 명시함)

## 남은 일 (순서대로)
1. ~~로컬에서 실제 AI 키로 실행~~ (완료) → 샘플 9개 눈으로 확인, 프롬프트·스키마 문제 있으면 수정
2. ~~`python eval/run_eval.py` 실행~~ (완료, 보고서 수치 기입함) → 결과를 보고서의 노란 칸에 기입
   (위험 재현율·정밀도, 긴급도 일치, 근거 확인율, 처리시간 중앙값, 모델명)
3. ~~GitHub 푸시·Vercel 배포~~ (완료) 테스트 URL: https://carebridge-liart-sigma.vercel.app (보고서에 기입함)
4. 보고서 노란 칸: 테스트 URL, 참여인력(개인/팀) 확정. 아이디어 번호는 목록 순서상 "13번"으로 적음(공식 번호 확인 필요)
5. 데모 영상 녹화 — `docs/record_demo.js`로 화면 녹화(약 80초, 무음) 가능. 내레이션 입히기는 사용자
6. 제출 메일 발송

## 사전질의 답변(2026-10-26 반영)
- 사용자가 받은 답변서 2건: 한국어 기록지원이 중심, 번역은 선택 보조. 진단·처방·건강위험 판정, 법정 기록지 대체·공단 자동 입력,
  근무시간·급여 판단, 상시 녹음, 승인 없는 가족 공유는 하지 않음. 대상은 교육기관(교육생·강사)과 요양기관(작성자·담당자 검토).
  메모에 없는 시점·양·복약 여부는 채우지 않고 다음 확인사항으로 남김. 현장 효과는 가설(부산 재가센터 인터뷰 기반)
- 그래서 화면은 '긴급도'를 '보고 우선순위(즉시 보고/오늘 확인/일반 기록)'로, '위험 신호'를 '보고가 필요한 변화'로,
  '기록지 초안'을 '인수인계·업무보고 초안'으로 표시함(내부 값·평가셋 라벨은 긴급/주의/일반 그대로)
- 신청인 박태규. 개인 칸(소속·생년월일·전화·이메일)은 저장소에 넣지 않음

## 열린 질문 (사용자에게 확인)
- 개인/팀 참가 여부
