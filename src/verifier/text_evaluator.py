"""T-604: OCR 텍스트/의미 일치 분석기.

단위구현계획서.md 제5장 [T-604] 8항 구현 내용을 따른다.
보정된 시뮬 LCD 스크린샷에서 위젯/헤더 문구를 로컬 OCR로 읽고,
기대 문자열과의 일치율(≥90%)로 PASS/FAIL을 판정한다.

T-009 alignment (Solar vision multimodal)
----------------------------------------
T-009 스파이크 결론: Solar Pro 3/2는 채팅 엔드포인트에서 이미지 멀티모달 입력을
거부한다 (`HTTP 400 "Image input is not allowed for this model"`).
따라서 본 모듈은 **라이브 비전 VLM이 동작한다고 주장하지 않는다.**

판정 우선순위
1. **Primary**: 로컬 OCR (EasyOCR 또는 Tesseract / Pillow+pytesseract) —
   기대 문구 일치율 ≥90%면 PASS.
2. **Solar/VLM**: 선택적 **텍스트 전용** 보조, 또는 비전 요청 stub.
   기본 타임아웃 15초; 시간 초과 시 카드 12항에 따라 **OCR 결과만 100%** 신뢰.

입력은 T-603과 동일하게 ``ImageSource`` (SimCaptureProvider / CameraCaptureProvider)를 사용한다.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Literal, Protocol

import cv2
import numpy as np

from src.verifier.vision_evaluator import ImageSource

DEFAULT_MATCH_THRESHOLD = 0.90
VLM_TIMEOUT_SEC = 15.0

VlmStatus = Literal["ok", "timeout", "unavailable", "skipped", "text_only"]
DecisionSource = Literal[
    "ocr_only",
    "ocr_only_after_vlm_timeout",
    "ocr_plus_vlm",
]


class OcrEngine(Protocol):
    """로컬 OCR 엔진 프로토콜 — 단위 테스트에서 mock/inject 가능."""

    def read_texts(self, image: np.ndarray) -> list[str]:
        """BGR/RGB uint8 이미지에서 인식된 문자열 목록을 반환한다."""


def match_ratio(expected: str, observed: str) -> float:
    """대소문자/공백을 정규화한 뒤 SequenceMatcher 비율(0~1)을 반환한다."""
    a = " ".join(expected.lower().split())
    b = " ".join(observed.lower().split())
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def best_ocr_match(expected: str, ocr_texts: list[str]) -> tuple[str, float]:
    """OCR 목록에서 기대 문구와 가장 유사한 항목과 일치율을 반환한다."""
    if not ocr_texts:
        return "", 0.0
    best_text = ocr_texts[0]
    best = match_ratio(expected, best_text)
    for text in ocr_texts[1:]:
        ratio = match_ratio(expected, text)
        if ratio > best:
            best = ratio
            best_text = text
    # 전체 OCR 결합 문장과도 비교 (위젯이 한 줄로 합쳐진 경우)
    joined = " ".join(ocr_texts)
    joined_ratio = match_ratio(expected, joined)
    if joined_ratio > best:
        return joined, joined_ratio
    return best_text, best


class EasyOcrEngine:
    """EasyOCR 백엔드 (선택 설치)."""

    def __init__(self, langs: list[str] | None = None) -> None:
        import easyocr  # type: ignore[import-not-found]

        self._reader = easyocr.Reader(langs or ["en"], gpu=False)

    def read_texts(self, image: np.ndarray) -> list[str]:
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB) if image.ndim == 3 else image
        results = self._reader.readtext(rgb)
        return [str(item[1]).strip() for item in results if str(item[1]).strip()]


class TesseractOcrEngine:
    """Pillow + pytesseract 백엔드 (선택 설치, 시스템 Tesseract 필요)."""

    def __init__(self) -> None:
        import pytesseract  # type: ignore[import-not-found]
        from PIL import Image  # noqa: F401 — import probe

        self._pytesseract = pytesseract

    def read_texts(self, image: np.ndarray) -> list[str]:
        from PIL import Image

        if image.ndim == 3:
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        else:
            rgb = image
        pil = Image.fromarray(rgb)
        raw = self._pytesseract.image_to_string(pil)
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        return lines


def create_default_ocr_engine() -> OcrEngine:
    """EasyOCR → Tesseract 순으로 가용 엔진을 반환한다."""
    errors: list[str] = []
    try:
        return EasyOcrEngine()
    except Exception as exc:  # noqa: BLE001 — 선택 의존성 probe
        errors.append(f"easyocr: {exc}")
    try:
        return TesseractOcrEngine()
    except Exception as exc:  # noqa: BLE001
        errors.append(f"pytesseract: {exc}")
    raise RuntimeError(
        "로컬 OCR 엔진을 초기화할 수 없습니다. easyocr 또는 pytesseract(+Tesseract)를 "
        f"설치하세요. attempts={errors}"
    )


class SolarVlmAssist:
    """Solar 보조 판정 스텁 / 텍스트 전용 경로.

    T-009에 따라 이미지 멀티모달 라이브 호출은 수행하지 않는다.
    - ``unavailable``: 비전 VLM 미지원을 즉시 알림 (기본)
    - ``text_only``: OCR 문자열만으로 의미 일치 보조 (이미지 미전송)
    - ``slow_stub``: 타임아웃 폴백(Card 12) 검증용으로 sleep
    """

    def __init__(
        self,
        *,
        mode: Literal["unavailable", "text_only", "slow_stub"] = "unavailable",
        sleep_sec: float = VLM_TIMEOUT_SEC + 1.0,
        match_threshold: float = DEFAULT_MATCH_THRESHOLD,
    ) -> None:
        self.mode = mode
        self.sleep_sec = sleep_sec
        self.match_threshold = match_threshold

    def semantic_check(
        self,
        *,
        ocr_texts: list[str],
        expected_phrases: list[str],
    ) -> dict[str, Any]:
        if self.mode == "slow_stub":
            time.sleep(self.sleep_sec)
            return {
                "status": "ok",
                "semantic_match": True,
                "detail": "slow_stub completed (should have timed out in evaluator)",
            }
        if self.mode == "unavailable":
            return {
                "status": "unavailable",
                "semantic_match": None,
                "detail": (
                    "T-009: Solar Pro 3 rejects image multimodal "
                    "('Image input is not allowed'); live vision VLM not used."
                ),
            }
        # text_only: 이미지 없이 OCR 텍스트와 기대 문구만 비교
        all_ok = True
        details: list[str] = []
        for phrase in expected_phrases:
            _best, ratio = best_ocr_match(phrase, ocr_texts)
            ok = ratio >= self.match_threshold
            all_ok = all_ok and ok
            details.append(f"{phrase!r} ratio={ratio:.3f} ok={ok}")
        return {
            "status": "text_only",
            "semantic_match": all_ok,
            "detail": "; ".join(details),
        }


class TextMatchEvaluator:
    """기대 문구 대비 OCR(±선택 VLM) 일치율로 PASS/FAIL을 판정한다."""

    def __init__(
        self,
        expected_phrases: list[str],
        *,
        ocr_engine: OcrEngine | None = None,
        vlm_assist: SolarVlmAssist | None = None,
        match_threshold: float = DEFAULT_MATCH_THRESHOLD,
        vlm_timeout_sec: float = VLM_TIMEOUT_SEC,
        use_vlm: bool = True,
    ) -> None:
        if not expected_phrases:
            raise ValueError("expected_phrases must not be empty")
        if not (0.0 < match_threshold <= 1.0):
            raise ValueError("match_threshold must be in (0, 1]")
        if vlm_timeout_sec <= 0:
            raise ValueError("vlm_timeout_sec must be positive")
        self.expected_phrases = list(expected_phrases)
        self.ocr_engine = ocr_engine
        self.vlm_assist = vlm_assist if vlm_assist is not None else SolarVlmAssist()
        self.match_threshold = match_threshold
        self.vlm_timeout_sec = vlm_timeout_sec
        self.use_vlm = use_vlm

    def evaluate(self, source: ImageSource) -> dict[str, Any]:
        """ImageSource 프레임을 OCR(+선택 VLM)로 읽어 PASS/FAIL 결과를 반환한다."""
        image = source.load()
        engine = self.ocr_engine if self.ocr_engine is not None else create_default_ocr_engine()
        ocr_texts = engine.read_texts(image)

        phrase_results: list[dict[str, Any]] = []
        for expected in self.expected_phrases:
            best_text, ratio = best_ocr_match(expected, ocr_texts)
            phrase_results.append(
                {
                    "expected": expected,
                    "best_ocr": best_text,
                    "match_ratio": round(ratio, 4),
                    "passed": ratio >= self.match_threshold,
                }
            )
        ocr_pass = all(item["passed"] for item in phrase_results)

        vlm_info: dict[str, Any]
        decision_source: DecisionSource

        if not self.use_vlm:
            vlm_info = {
                "status": "skipped",
                "semantic_match": None,
                "detail": "use_vlm=False",
            }
            decision_source = "ocr_only"
            verdict: Literal["PASS", "FAIL"] = "PASS" if ocr_pass else "FAIL"
        else:
            vlm_info = self._call_vlm_with_timeout(ocr_texts)
            status = vlm_info.get("status")
            if status == "timeout":
                # 카드 12: VLM 타임아웃 → OCR만 100% 신뢰
                decision_source = "ocr_only_after_vlm_timeout"
                verdict = "PASS" if ocr_pass else "FAIL"
            elif status in ("unavailable", "skipped"):
                decision_source = "ocr_only"
                verdict = "PASS" if ocr_pass else "FAIL"
            else:
                # text_only / ok: OCR + VLM 의미 일치를 융합
                semantic = bool(vlm_info.get("semantic_match"))
                decision_source = "ocr_plus_vlm"
                verdict = "PASS" if (ocr_pass and semantic) else "FAIL"

        return {
            "verdict": verdict,
            "match_threshold": self.match_threshold,
            "ocr_texts": ocr_texts,
            "phrase_results": phrase_results,
            "ocr_pass": ocr_pass,
            "vlm": vlm_info,
            "decision_source": decision_source,
            "vlm_timeout_sec": self.vlm_timeout_sec,
            "notes": (
                "T-009: Solar vision multimodal not supported; "
                "primary path is local OCR."
            ),
        }

    def _call_vlm_with_timeout(self, ocr_texts: list[str]) -> dict[str, Any]:
        """VLM 보조를 ``vlm_timeout_sec`` 안에 호출하고, 초과 시 timeout 상태를 반환한다."""

        def _invoke() -> dict[str, Any]:
            return self.vlm_assist.semantic_check(
                ocr_texts=ocr_texts,
                expected_phrases=self.expected_phrases,
            )

        # wait=False: 타임아웃 후에도 slow stub thread 종료를 기다리지 않는다.
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            future = pool.submit(_invoke)
            try:
                return future.result(timeout=self.vlm_timeout_sec)
            except FuturesTimeout:
                return {
                    "status": "timeout",
                    "semantic_match": None,
                    "detail": (
                        f"VLM assist exceeded {self.vlm_timeout_sec}s; "
                        "falling back to OCR-only (Card 12)."
                    ),
                }
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    def save_readout(self, path: Path | str, result: dict[str, Any] | None = None) -> Path:
        """추출 텍스트 매칭율을 JSON 검증 기록으로 저장한다."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = result if result is not None else {}
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path
