"""python -m unittest discover tests"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["LLM_PROVIDER"] = "mock"

from carebridge import pii, pipeline, rules  # noqa: E402


class TestPII(unittest.TestCase):
    def test_phone_name_masked(self):
        m = pii.mask("김순자 할머니 보호자 전화 010-5512-8890")
        self.assertNotIn("김순자", m.text)
        self.assertNotIn("8890", m.text)
        self.assertIn("[이름1]", m.text)
        self.assertIn("[전화1]", m.text)

    def test_no_false_positive_on_common_words(self):
        m = pii.mask("오전에 할머니가 식사하심. 오늘은 할아버지 기분 좋음.")
        self.assertEqual(m.entities, [])

    def test_same_value_same_token(self):
        m = pii.mask("박영희 어르신 식사. 박영희 어르신 산책.")
        self.assertEqual(m.text.count("[이름1]"), 2)

    def test_latin_honorific_name(self):
        m = pii.mask("Mr. Park refused medicine. ông Trần bị ngã.")
        self.assertNotIn("Park", m.text)
        self.assertNotIn("Trần", m.text)

    def test_latin_name_stops_at_lowercase_word(self):
        m = pii.mask("Hôm nay bà Lan ăn rất ít")
        self.assertEqual(m.text, "Hôm nay bà [이름1] ăn rất ít")

    def test_registered_names(self):
        m = pii.mask("Nguyen Thi Hoa helped Lola today", extra_names=["Nguyen Thi Hoa"])
        self.assertNotIn("Hoa", m.text)

    def test_rrn(self):
        m = pii.mask("주민번호 380503-2123456")
        self.assertIn("[주민번호1]", m.text)


class TestEvidence(unittest.TestCase):
    src = "Hôm nay bà ăn rất ít, bữa trưa chỉ ăn khoảng 3 thìa cháo."

    def test_exact(self):
        r = pipeline.locate_evidence("bữa trưa chỉ ăn khoảng 3 thìa cháo", self.src)
        self.assertEqual(r["status"], "exact")
        self.assertEqual(self.src[r["start"]:r["end"]], "bữa trưa chỉ ăn khoảng 3 thìa cháo")

    def test_punctuation_insensitive(self):
        r = pipeline.locate_evidence("bà ăn rất ít bữa trưa", self.src)
        self.assertEqual(r["status"], "exact")

    def test_hallucinated(self):
        r = pipeline.locate_evidence("bà bị sốt cao 39 độ", self.src)
        self.assertEqual(r["status"], "missing")


class TestNormalize(unittest.TestCase):
    def test_urgency_raised_to_match_flags(self):
        out, fixes = pipeline.normalize({"risk_flags": [{"type": "낙상 위험", "level": "긴급",
                                                         "reason_ko": "x", "evidence_original": "y"}],
                                         "urgency": "일반"})
        self.assertEqual(out["risk_flags"][0]["type"], "낙상")
        self.assertEqual(out["urgency"], "긴급")
        self.assertTrue(any("긴급도" in f for f in fixes))

    def test_bad_enum_falls_back(self):
        out, _ = pipeline.normalize({"observations": [{"category": "???", "content_ko": "a",
                                                       "evidence_original": "b", "certainty": "maybe"}]})
        self.assertEqual(out["observations"][0]["category"], "기타")
        self.assertEqual(out["observations"][0]["certainty"], "추정")


class TestRulesAndPipeline(unittest.TestCase):
    def test_cross_language_collision(self):
        # 인도네시아어 'sore'(오후)는 영어 'sore'(상처)가 아님
        self.assertEqual([h for h in rules.scan("Sore jalan-jalan di taman") if h["type"] == "피부손상·욕창"], [])

    def test_demo_pipeline(self):
        out = pipeline.analyze("आज बिहान हजुरआमा बाथरूममा चिप्लिएर लड्नुभयो।")
        self.assertEqual(out["meta"]["mode"], "demo")
        self.assertEqual(out["checks"]["final_urgency"], "긴급")
        self.assertEqual(out["result"]["detected_language"], "ne")

    def test_cross_check_raises_urgency(self):
        # AI가 위험을 놓친 상황을 흉내: 규칙이 낙상을 찾으면 최종 긴급도는 '긴급'
        res = {"risk_flags": [], "urgency": "일반"}
        norm, _ = pipeline.normalize(res)
        self.assertEqual(norm["urgency"], "일반")
        hits = rules.scan("Lola fell in the bathroom")
        self.assertEqual(hits[0]["type"], "낙상")

    def test_invented_tokens_removed(self):
        res = {"summary_ko": "[이름1] 어르신이 식사하심. 보호자 [전화1]",
               "observations": [{"content_ko": "[이름2] 할머니 식사", "evidence_original": "[이름2] ăn"}]}
        fixes = pipeline.drop_unknown_tokens(res, "bà ăn ít, gọi số [전화1]")
        self.assertEqual(res["summary_ko"], "어르신이 식사하심. 보호자 [전화1]")
        self.assertEqual(res["observations"][0]["content_ko"], "할머니 식사")
        self.assertEqual(res["observations"][0]["evidence_original"], "[이름2] ăn")
        self.assertTrue(fixes)

    def test_limits(self):
        with self.assertRaises(ValueError):
            pipeline.analyze("")
        with self.assertRaises(ValueError):
            pipeline.analyze("a" * 3001)


if __name__ == "__main__":
    unittest.main()
