"""합성 관찰메모 평가 스크립트.

  python eval/run_eval.py                 # 현재 환경변수의 AI 제공사로 평가
  LLM_PROVIDER=mock python eval/run_eval.py   # AI 없이 규칙 기반만 평가(기준선)

지표
  - 비식별: 정답 개인정보 문자열이 가려진 비율(재현율)
  - 위험 신호: 유형 단위 재현율·정밀도 (optional_risks는 맞혀도·틀려도 정밀도에서 제외)
     · AI 단독 / 규칙 단독 / AI+규칙 교차검증 세 가지를 비교
  - 긴급도: 정답 허용 범위 안에 든 비율, 과소분류율(정답보다 낮게 판단)
  - 근거 대조: AI가 댄 근거 구절이 원문에서 확인된 비율 (환각 점검)
  - 언어 식별 정확도, 스키마 보정 건수, 지연시간
결과는 eval/results.md 와 eval/results.json 으로 저장된다.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from carebridge import pii, pipeline, rules  # noqa: E402
from carebridge.llm import LLMError, resolve_provider  # noqa: E402

RANK = {"일반": 0, "주의": 1, "긴급": 2}


def prf(tp: int, fp: int, fn: int) -> tuple[float, float]:
    rec = tp / (tp + fn) if tp + fn else 1.0
    prec = tp / (tp + fp) if tp + fp else 1.0
    return rec, prec


def main():
    rows = [json.loads(l) for l in (ROOT / "eval" / "dataset.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    provider, model = resolve_provider()
    print(f"평가 대상: {provider} / {model}, 메모 {len(rows)}건", flush=True)

    counts = {k: [0, 0, 0] for k in ("ai", "rule", "hybrid")}  # tp, fp, fn
    pii_tp = pii_fn = 0
    urg_ok = urg_under = lang_ok = 0
    ev_total = ev_exact = ev_partial = ev_missing = 0
    fixes = 0
    latencies = []
    per_row = []
    failures = []

    for r in rows:
        masked = pii.mask(r["memo"])
        leaked = [p for p in r["pii"] if p in masked.text]
        pii_tp += len(r["pii"]) - len(leaked)
        pii_fn += len(leaked)
        try:
            t0 = time.time()
            out = pipeline.analyze(r["memo"])
            latencies.append(time.time() - t0)
        except (LLMError, ValueError) as e:
            failures.append({"id": r["id"], "error": str(e)[:200]})
            print(f"  {r['id']}: 실패 {e}", flush=True)
            continue
        gold, opt = set(r["gold_risks"]), set(r["optional_risks"])
        ai = {f["type"] for f in out["result"]["risk_flags"]}
        rule = {h["type"] for h in out["checks"]["rule_hits"]}
        hybrid = ai | rule
        for name, pred in (("ai", ai), ("rule", rule), ("hybrid", hybrid)):
            counts[name][0] += len(pred & gold)
            counts[name][1] += len(pred - gold - opt)
            counts[name][2] += len(gold - pred)
        final_u = out["checks"]["final_urgency"]
        if final_u in r["gold_urgency"]:
            urg_ok += 1
        elif RANK[final_u] < min(RANK[g] for g in r["gold_urgency"]):
            urg_under += 1
        det = out["result"]["detected_language"]
        if det == r["lang"] or (r["lang"] == "tl" and det in ("tl", "fil")):
            lang_ok += 1
        ev = out["checks"]["evidence"]
        ev_total += ev["total"]; ev_exact += ev["exact"]; ev_partial += ev["partial"]; ev_missing += ev["missing"]
        fixes += len(out["checks"]["schema_fixes"])
        per_row.append({"id": r["id"], "gold": sorted(gold), "ai": sorted(ai), "rule": sorted(rule),
                        "urgency": final_u, "gold_urgency": r["gold_urgency"], "lang": det,
                        "evidence": ev, "leaked_pii": leaked})
        print(f"  {r['id']}: AI={sorted(ai)} 긴급도={final_u}", flush=True)

    n = len(per_row)
    summary = {
        "provider": provider, "model": model, "n_memos": len(rows), "n_ok": n, "failures": failures,
        "pii_recall": pii_tp / (pii_tp + pii_fn) if pii_tp + pii_fn else 1.0, "pii_total": pii_tp + pii_fn,
        "risk": {k: dict(zip(("recall", "precision"), prf(*v))) | {"tp": v[0], "fp": v[1], "fn": v[2]}
                 for k, v in counts.items()},
        "urgency_accuracy": urg_ok / n if n else 0, "urgency_under_triage": urg_under / n if n else 0,
        "language_accuracy": lang_ok / n if n else 0,
        "evidence": {"total": ev_total, "exact": ev_exact, "partial": ev_partial, "missing": ev_missing,
                     "verified_rate": (ev_exact + ev_partial) / ev_total if ev_total else None},
        "schema_fixes": fixes,
        "latency_sec_median": statistics.median(latencies) if latencies else None,
        "rows": per_row,
    }
    (ROOT / "eval" / "results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")

    pct = lambda x: "-" if x is None else f"{x * 100:.1f}%"  # noqa: E731
    md = [f"# 케어브릿지 평가 결과", "",
          f"- 평가 대상: `{provider}` / `{model}`",
          f"- 합성 관찰메모 {len(rows)}건 (8개 언어), 처리 성공 {n}건",
          *(["- ※ mock 모드: AI 없이 규칙 사전만 쓴 기준선입니다. 규칙 사전은 이 데이터셋을 보며 다듬었으므로 수치가 실제보다 높게 나옵니다."]
            if provider == "mock" else []),
          "", "| 지표 | 값 |", "|---|---|",
          f"| 비식별 재현율 (개인정보 {summary['pii_total']}건) | {pct(summary['pii_recall'])} |"]
    for k, label in (("ai", "AI 단독"), ("rule", "규칙 단독"), ("hybrid", "AI+규칙 교차검증")):
        v = summary["risk"][k]
        md.append(f"| 위험 신호 재현율 / 정밀도 — {label} | {pct(v['recall'])} / {pct(v['precision'])} |")
    md += [f"| 긴급도 일치율 | {pct(summary['urgency_accuracy'])} |",
           f"| 긴급도 과소분류율 (낮게 판단) | {pct(summary['urgency_under_triage'])} |",
           f"| 언어 식별 정확도 | {pct(summary['language_accuracy'])} |",
           f"| 근거 구절 원문 확인율 ({ev_total}건) | {pct(summary['evidence']['verified_rate'])} |",
           f"| 스키마 자동 보정 건수 | {fixes} |",
           f"| 지연시간 중앙값 | {summary['latency_sec_median']:.2f}초 |" if latencies else "| 지연시간 | - |"]
    if failures:
        md += ["", f"실패 {len(failures)}건: " + ", ".join(f["id"] for f in failures)]
    (ROOT / "eval" / "results.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
