"""T-603: OpenCV 기반 위젯 크기/위치 정량 PASS/FAIL 판정기.

단위구현계획서.md 제5장 [T-603] 8항 구현 내용을 따른다.
T-802 시뮬레이터 스크린샷(1024×600 PNG)과 T-303 위젯 트리(매니페스트에
bbox가 포함된 형태)를 대조해 ±5% 허용 오차로 PASS/FAIL을 반환한다.

검출 경로
---------
1) 기본: cv2.Canny + cv2.findContours 로 사각형 위젯 영역 추출
2) 폴백(카드 12항): 조도/난반사로 윤곽이 깨질 때 cv2.adaptiveThreshold

ImageSource
-----------
- SimCaptureProvider: T-802 캡처 PNG 경로
- CameraCaptureProvider: Phase HW(T-602)용 스텁 — 경로가 있으면 로드, 없으면 NotImplemented
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Literal

import cv2
import numpy as np

# coding-standards: 위젯 좌표 허용 오차 ±5%
DEFAULT_TOLERANCE = 0.05

# 텍스트/노이즈 제외 — T-009 fallback과 동일한 버튼급 면적 하한
_MIN_WIDGET_AREA = 4000

DetectMethod = Literal["canny", "adaptive", "auto"]


class ImageSource(ABC):
    """Vision 입력 추상화 — 시뮬 PNG / 실기 카메라 캡처를 동일 인터페이스로 공급."""

    @abstractmethod
    def load(self) -> np.ndarray:
        """BGR uint8 이미지(H×W×3)를 반환한다."""


class SimCaptureProvider(ImageSource):
    """T-802 `captured_sim.png`(또는 fixture PNG)를 읽는 Phase A 입력."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def load(self) -> np.ndarray:
        image = cv2.imread(str(self.path))
        if image is None:
            raise FileNotFoundError(f"시뮬 캡처 이미지를 열 수 없습니다: {self.path}")
        return image


class CameraCaptureProvider(ImageSource):
    """T-602 실기 카메라 입력 스텁.

    Phase A에서는 파일 경로가 주어지면 로드만 지원하고,
    실제 카메라 연동(HW)은 경로 없이 호출 시 NotImplementedError를 낸다.
    """

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else None

    def load(self) -> np.ndarray:
        if self.path is None:
            raise NotImplementedError(
                "CameraCaptureProvider: 실기 카메라 캡처는 Phase HW(T-602)에서 연동합니다. "
                "지금은 보정 이미지 경로를 넘겨 파일 로드만 가능합니다."
            )
        image = cv2.imread(str(self.path))
        if image is None:
            raise FileNotFoundError(f"카메라 캡처 이미지를 열 수 없습니다: {self.path}")
        return image


def flatten_expected_widgets(layout: dict) -> list[dict[str, Any]]:
    """T-303 스타일 위젯 트리에서 bbox가 있는 노드를 평탄화한다.

    루트 screen은 전체 캔버스이므로 매칭 대상에서 제외한다.
    """
    widgets: list[dict[str, Any]] = []

    def walk(node: dict) -> None:
        bbox = node.get("bbox")
        wtype = node.get("type")
        if bbox is not None and wtype != "screen":
            x, y, w, h = (int(v) for v in bbox)
            widgets.append(
                {
                    "var": node.get("var"),
                    "type": wtype,
                    "bbox": (x, y, w, h),
                }
            )
        for child in node.get("children") or []:
            walk(child)

    walk(layout)
    return widgets


class WidgetLocationEvaluator:
    """기대 레이아웃 bbox와 OpenCV 검출 bbox를 ±tolerance로 정량 비교한다."""

    def __init__(self, layout: dict, tolerance: float = DEFAULT_TOLERANCE) -> None:
        if tolerance <= 0:
            raise ValueError("tolerance must be positive")
        self.layout = layout
        self.tolerance = tolerance
        self.expected = flatten_expected_widgets(layout)

    # ------------------------------------------------------------------ #
    # 검출
    # ------------------------------------------------------------------ #
    def detect_widget_bboxes(
        self,
        image: np.ndarray,
        method: DetectMethod = "auto",
        *,
        allow_adaptive_fallback: bool = True,
        min_area: int = _MIN_WIDGET_AREA,
    ) -> list[tuple[int, int, int, int]]:
        """사각형 위젯 바운딩 박스 목록 ``[(x, y, w, h), ...]`` 을 반환한다."""
        if method == "canny":
            boxes = self._detect_canny(image, min_area=min_area)
            # 카드 12항: Canny 윤곽이 깨지면 adaptiveThreshold 폴백
            if allow_adaptive_fallback and not boxes:
                return self._detect_adaptive(image, min_area=min_area)
            return boxes
        if method == "adaptive":
            return self._detect_adaptive(image, min_area=min_area)

        # auto: Canny+findContours 우선, 기대 위젯 대비 부족하면 adaptiveThreshold 폴백
        boxes = self._detect_canny(image, min_area=min_area)
        if allow_adaptive_fallback and len(boxes) < max(1, len(self.expected)):
            adaptive = self._detect_adaptive(image, min_area=min_area)
            boxes = self._merge_boxes(boxes, adaptive)
        return boxes

    def _detect_canny(
        self, image: np.ndarray, *, min_area: int
    ) -> list[tuple[int, int, int, int]]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        # 프레임 경계에 붙는 위젯(헤더) 윤곽이 잘리지 않도록 1px 패딩
        padded = cv2.copyMakeBorder(gray, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=255)
        blurred = cv2.GaussianBlur(padded, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 150)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        edges = cv2.dilate(edges, kernel, iterations=1)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        # 패딩 좌표 → 원본 좌표로 보정한 뒤 박스 필터링
        h, w = gray.shape
        boxes: list[tuple[int, int, int, int]] = []
        for contour in contours:
            x, y, cw, ch = cv2.boundingRect(contour)
            x, y = max(x - 1, 0), max(y - 1, 0)
            cw = min(cw, w - x)
            ch = min(ch, h - y)
            area = cw * ch
            if area < min_area:
                continue
            if cw >= w * 0.95 and ch >= h * 0.95:
                continue
            boxes.append((int(x), int(y), int(cw), int(ch)))
        boxes.sort(key=lambda b: (b[1], b[0]))
        return boxes

    def _detect_adaptive(
        self, image: np.ndarray, *, min_area: int
    ) -> list[tuple[int, int, int, int]]:
        """카드 12항: 고정 threshold 대신 적응형 이진화로 위젯 마스크를 만든다."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        binary = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            35,
            5,
        )
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        return self._contours_to_boxes(contours, image.shape[:2], min_area=min_area)

    @staticmethod
    def _iou(
        a: tuple[int, int, int, int], b: tuple[int, int, int, int]
    ) -> float:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        x1, y1 = max(ax, bx), max(ay, by)
        x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        if inter <= 0:
            return 0.0
        union = aw * ah + bw * bh - inter
        return inter / union if union else 0.0

    def _merge_boxes(
        self, *groups: list[tuple[int, int, int, int]]
    ) -> list[tuple[int, int, int, int]]:
        """중복 bbox는 IoU>0.5일 때 면적이 큰 쪽을 남긴다."""
        merged: list[tuple[int, int, int, int]] = []
        for group in groups:
            merged.extend(group)
        merged.sort(key=lambda b: b[2] * b[3], reverse=True)
        kept: list[tuple[int, int, int, int]] = []
        for box in merged:
            if any(self._iou(box, other) > 0.5 for other in kept):
                continue
            kept.append(box)
        kept.sort(key=lambda b: (b[1], b[0]))
        return kept

    @staticmethod
    def _contours_to_boxes(
        contours: Any,
        shape_hw: tuple[int, int],
        *,
        min_area: int,
    ) -> list[tuple[int, int, int, int]]:
        h, w = shape_hw
        boxes: list[tuple[int, int, int, int]] = []
        for contour in contours:
            x, y, cw, ch = cv2.boundingRect(contour)
            area = cw * ch
            if area < min_area:
                continue
            # 거의 전체 프레임인 컨투어는 제외(배경)
            if cw >= w * 0.95 and ch >= h * 0.95:
                continue
            boxes.append((int(x), int(y), int(cw), int(ch)))
        boxes.sort(key=lambda b: (b[1], b[0]))
        return boxes

    # ------------------------------------------------------------------ #
    # 매칭 / 판정
    # ------------------------------------------------------------------ #
    def evaluate(self, source: ImageSource) -> dict[str, Any]:
        """ImageSource 프레임을 기대 레이아웃과 비교해 PASS/FAIL 결과를 반환한다."""
        image = source.load()
        detected = self.detect_widget_bboxes(image, method="auto")
        matches: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        used: set[int] = set()

        for expected in self.expected:
            best_idx, _best_score = self._best_match(expected["bbox"], detected, used)
            if best_idx is None:
                failed.append(
                    {
                        "var": expected["var"],
                        "type": expected["type"],
                        "expected": expected["bbox"],
                        "reason": "missing",
                    }
                )
                continue

            used.add(best_idx)
            det = detected[best_idx]
            within, metrics = self._within_tolerance(expected["bbox"], det)
            record = {
                "var": expected["var"],
                "type": expected["type"],
                "expected": expected["bbox"],
                "detected": det,
                "metrics": metrics,
            }
            if within:
                matches.append(record)
            else:
                record["reason"] = "offset_or_size"
                failed.append(record)

        verdict = "PASS" if not failed else "FAIL"
        return {
            "verdict": verdict,
            "tolerance": self.tolerance,
            "matched": matches,
            "failed_widgets": failed,
            "detected_count": len(detected),
            "detected_bboxes": detected,
            "expected_count": len(self.expected),
        }

    def _best_match(
        self,
        expected: tuple[int, int, int, int],
        detected: list[tuple[int, int, int, int]],
        used: set[int],
    ) -> tuple[int | None, float]:
        ex, ey, ew, eh = expected
        ecx, ecy = ex + ew / 2.0, ey + eh / 2.0
        best_idx: int | None = None
        best_dist = float("inf")
        for idx, (x, y, w, h) in enumerate(detected):
            if idx in used:
                continue
            cx, cy = x + w / 2.0, y + h / 2.0
            dist = ((cx - ecx) ** 2 + (cy - ecy) ** 2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best_idx = idx
        # 매칭 후보가 기대 대각선의 50%를 넘으면 소실로 간주
        diag = (ew**2 + eh**2) ** 0.5
        if best_idx is None or best_dist > max(diag * 0.5, 1.0):
            return None, best_dist
        return best_idx, best_dist

    def _within_tolerance(
        self,
        expected: tuple[int, int, int, int],
        detected: tuple[int, int, int, int],
    ) -> tuple[bool, dict[str, float]]:
        ex, ey, ew, eh = expected
        dx, dy, dw, dh = detected
        ecx, ecy = ex + ew / 2.0, ey + eh / 2.0
        dcx, dcy = dx + dw / 2.0, dy + dh / 2.0

        # 허용 반경: 기대 가로/세로의 ±tolerance (coding-standards ±5%)
        max_dx = self.tolerance * ew
        max_dy = self.tolerance * eh
        err_x = abs(dcx - ecx)
        err_y = abs(dcy - ecy)
        err_w = abs(dw - ew) / max(ew, 1)
        err_h = abs(dh - eh) / max(eh, 1)

        metrics = {
            "center_err_x": err_x,
            "center_err_y": err_y,
            "width_err_ratio": err_w,
            "height_err_ratio": err_h,
            "max_dx": max_dx,
            "max_dy": max_dy,
        }
        within = (
            err_x <= max_dx
            and err_y <= max_dy
            and err_w <= self.tolerance
            and err_h <= self.tolerance
        )
        return within, metrics

    # ------------------------------------------------------------------ #
    # 검증 산출물
    # ------------------------------------------------------------------ #
    def save_overlay(
        self,
        source: ImageSource,
        path: Path | str,
        *,
        result: dict[str, Any] | None = None,
    ) -> Path:
        """기대(초록)/검출(파랑)/실패(빨강) bbox를 중첩한 PNG를 저장한다."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        image = source.load().copy()
        if result is None:
            result = self.evaluate(source)

        detected = result.get("detected_bboxes") or self.detect_widget_bboxes(image)

        for x, y, w, h in detected:
            cv2.rectangle(image, (x, y), (x + w, y + h), (255, 128, 0), 2)

        for widget in self.expected:
            x, y, w, h = widget["bbox"]
            cv2.rectangle(image, (x, y), (x + w, y + h), (0, 200, 0), 2)
            label = str(widget.get("var") or "")
            if label:
                cv2.putText(
                    image,
                    label,
                    (x + 4, max(y - 6, 12)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    (0, 180, 0),
                    1,
                    cv2.LINE_AA,
                )

        for failed in result.get("failed_widgets") or []:
            exp = failed.get("expected")
            if exp:
                x, y, w, h = exp
                cv2.rectangle(image, (x, y), (x + w, y + h), (0, 0, 255), 2)

        cv2.imwrite(str(path), image)
        return path
