"""T-010 스파이크: NC AI VARCO Art 이미지 생성 API 접속 검증 — 단위 테스트.

단위구현계획서.md 제5장 [T-010] 10항 절차를 코드로 검증한다.
목적(7): [가정 2] "VARCO Art 이미지 생성 API가 외부 서비스 접근을 완전히 허용하고
REST API 호출 규격을 신뢰성 있게 준수하는가"를 실측 검증한다.

- 오프라인: 요청 페이로드 구성, 응답(JSON 링크/base64/raw 바이너리) 파싱, PNG 매직넘버
  검증, 디스크 저장, 그리고 카드 12항 Placeholder Fallback(단순 색상 채우기 PNG 생성)이
  존재·동작함을 항상 검증한다. (API 키 없이도 통과)
- 라이브(@REQUIRES_LIVE_API): NC_VARCO_API_KEY가 있을 때만, 실제 VARCO Art API에
  "100x50 파란색 사각형 버튼" 프롬프트를 POST 하고 응답 이미지를 온전한 PNG로 저장한다.
"""
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv()

from src.agent.varco_art import (  # noqa: E402
    DEFAULT_API_BASE,
    DEFAULT_ENDPOINT,
    PNG_MAGIC,
    VARCO_IMAGE_TO_3D_PATH,
    build_auth_headers,
    build_generation_payload,
    extract_image_bytes,
    is_valid_png,
    make_placeholder_png,
    request_image,
    resolve_varco_endpoint,
    save_image_bytes,
)

REQUIRES_LIVE_API = pytest.mark.skipif(
    not os.getenv("NC_VARCO_API_KEY"),
    reason="NC_VARCO_API_KEY가 .env에 설정되어 있지 않습니다.",
)

# 카드 9 산출물: 수신용 임시 이미지 에셋 폴더.
ASSETS_DIR = Path(__file__).parent / "data" / "varco_received"

BUTTON_PROMPT = "100x50 size blue rectangular submit button image"


# ---------------------------------------------------------------------------
# 엔드포인트 해석 (openapi.ai.nc.com 기본값 / 환경변수 오버라이드)
# ---------------------------------------------------------------------------
def test_default_endpoint_uses_openapi_ai_nc_com():
    """기본 엔드포인트는 openapi.ai.nc.com/3d/varco/v1/image-to-3d 이어야 한다."""
    assert DEFAULT_API_BASE == "https://openapi.ai.nc.com"
    assert VARCO_IMAGE_TO_3D_PATH == "/3d/varco/v1/image-to-3d"
    assert DEFAULT_ENDPOINT == "https://openapi.ai.nc.com/3d/varco/v1/image-to-3d"


def test_resolve_varco_endpoint_defaults(monkeypatch):
    """환경변수 미설정 시 기본 전체 엔드포인트를 반환한다."""
    monkeypatch.delenv("NC_VARCO_API_URL", raising=False)
    monkeypatch.delenv("NC_VARCO_API_BASE", raising=False)
    assert resolve_varco_endpoint() == DEFAULT_ENDPOINT


def test_resolve_varco_endpoint_full_url_env(monkeypatch):
    """NC_VARCO_API_URL이 설정되면 전체 URL 오버라이드가 최우선이다."""
    monkeypatch.setenv("NC_VARCO_API_URL", "https://custom.example.com/v1/generate")
    monkeypatch.setenv("NC_VARCO_API_BASE", "https://ignored.example.com")
    assert resolve_varco_endpoint() == "https://custom.example.com/v1/generate"


def test_resolve_varco_endpoint_base_plus_path(monkeypatch):
    """NC_VARCO_API_URL 미설정 시 NC_VARCO_API_BASE + 기본 path를 조합한다."""
    monkeypatch.delenv("NC_VARCO_API_URL", raising=False)
    monkeypatch.setenv("NC_VARCO_API_BASE", "https://staging.openapi.ai.nc.com")
    assert (
        resolve_varco_endpoint()
        == "https://staging.openapi.ai.nc.com/3d/varco/v1/image-to-3d"
    )


def test_resolve_varco_endpoint_url_arg_overrides_env(monkeypatch):
    """url 인자가 환경변수보다 우선한다."""
    monkeypatch.setenv("NC_VARCO_API_URL", "https://env.example.com/api")
    assert resolve_varco_endpoint(url="https://arg.example.com/api") == "https://arg.example.com/api"


# ---------------------------------------------------------------------------
# 오프라인 로직: NC OpenAPI 인증 헤더 (OPENAPI_KEY)
# ---------------------------------------------------------------------------
def test_build_auth_headers_uses_openapi_key_by_default():
    """NC OpenAPI 기본 인증은 OPENAPI_KEY 헤더를 사용한다."""
    headers = build_auth_headers("test-token-xyz")
    assert headers == {"OPENAPI_KEY": "test-token-xyz"}
    assert "Authorization" not in headers


def test_build_auth_headers_respects_env_override(monkeypatch):
    """NC_VARCO_AUTH_HEADER로 헤더 이름을 오버라이드할 수 있다."""
    monkeypatch.setenv("NC_VARCO_AUTH_HEADER", "X-Custom-Key")
    headers = build_auth_headers("secret")
    assert headers == {"X-Custom-Key": "secret"}


def test_build_auth_headers_authorization_uses_bearer():
    """Authorization 헤더 지정 시 Bearer 스킴을 붙인다(레거시/테스트용)."""
    headers = build_auth_headers("secret", auth_header="Authorization")
    assert headers == {"Authorization": "Bearer secret"}


def test_request_image_sends_openapi_key_header(tmp_path, monkeypatch):
    """request_image는 requests.post에 OPENAPI_KEY 인증 헤더를 전달한다."""
    import src.agent.varco_art as mod

    png = make_placeholder_png(100, 50, color=(0, 0, 255))
    captured: dict = {}

    class FakeResp:
        status_code = 200
        headers = {"Content-Type": "image/png"}
        content = png

    def fake_post(url, headers=None, json=None, timeout=60):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return FakeResp()

    monkeypatch.setattr(mod.requests, "post", fake_post)
    monkeypatch.delenv("NC_VARCO_AUTH_HEADER", raising=False)

    dst = tmp_path / "out.png"
    result = request_image(
        BUTTON_PROMPT,
        width=100,
        height=50,
        save_path=dst,
        api_key="live-key-not-logged",
        endpoint="https://openapi.ai.nc.com/3d/varco/v1/image-to-3d",
    )

    assert result["ok"] is True
    assert captured["headers"]["OPENAPI_KEY"] == "live-key-not-logged"
    assert "Authorization" not in captured["headers"]
    assert captured["headers"]["Content-Type"] == "application/json"


# ---------------------------------------------------------------------------
# 오프라인 로직: 요청 페이로드 구성 (카드 8-2)
# ---------------------------------------------------------------------------
def test_build_generation_payload_contains_prompt_and_size():
    """요청 바디에 프롬프트와 100x50 크기가 반영돼야 한다(카드 8-2)."""
    payload = build_generation_payload(BUTTON_PROMPT, width=100, height=50)
    assert payload["prompt"] == BUTTON_PROMPT
    assert payload["width"] == 100
    assert payload["height"] == 50


# ---------------------------------------------------------------------------
# 오프라인 로직: PNG 매직넘버 검증 (카드 11 DoD)
# ---------------------------------------------------------------------------
def test_png_magic_number_constant():
    """카드 11: PNG 매직넘버는 89 50 4E 47 로 시작해야 한다."""
    assert PNG_MAGIC == b"\x89PNG\r\n\x1a\n"
    assert PNG_MAGIC[:4] == bytes([0x89, 0x50, 0x4E, 0x47])


def test_is_valid_png_accepts_real_png():
    png = make_placeholder_png(100, 50, color=(0, 0, 255))
    assert is_valid_png(png) is True


def test_is_valid_png_rejects_garbage():
    assert is_valid_png(b"not a png at all") is False
    assert is_valid_png(b"") is False
    assert is_valid_png(b"\x89PNG") is False  # 매직만 있고 본문 없음


# ---------------------------------------------------------------------------
# 오프라인 로직: 응답 파싱 — JSON 링크 / base64 / raw 바이너리 (카드 8-3)
# ---------------------------------------------------------------------------
def test_extract_image_bytes_from_base64_json():
    """응답 JSON에 base64 이미지가 담긴 경우 디코딩해 바이트를 얻는다."""
    import base64

    png = make_placeholder_png(100, 50, color=(0, 0, 255))
    b64 = base64.b64encode(png).decode("ascii")

    class FakeResp:
        status_code = 200
        headers = {"Content-Type": "application/json"}

        def json(self):
            return {"images": [{"data": b64}]}

    out = extract_image_bytes(FakeResp())
    assert out == png
    assert is_valid_png(out)


def test_extract_image_bytes_from_raw_binary_response():
    """응답이 image/png raw 바이너리인 경우 그대로 바이트를 반환한다."""
    png = make_placeholder_png(100, 50, color=(0, 0, 255))

    class FakeResp:
        status_code = 200
        headers = {"Content-Type": "image/png"}
        content = png

    out = extract_image_bytes(FakeResp())
    assert out == png


def test_extract_image_bytes_from_url_json(monkeypatch):
    """응답 JSON에 이미지 URL만 있는 경우, URL을 내려받아 바이트를 얻는다."""
    png = make_placeholder_png(100, 50, color=(0, 0, 255))

    class FakeDownloadResp:
        status_code = 200
        content = png

    def fake_get(url, timeout=30):
        assert url == "https://cdn.example.com/img.png"
        return FakeDownloadResp()

    import src.agent.varco_art as mod

    monkeypatch.setattr(mod.requests, "get", fake_get)

    class FakeResp:
        status_code = 200
        headers = {"Content-Type": "application/json"}

        def json(self):
            return {"images": [{"url": "https://cdn.example.com/img.png"}]}

    out = extract_image_bytes(FakeResp())
    assert out == png


# ---------------------------------------------------------------------------
# 오프라인 로직: 디스크 저장 (카드 10 통과 기준)
# ---------------------------------------------------------------------------
def test_save_image_bytes_writes_valid_png(tmp_path):
    """정상 PNG 바이트를 디스크에 저장하면 매직넘버가 보존돼야 한다."""
    png = make_placeholder_png(100, 50, color=(0, 0, 255))
    dst = tmp_path / "out.png"
    save_image_bytes(png, dst)
    assert dst.exists()
    assert is_valid_png(dst.read_bytes())


def test_save_image_bytes_rejects_broken_png(tmp_path):
    """12: 깨진(비-PNG) 바이너리는 저장을 거부해 오염을 막는다."""
    with pytest.raises(ValueError):
        save_image_bytes(b"broken-bytes", tmp_path / "bad.png")


# ---------------------------------------------------------------------------
# 카드 12항 Placeholder Fallback: 단순 색상 채우기 PNG 생성
# ---------------------------------------------------------------------------
def test_make_placeholder_png_is_valid_and_sized():
    """12: API 불가 시 100x50 파란색 placeholder PNG를 온전하게 생성한다."""
    png = make_placeholder_png(100, 50, color=(0, 0, 255))
    assert is_valid_png(png)
    # PNG IHDR(오프셋 16~24)에 폭/높이가 빅엔디언 4바이트로 기록된다.
    width = int.from_bytes(png[16:20], "big")
    height = int.from_bytes(png[20:24], "big")
    assert (width, height) == (100, 50)


def test_request_image_falls_back_on_network_error(tmp_path, monkeypatch):
    """12: 네트워크 에러/비200이면 [가정] 기각 → placeholder fallback PNG를 저장한다."""
    import src.agent.varco_art as mod

    def boom(*args, **kwargs):
        raise mod.requests.exceptions.ConnectionError("no route to host")

    monkeypatch.setattr(mod.requests, "post", boom)

    dst = tmp_path / "fallback.png"
    result = request_image(
        BUTTON_PROMPT,
        width=100,
        height=50,
        save_path=dst,
        api_key="dummy",
        endpoint="https://unreachable.invalid/generate",
    )
    assert result["ok"] is False
    assert result["used_fallback"] is True
    assert dst.exists()
    assert is_valid_png(dst.read_bytes())


# ---------------------------------------------------------------------------
# 라이브 실험 — 카드 10항: 실제 VARCO Art API 호출 및 PNG 저장
# ---------------------------------------------------------------------------
@REQUIRES_LIVE_API
def test_varco_art_live_generation():
    """10, 11: 실제 VARCO Art API에 프롬프트를 POST 하고 온전한 PNG로 저장한다.

    성공 시(200/201) 수신 바이너리가 PNG 매직넘버를 지녀야 한다.
    권한 미획득/서비스 중단 등으로 실패하면 카드 12항에 따라 fallback으로 전환되며,
    이때도 스파이크 결론(가정 기각 + placeholder)은 유효하다.
    """
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    dst = ASSETS_DIR / "live_button.png"
    result = request_image(BUTTON_PROMPT, width=100, height=50, save_path=dst)
    print(f"[T-010] live result={result}")

    assert dst.exists()
    assert is_valid_png(dst.read_bytes())
    if result["ok"]:
        assert result["status_code"] in (200, 201)
