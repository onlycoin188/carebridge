"""AI 응답 경로 점검: 실제 AI 대신 기록해 둔 응답(fixtures)을 넣어 후처리를 검증한다.
이 응답은 '투약 문제' 위험 신호를 일부러 빠뜨린 것으로, 규칙 교차검증이 잡아내는지 본다."""
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from carebridge import pipeline  # noqa: E402

RAW = json.loads((HERE / "fixtures" / "ai_raw_vi02.json").read_text(encoding="utf-8"))
MEMO = json.loads((HERE.parent / "public" / "samples.json").read_text(encoding="utf-8"))[0]["memo"]
META = {"provider": "gemini", "model": "gemini-2.5-flash", "latency_ms": 3120, "tokens_in": 2100, "tokens_out": 900}


def run():
    with mock.patch.dict(os.environ, {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "test"}), \
         mock.patch.object(pipeline, "chat_json", return_value=(json.loads(json.dumps(RAW)), META)):
        return pipeline.analyze(MEMO, {"shift": "저녁", "recipient_code": "A-07"})


class TestAIPath(unittest.TestCase):
    def test_pii_not_sent(self):
        captured = {}

        def fake(system, user, *a, **k):
            captured["user"] = user
            return json.loads(json.dumps(RAW)), META
        with mock.patch.dict(os.environ, {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "test"}), \
             mock.patch.object(pipeline, "chat_json", side_effect=fake):
            pipeline.analyze(MEMO)
        self.assertNotIn("010-4821-3307", captured["user"])
        self.assertNotIn(" Lan ", captured["user"])

    def test_cross_check_catches_missed_medication(self):
        out = run()
        types = [a["type"] for a in out["checks"]["cross_check_alerts"]]
        self.assertIn("투약 문제", types)

    def test_evidence_all_found(self):
        out = run()
        self.assertEqual(out["checks"]["evidence"]["missing"], 0)
        self.assertEqual(out["meta"]["mode"], "ai")


if __name__ == "__main__":
    if os.environ.get("DUMP_FIXTURE"):
        print(json.dumps(run(), ensure_ascii=False))
    else:
        unittest.main()
