# 케어브릿지 (CareBridge)

외국인 요양보호사(후보 포함)가 모국어나 서툰 한국어로 쓴 **비식별 관찰메모**를 AI가 번역·분석해
**한국어 구조화 초안**(위험 신호, 관찰 내용, 권장 조치, 급여제공기록지 특이사항 초안, 되묻기 질문)으로 정리하고,
돌봄인력 담당자가 검토·승인하도록 돕는 웹 서비스입니다.

> 2026 AI 라이프 솔루션 챌린지 출품작 — AI 라이프 아이디어 챌린지 후보작 「케어브릿지」 구현

## 처리 흐름

```
원문 메모 ─▶ ① 비식별 안전망 ─▶ ② AI 번역·구조화 ─▶ ③ 스키마 정리 ─▶ ④ 근거 대조 ─▶ ⑤ 규칙 교차검증 ─▶ 담당자 검토·승인
            (서버 안, 규칙)     (LLM, JSON 스키마)   (값 보정)        (환각 점검)     (위험 누락 방지)
```

| 단계 | 하는 일 | 파일 |
|---|---|---|
| ① 비식별 안전망 | 이름(한국 이름+호칭, 외국 이름+호칭, 기관 등록 이름), 전화, 주민번호, 주소, 이메일, 생년월일을 AI로 보내기 **전에** `[이름1]` 같은 토큰으로 가림 | `carebridge/pii.py` |
| ② AI 구조화 | 언어 감지, 전체 번역, 관찰 항목(11개 범주), 위험 신호(10개 유형·3단계), 권장 조치(담당·기한), 누락 정보, 작성자 언어로 된 되묻기 질문, 용어 표준화, 기록지 초안 | `carebridge/prompts.py`, `llm.py` |
| ③ 스키마 정리 | 허용 값 밖의 응답 보정, 긴급도와 위험 신호 단계 일치 | `pipeline.normalize` |
| ④ 근거 대조 | AI가 댄 근거 구절이 원문에 실제로 있는지 확인(정확 일치 / 대부분 일치 / 찾을 수 없음) → 화면에 표시, 클릭하면 원문에 형광펜 표시 | `pipeline.locate_evidence` |
| ⑤ 규칙 교차검증 | 7개 언어 위험 표현 사전으로 따로 찾고, AI가 놓친 위험은 **경고**로 띄우고 긴급도를 올림 | `carebridge/rules.py` |

서버는 메모를 저장하지 않습니다. 승인한 기록은 담당자 브라우저(localStorage)에만 저장되고 CSV로 내보낼 수 있습니다.

## 실행

외부 패키지가 필요 없습니다 (Python 3.10 이상, 표준 라이브러리만 사용).

```bash
export GEMINI_API_KEY=...        # 또는 OPENAI_API_KEY / ANTHROPIC_API_KEY
python server.py                 # http://localhost:7860
```

키가 없으면 **데모 모드**(규칙 기반, 번역 없음)로 동작하며 화면에 그렇게 표시됩니다.

| 환경변수 | 설명 |
|---|---|
| `GEMINI_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | 하나만 있으면 자동 선택 |
| `LLM_PROVIDER` | `gemini` · `openai` · `anthropic` · `mock` 강제 지정 |
| `LLM_MODEL` | 기본값: gemini-2.5-flash / gpt-4.1-mini / claude-sonnet-5-5 |
| `RATE_LIMIT_PER_HOUR` | IP당 시간당 요청 수 (기본 40, 키 비용 보호) |

## 배포 (심사용 테스트 URL)

### 추천: Vercel (무료, 잠들지 않음)
정적 화면(`public/`)은 Vercel이 바로 제공하고, `/api/analyze`·`/api/reply`·`/api/health`는
`api/*.py` 서버리스 함수로 실행됩니다. 외부 패키지가 없어 빌드 설정이 필요 없습니다.

1. 이 폴더를 GitHub 저장소로 올리기 (비공개 저장소도 됨)
2. vercel.com에 GitHub로 가입(Hobby, 무료) → **Add New → Project** → 저장소 선택
3. Framework Preset은 **Other** 그대로, 설정 변경 없이 진행
4. **Environment Variables**에 `GEMINI_API_KEY`(또는 OpenAI·Anthropic 키) 추가 → **Deploy**
5. 생성된 `https://<프로젝트>.vercel.app` 이 테스트 URL. 열어서 상단이 **AI 연결됨**인지 확인

키를 나중에 넣었다면 Deployments 탭에서 **Redeploy** 해야 반영됩니다.

### 대안: Render (무료, 15분 미사용 시 잠듦)
GitHub에 올린 뒤 New → Blueprint → 저장소 선택(`render.yaml` 사용) → `GEMINI_API_KEY` 입력.
잠든 뒤 첫 접속은 1분가량 걸리므로 심사 기간에는 Vercel을 권합니다.

### 그 밖
`Dockerfile`이 있어 Docker를 지원하는 어느 서버에서나 `docker build`/`run`으로 실행할 수 있습니다.
(Hugging Face Spaces는 Docker·Gradio Space 생성에 유료 플랜이 필요하도록 바뀌었습니다.)

## 평가

```bash
python -m unittest discover tests         # 단위 테스트 (AI 없이)
python eval/run_eval.py                   # 현재 AI로 합성 메모 30건 평가 → eval/results.md
LLM_PROVIDER=mock python eval/run_eval.py # 규칙만 쓴 기준선
```

`eval/dataset.jsonl`: 베트남어·인도네시아어·네팔어·영어(필리핀)·중국어·우즈베크어·서툰 한국어·타갈로그어
합성 관찰메모 30건과 정답(위험 유형, 긴급도 허용 범위, 개인정보 문자열).
지표: 비식별 재현율, 위험 신호 재현율·정밀도(AI 단독 / 규칙 단독 / AI+규칙), 긴급도 일치율·과소분류율,
근거 구절 원문 확인율, 언어 식별 정확도, 지연시간.

## 한계

- 평가 데이터는 직접 만든 합성 메모이며 원어민 검수를 거치지 않았습니다. 규칙 사전도 같은 데이터를 보며 다듬어 규칙 수치는 높게 나옵니다.
- 이름 가리기는 호칭이 붙은 이름 중심입니다. 호칭 없는 외국 이름은 '가릴 이름 등록'으로 보완합니다.
- 진단이 아니라 기록 초안입니다. 최종 판단은 담당자가 합니다.

## 구조

```
server.py              로컬·Render·Docker 실행 파일
api/                   Vercel 서버리스 함수 (analyze, reply, health)
carebridge/            파이프라인 (pii, rules, prompts, llm, pipeline) + web.py(WSGI 앱)
public/                담당자 화면 (HTML/CSS/JS, 빌드 없음) + samples.json(예시 메모 9건)
eval/                  합성 평가셋, 평가 스크립트
tests/                 단위 테스트, AI 응답 경로 테스트
```
