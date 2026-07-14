"""T-603: OpenCV 위젯 크기/위치 PASS/FAIL 판정기 — 단위 테스트.

단위구현계획서.md 제5장 [T-603] 10항 절차를 코드로 검증한다.
- 준비: 모형 LCD UI 캡처(ui_normal / ui_misplaced)와 타겟 레이아웃 JSON.
- 실행: pytest tests/test_vision_evaluator.py -v -s
- 통과 기준: ±5% 이내면 PASS, 오프셋/소실이면 FAIL.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from src.verifier.vision_evaluator import (
    CameraCaptureProvider,
    SimCaptureProvider,
    WidgetLocationEvaluator,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "tests" / "data"
UI_NORMAL = DATA_DIR / "ui_normal.png"
UI_MISPLACED = DATA_DIR / "ui_misplaced.png"
LAYOUT_JSON = DATA_DIR / "ui_layout_expected.json"
VERIFY_OVERLAY = REPO_ROOT / "docs" / "verification" / "T-603_match_contours.png"


@pytest.fixture
def expected_layout() -> dict:
    return json.loads(LAYOUT_JSON.read_text(encoding="utf-8"))


@pytest.fixture
def evaluator(expected_layout: dict) -> WidgetLocationEvaluator:
    return WidgetLocationEvaluator(expected_layout, tolerance=0.05)


def test_normal_layout_passes_within_tolerance(evaluator: WidgetLocationEvaluator):
    """정상 배치 이미지 → ±5% 이내 PASS."""
    source = SimCaptureProvider(UI_NORMAL)
    result = evaluator.evaluate(source)
    assert result["verdict"] == "PASS", result
    assert result["failed_widgets"] == []


def test_misplaced_layout_fails(evaluator: WidgetLocationEvaluator):
    """오프셋/겹침/프레임 이탈 이미지 → FAIL."""
    source = SimCaptureProvider(UI_MISPLACED)
    result = evaluator.evaluate(source)
    assert result["verdict"] == "FAIL"
    assert result["failed_widgets"], "실패 위젯 목록이 비어 있으면 안 된다."


def test_missing_widget_fails(expected_layout: dict):
    """기대 위젯이 이미지에 없으면 FAIL."""
    layout = json.loads(json.dumps(expected_layout))
    layout["children"].append(
        {
            "var": "ghost_btn",
            "type": "button",
            "bbox": [50, 300, 120, 60],
            "children": [],
            "event_handlers": [],
        }
    )
    evaluator = WidgetLocationEvaluator(layout, tolerance=0.05)
    result = evaluator.evaluate(SimCaptureProvider(UI_NORMAL))
    assert result["verdict"] == "FAIL"
    assert any(w.get("var") == "ghost_btn" for w in result["failed_widgets"])


def test_detect_widgets_via_canny_contours(evaluator: WidgetLocationEvaluator):
    """Canny + findContours 경로로 사각형 위젯 bbox를 추출한다."""
    image = cv2.imread(str(UI_NORMAL))
    assert image is not None
    boxes = evaluator.detect_widget_bboxes(image, method="canny")
    assert len(boxes) >= 2, f"버튼급 컨투어가 부족: {boxes}"
    # OK / Cancel 근처(우하단)에 검출이 있어야 한다.
    lower_right = [b for b in boxes if b[0] >= 500 and b[1] >= 400]
    assert len(lower_right) >= 2, lower_right


def test_adaptive_threshold_fallback_on_glare(tmp_path: Path, expected_layout: dict):
    """카드 12: 조도 불균일/난반사에서 Canny가 깨지고 adaptiveThreshold가 위젯을 잡는다.

    가로 사인파 + 세로 그라데이션 배경에 약한 대비 위젯을 올려 Canny 단독은 실패하고,
    adaptive 경로는 버튼급 bbox를 확보하는지 검증한다.
    """
    img = np.zeros((600, 1024, 3), dtype=np.uint8)
    ys = np.arange(600, dtype=np.float64)[:, None]
    xs = np.arange(1024, dtype=np.float64)[None, :]
    levels = np.clip(120 + 50 * np.sin(xs / 40.0) + 40 * (ys / 599.0), 0, 255).astype(
        np.uint8
    )
    img[:, :, 0] = levels
    img[:, :, 1] = levels
    img[:, :, 2] = levels

    for (x, y, w, h), delta in [
        ((0, 0, 1024, 71), 25),
        ((620, 470, 171, 81), 30),
        ((810, 470, 171, 81), 30),
    ]:
        patch = img[y : y + h, x : x + w].astype(np.int16) - delta
        img[y : y + h, x : x + w] = np.clip(patch, 0, 255).astype(np.uint8)

    glare_path = tmp_path / "ui_glare.png"
    cv2.imwrite(str(glare_path), img)

    evaluator = WidgetLocationEvaluator(expected_layout, tolerance=0.08)
    canny_boxes = evaluator.detect_widget_bboxes(
        img, method="canny", allow_adaptive_fallback=False
    )
    adaptive_boxes = evaluator.detect_widget_bboxes(img, method="adaptive")

    assert len(canny_boxes) == 0, f"Canny가 깨져야 함: {canny_boxes}"
    assert len(adaptive_boxes) >= 2, adaptive_boxes
    lower_right = [b for b in adaptive_boxes if b[0] >= 500 and b[1] >= 400]
    assert len(lower_right) >= 2, lower_right

    result = evaluator.evaluate(SimCaptureProvider(glare_path))
    # 폴백을 포함한 기본 evaluate 경로로 판정이 완료되어야 한다(예외 없이).
    assert result["verdict"] in ("PASS", "FAIL")
    assert result["detected_count"] >= 2


def test_image_source_sim_and_camera_smoke():
    """ImageSource 추상화: SimCaptureProvider / CameraCaptureProvider 스모크."""
    sim = SimCaptureProvider(UI_NORMAL)
    frame = sim.load()
    assert isinstance(frame, np.ndarray)
    assert frame.shape[0] == 600 and frame.shape[1] == 1024

    # Phase A: 카메라 제공자는 경로가 있으면 파일 로드(스텁 래퍼), 없으면 NotImplemented.
    cam_file = CameraCaptureProvider(UI_NORMAL)
    cam_frame = cam_file.load()
    assert cam_frame.shape == frame.shape

    cam_stub = CameraCaptureProvider(None)
    with pytest.raises(NotImplementedError):
        cam_stub.load()


def test_save_match_contours_overlay(evaluator: WidgetLocationEvaluator):
    """검증 기록: 검출 bbox 중첩 오버레이를 docs/verification에 저장."""
    VERIFY_OVERLAY.parent.mkdir(parents=True, exist_ok=True)
    source = SimCaptureProvider(UI_NORMAL)
    result = evaluator.evaluate(source)
    out = evaluator.save_overlay(source, VERIFY_OVERLAY, result=result)
    assert out.is_file()
    assert out.stat().st_size > 0
    loaded = cv2.imread(str(out))
    assert loaded is not None
    assert loaded.shape[1] == 1024 and loaded.shape[0] == 600
