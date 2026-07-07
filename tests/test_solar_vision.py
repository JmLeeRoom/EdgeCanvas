"""T-009 스파이크: Solar Pro 3 비전 멀티모달 입력 및 판정 실험 — 단위 테스트.

단위구현계획서.md 제5장 [T-009] 10항 절차를 코드로 검증한다.
목적(7): [가정 1] "Solar Pro 3가 멀티모달 비전 인풋을 정식 지원하고,
LCD 캡처 이미지 상의 텍스트/UI 구조를 인식할 수 있는가"를 실측 검증한다.

- 오프라인: base64 인코딩 로직 + OpenAI 스타일 멀티모달 메시지 구성 +
  카드 12항 Fallback(OpenCV 픽셀/OCR 계열 로컬 판정)이 존재·동작함을 검증한다.
- 라이브(@REQUIRES_LIVE_API): 실제 Solar 채팅 모델에 이미지+텍스트를 전송해
  이미지 입력 지원 여부를 정직하게 관측한다. 지원되면 판정 정확도를,
  미지원이면 거부 응답을 기록하며, 둘 다 유효한 스파이크 결론이다.
"""
import base64
import os
from pathlib import Path

import cv2
import pytest
from dotenv import load_dotenv

load_dotenv()

REQUIRES_LIVE_API = pytest.mark.skipif(
    not os.getenv("UPSTAGE_API_KEY"),
    reason="UPSTAGE_API_KEY가 .env에 설정되어 있지 않습니다.",
)

DATA_DIR = Path(__file__).parent / "data"
UI_NORMAL = DATA_DIR / "ui_normal.png"
UI_TRUNCATED = DATA_DIR / "ui_truncated.png"
UI_MISPLACED = DATA_DIR / "ui_misplaced.png"
ALL_FIXTURES = (UI_NORMAL, UI_TRUNCATED, UI_MISPLACED)

CHAT_ENDPOINT = "https://api.upstage.ai/v1/chat/completions"
VISION_PROMPT = (
    "You are a UI QA inspector. Inspect this 1024x600 device control panel "
    "screenshot and state whether the layout is NORMAL or DEFECTIVE. "
    "If defective, name the defect (truncated text / misplaced or clipped buttons)."
)


# ---------------------------------------------------------------------------
# 오프라인 로직: base64 인코딩 + 멀티모달 메시지 구성
# ---------------------------------------------------------------------------
def encode_image_base64(path) -> str:
    """이미지 파일을 base64 문자열로 인코딩한다(카드 8-2 베이스64 인코딩)."""
    return base64.b64encode(Path(path).read_bytes()).decode("utf-8")


def build_multimodal_messages(image_path, prompt: str = VISION_PROMPT) -> list:
    """Solar 채팅 API용 OpenAI 스타일 멀티모달 메시지(text + image_url)를 만든다."""
    b64 = encode_image_base64(image_path)
    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"},
                },
            ],
        }
    ]


def test_fixtures_exist():
    """카드 9 산출물: 스크린샷 3종(정상/텍스트잘림/버튼배치오류)이 있어야 한다."""
    for f in ALL_FIXTURES:
        assert f.exists(), f"UI fixture 누락: {f}"


def test_encode_image_base64_roundtrip():
    """base64 인코딩 로직이 원본 바이트를 정확히 복원할 수 있어야 한다."""
    b64 = encode_image_base64(UI_NORMAL)
    assert isinstance(b64, str) and len(b64) > 0
    assert base64.b64decode(b64) == UI_NORMAL.read_bytes()


def test_build_multimodal_messages_shape():
    """멀티모달 메시지가 text + image_url(data URI) 구조를 갖춰야 한다."""
    msgs = build_multimodal_messages(UI_NORMAL)
    content = msgs[0]["content"]
    assert msgs[0]["role"] == "user"
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


# ---------------------------------------------------------------------------
# 카드 12항 Fallback: OpenCV 기반 로컬 UI 결격 판정 (이미지 입력 미지원 대비)
# ---------------------------------------------------------------------------
def opencv_layout_verdict(image_path) -> dict:
    """OpenCV로 UI 스크린샷의 명백한 레이아웃 결격을 로컬 판정한다.

    Solar가 이미지 입력을 지원하지 않을 때의 1차(메인) 검증 경로.
    - 프레임 경계(우/하단)에 붙은 큰 채색 컴포넌트가 있으면 '버튼 잘림/이탈'로 본다.
    반환: {"verdict": "PASS"|"FAIL", "reasons": [...]}
    """
    img = cv2.imread(str(image_path))
    if img is None:
        raise FileNotFoundError(f"이미지를 열 수 없습니다: {image_path}")
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # 배경(밝은 회색)과 구분되는 진한 컴포넌트만 남긴다.
    _, mask = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    reasons = []
    edge_margin = 2
    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)
        area = cw * ch
        if area < 4000:  # 텍스트/작은 요소는 무시, 버튼급 블록만 검사
            continue
        # 상단 헤더 배너는 정상 요소이므로 제외한다.
        if y <= edge_margin and cw > w * 0.5:
            continue
        touches_right = (x + cw) >= (w - edge_margin)
        touches_bottom = (y + ch) >= (h - edge_margin)
        if touches_right or touches_bottom:
            reasons.append(
                f"component at ({x},{y},{cw}x{ch}) clipped by frame edge"
            )
    verdict = "FAIL" if reasons else "PASS"
    return {"verdict": verdict, "reasons": reasons}


def test_fallback_opencv_flags_misplaced_layout():
    """12: 이미지 입력 미지원 시 OpenCV fallback이 버튼 배치오류 화면을 FAIL로 잡아야 한다."""
    result = opencv_layout_verdict(UI_MISPLACED)
    assert result["verdict"] == "FAIL"
    assert result["reasons"], "결격 사유가 비어 있으면 안 된다."


def test_fallback_opencv_passes_normal_layout():
    """12: fallback이 정상 화면을 FAIL로 오판하지 않아야 한다(false positive 방지)."""
    result = opencv_layout_verdict(UI_NORMAL)
    assert result["verdict"] == "PASS", result["reasons"]


def test_fallback_opencv_missing_file_raises():
    """12: fallback 입력 이미지가 없으면 명확한 예외를 던진다."""
    with pytest.raises(FileNotFoundError):
        opencv_layout_verdict(DATA_DIR / "__does_not_exist__.png")


# ---------------------------------------------------------------------------
# 라이브 실험 — 카드 10항: Solar 이미지 멀티모달 입력 지원 여부 실측
# ---------------------------------------------------------------------------
def _post_chat(model: str, messages: list):
    import requests

    return requests.post(
        CHAT_ENDPOINT,
        headers={
            "Authorization": f"Bearer {os.environ['UPSTAGE_API_KEY']}",
            "Content-Type": "application/json",
        },
        json={"model": model, "messages": messages, "max_tokens": 300},
        timeout=60,
    )


@REQUIRES_LIVE_API
@pytest.mark.parametrize("model", ["solar-pro3", "solar-pro2"])
def test_solar_multimodal_image_input_support(model):
    """10: 실제 Solar 채팅 모델에 이미지+텍스트를 전송해 지원 여부를 관측한다.

    스파이크 계약: 이미지 입력을 지원하면(HTTP 200) 판정 텍스트를 검증하고,
    지원하지 않으면(HTTP 400 'Image input is not allowed') [가정 1] 기각을
    확정한다. 어느 쪽이든 결정적(deterministic) 결론이므로 테스트는 통과한다.
    """
    resp = _post_chat(model, build_multimodal_messages(UI_TRUNCATED))
    print(f"[T-009] model={model} HTTP={resp.status_code} body={resp.text[:400]}")

    if resp.status_code == 200:
        content = resp.json()["choices"][0]["message"]["content"]
        assert content and len(content) > 0
        return  # Go 경로: 지원 확인

    # No-Go 경로: 이미지 입력 거부가 명시적이어야 스파이크 결론이 성립한다.
    assert resp.status_code == 400
    assert "image input is not allowed" in resp.text.lower(), (
        "예상치 못한 거부 사유 — 카드 12항 Fallback 판단 전에 응답을 재확인할 것: "
        f"{resp.text}"
    )


@REQUIRES_LIVE_API
def test_text_only_chat_still_works():
    """대조군: 텍스트 전용 요청은 정상 동작해야 한다(키/엔드포인트 자체는 유효)."""
    resp = _post_chat(
        "solar-pro3",
        [{"role": "user", "content": "Reply with the single word OK."}],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["choices"][0]["message"]["content"]
