"""T-604: OCR 텍스트 일치 분석기 — 단위 테스트.

단위구현계획서.md 제5장 [T-604] 10항 절차를 코드로 검증한다.
- 준비: LCD 상에 "P10 System Status" 문구가 인가된 보정 이미지(fixture).
- 실행: pytest tests/test_text_evaluator.py
- 통과 기준: OCR 일치율 ≥90% → PASS, 고의 오타 → FAIL.
- 카드 12: VLM 15초 타임아웃 시 OCR-only 100% 판정.

T-009: Solar vision multimodal 미지원 — 테스트는 OCR mock + VLM stub/timeout만 사용한다.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from src.verifier.text_evaluator import (
    DEFAULT_MATCH_THRESHOLD,
    VLM_TIMEOUT_SEC,
    SolarVlmAssist,
    TextMatchEvaluator,
    match_ratio,
)
from src.verifier.vision_evaluator import SimCaptureProvider

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "tests" / "data"
LCD_OK = DATA_DIR / "lcd_p10_status.png"
LCD_TYPO = DATA_DIR / "lcd_p10_typo.png"
VERIFY_JSON = REPO_ROOT / "docs" / "verification" / "T-604_ocr_readout.json"

EXPECTED = "P10 System Status"


def _has_live_ocr() -> bool:
    try:
        from src.verifier.text_evaluator import create_default_ocr_engine

        create_default_ocr_engine()
        return True
    except Exception:
        return False


def _write_lcd_png(path: Path, caption: str) -> None:
    """1024×600 시뮬 LCD fixture에 캡션을 그려 저장한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (1024, 600), color=(40, 44, 52))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 1023, 70], fill=(30, 90, 160))
    try:
        font = ImageFont.truetype("arial.ttf", 36)
    except OSError:
        font = ImageFont.load_default()
    draw.text((40, 18), caption, fill=(255, 255, 255), font=font)
    draw.rectangle([40, 120, 980, 520], outline=(80, 80, 90), width=2)
    img.save(path)


@pytest.fixture(scope="session", autouse=True)
def lcd_fixtures() -> None:
    if not LCD_OK.exists():
        _write_lcd_png(LCD_OK, EXPECTED)
    if not LCD_TYPO.exists():
        _write_lcd_png(LCD_TYPO, "P10 Sistem Statys")  # 고의 오타


class ScriptedOcrEngine:
    """단위 테스트용 OCR mock — 호출 시 지정 문자열 목록을 반환한다."""

    def __init__(self, texts: list[str]) -> None:
        self.texts = list(texts)
        self.calls = 0

    def read_texts(self, image: np.ndarray) -> list[str]:
        self.calls += 1
        assert isinstance(image, np.ndarray)
        assert image.ndim == 3
        return list(self.texts)


def test_match_ratio_threshold_semantics():
    """일치율 계산: 동일 문자열 1.0, 고의 오타는 0.9 미만이어야 한다."""
    assert match_ratio(EXPECTED, EXPECTED) == pytest.approx(1.0)
    assert match_ratio(EXPECTED, "P10 Sistem Statys") < DEFAULT_MATCH_THRESHOLD


def test_ocr_expected_phrase_passes_at_90_percent():
    """OCR 인식 리스트에 P10 System Status 일치율 ≥90% → PASS."""
    ocr = ScriptedOcrEngine([EXPECTED, "OK", "Cancel"])
    evaluator = TextMatchEvaluator(
        [EXPECTED],
        ocr_engine=ocr,
        use_vlm=False,
    )
    result = evaluator.evaluate(SimCaptureProvider(LCD_OK))
    assert result["verdict"] == "PASS", result
    assert result["decision_source"] == "ocr_only"
    assert ocr.calls == 1
    best = result["phrase_results"][0]
    assert best["match_ratio"] >= DEFAULT_MATCH_THRESHOLD
    assert EXPECTED.lower() in best["best_ocr"].lower() or best["match_ratio"] >= 0.9


def test_deliberate_typo_fails():
    """잘못된 오타 단어를 고의 노출했을 때 FAIL을 정상 리턴한다."""
    ocr = ScriptedOcrEngine(["P10 Sistem Statys", "OK"])
    evaluator = TextMatchEvaluator(
        [EXPECTED],
        ocr_engine=ocr,
        use_vlm=False,
    )
    result = evaluator.evaluate(SimCaptureProvider(LCD_TYPO))
    assert result["verdict"] == "FAIL"
    assert result["phrase_results"][0]["match_ratio"] < DEFAULT_MATCH_THRESHOLD


def test_vlm_timeout_falls_back_to_ocr_only():
    """카드 12: Solar/VLM이 15초 타임아웃되면 OCR 결과만 100% 신뢰한다."""
    ocr = ScriptedOcrEngine([EXPECTED])
    # timeout보다 길게 sleep하는 stub → Futures timeout → OCR-only
    slow_vlm = SolarVlmAssist(mode="slow_stub", sleep_sec=VLM_TIMEOUT_SEC + 5.0)
    evaluator = TextMatchEvaluator(
        [EXPECTED],
        ocr_engine=ocr,
        vlm_assist=slow_vlm,
        use_vlm=True,
        vlm_timeout_sec=0.3,  # 단위 테스트 속도용 (프로덕션 기본은 15s)
    )
    t0 = time.perf_counter()
    result = evaluator.evaluate(SimCaptureProvider(LCD_OK))
    elapsed = time.perf_counter() - t0
    assert result["verdict"] == "PASS", result
    assert result["decision_source"] == "ocr_only_after_vlm_timeout"
    assert result["vlm"]["status"] == "timeout"
    assert elapsed < 2.0, f"타임아웃 폴백이 너무 느림: {elapsed:.2f}s"


def test_vlm_timeout_preserves_ocr_fail():
    """VLM 타임아웃 시에도 OCR FAIL은 FAIL로 유지된다 (OCR 100%)."""
    ocr = ScriptedOcrEngine(["totally wrong caption"])
    slow_vlm = SolarVlmAssist(mode="slow_stub", sleep_sec=5.0)
    evaluator = TextMatchEvaluator(
        [EXPECTED],
        ocr_engine=ocr,
        vlm_assist=slow_vlm,
        use_vlm=True,
        vlm_timeout_sec=0.2,
    )
    result = evaluator.evaluate(SimCaptureProvider(LCD_TYPO))
    assert result["verdict"] == "FAIL"
    assert result["decision_source"] == "ocr_only_after_vlm_timeout"


def test_save_ocr_readout_json():
    """검증 기록: docs/verification/T-604_ocr_readout.json에 매칭율 저장."""
    ocr = ScriptedOcrEngine([EXPECTED, "Ready"])
    evaluator = TextMatchEvaluator([EXPECTED], ocr_engine=ocr, use_vlm=False)
    result = evaluator.evaluate(SimCaptureProvider(LCD_OK))
    out = evaluator.save_readout(VERIFY_JSON, result)
    assert out.is_file()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["verdict"] == "PASS"
    assert payload["phrase_results"][0]["match_ratio"] >= DEFAULT_MATCH_THRESHOLD
    assert "ocr_texts" in payload


@pytest.mark.skipif(
    not _has_live_ocr(),
    reason="EasyOCR/pytesseract 미설치 — 라이브 OCR 경로 skip",
)
def test_optional_live_ocr_on_fixture():
    """선택적 라이브 OCR: 실제 엔진이 있으면 fixture에서 문구를 읽는다."""
    from src.verifier.text_evaluator import create_default_ocr_engine

    engine = create_default_ocr_engine()
    image = cv2.imread(str(LCD_OK))
    assert image is not None
    texts = engine.read_texts(image)
    assert texts, "OCR이 빈 결과를 반환함"
    ratios = [match_ratio(EXPECTED, t) for t in texts]
    assert max(ratios) >= DEFAULT_MATCH_THRESHOLD, texts
