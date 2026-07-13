"""T-010 스파이크: NC AI VARCO Art 이미지 생성 API 접속 검증.

단위구현계획서.md 제5장 [T-010] 8항 구현 내용을 따른다.
"100x50 파란색 사각형 전송 버튼 이미지" 프롬프트를 VARCO 이미지(3D) 생성 REST API에
`requests`로 POST 하고, 응답(JSON 링크/base64 또는 raw 바이너리)을 로컬 PNG로 저장한다.

기본 엔드포인트: ``https://openapi.ai.nc.com/3d/varco/v1/image-to-3d``
(다른 NC OpenAPI 예: ``https://openapi.ai.nc.com/mt/chat-content/v1/translate``)

카드 12항(Placeholder Fallback): 권한 미획득/서비스 중단 등 네트워크 에러 시 [가정]을
기각하고, 단순 색상 채우기 placeholder PNG를 로컬에서 생성해 파이프라인을 잇는다.

설정은 모두 환경변수로 읽는다(코딩표준: 키/엔드포인트를 코드·로그에 남기지 않는다):
- NC_VARCO_API_KEY  : 인증 토큰 (없으면 라이브 호출 스킵 → fallback)
- NC_VARCO_API_URL  : 전체 엔드포인트 URL 오버라이드 (최우선)
- NC_VARCO_API_BASE : 베이스 URL만 오버라이드 (``NC_VARCO_API_URL`` 미설정 시 path와 조합)
- NC_VARCO_MODEL    : 사용 모델 식별자(선택)
"""
from __future__ import annotations

import base64
import os
import struct
import zlib
from pathlib import Path

import requests

# 카드 11 DoD: PNG 매직 넘버 (89 50 4E 47 0D 0A 1A 0A).
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# NC OpenAPI (openapi.ai.nc.com) VARCO 이미지(3D) 생성 엔드포인트.
# 전체 URL·베이스 URL은 환경변수로 오버라이드 가능(아래 resolve_varco_endpoint 참고).
DEFAULT_API_BASE = "https://openapi.ai.nc.com"
VARCO_IMAGE_TO_3D_PATH = "/3d/varco/v1/image-to-3d"
DEFAULT_ENDPOINT = f"{DEFAULT_API_BASE}{VARCO_IMAGE_TO_3D_PATH}"


def resolve_varco_endpoint(
    url: str | None = None,
    base: str | None = None,
    path: str | None = None,
) -> str:
    """VARCO 이미지(3D) 생성 엔드포인트 URL을 인자·환경변수·기본값 순으로 결정한다.

    우선순위:
    1. ``url`` 인자 또는 ``NC_VARCO_API_URL`` (전체 URL 오버라이드)
    2. ``base``/``NC_VARCO_API_BASE`` + ``path``/``VARCO_IMAGE_TO_3D_PATH``
    3. ``DEFAULT_ENDPOINT``
    """
    full_url = url or os.getenv("NC_VARCO_API_URL")
    if full_url:
        return full_url.strip().rstrip("/")

    api_base = (base or os.getenv("NC_VARCO_API_BASE") or DEFAULT_API_BASE).strip().rstrip("/")
    api_path = path or VARCO_IMAGE_TO_3D_PATH
    if not api_path.startswith("/"):
        api_path = f"/{api_path}"
    return f"{api_base}{api_path}"


def build_generation_payload(
    prompt: str,
    *,
    width: int = 100,
    height: int = 50,
    model: str | None = None,
) -> dict:
    """VARCO Art 이미지 생성 요청 바디를 구성한다(카드 8-2).

    범용 이미지 생성 REST 규격(prompt + 크기)을 따르며, 서비스별 세부 필드는
    환경변수/인자로 확장 가능하도록 최소 형태로 둔다.
    """
    payload: dict = {"prompt": prompt, "width": width, "height": height}
    if model:
        payload["model"] = model
    return payload


def is_valid_png(data: bytes) -> bool:
    """바이트가 온전한 PNG 구조(매직넘버 + 최소 본문)를 갖는지 검사한다(카드 11).

    매직넘버 8바이트에 더해, IHDR 청크가 담길 최소 길이를 요구해 '매직만 있는'
    깨진 데이터를 걸러낸다.
    """
    return (
        isinstance(data, (bytes, bytearray))
        and len(data) >= len(PNG_MAGIC) + 12
        and bytes(data[: len(PNG_MAGIC)]) == PNG_MAGIC
    )


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    """길이 + 태그 + 데이터 + CRC32로 PNG 청크 1개를 직렬화한다."""
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def make_placeholder_png(width: int, height: int, color=(0, 0, 255)) -> bytes:
    """단색 채우기 placeholder PNG를 순수 파이썬(stdlib)으로 생성한다(카드 12).

    Pillow 등 외부 이미지 라이브러리 없이 zlib만으로 RGB PNG를 인코딩한다.
    """
    r, g, b = color
    row = bytes((r, g, b)) * width
    # 각 스캔라인 앞에 필터 타입 바이트(0: None)를 붙인다.
    raw = b"".join(b"\x00" + row for _ in range(height))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8bit, RGB
    return (
        PNG_MAGIC
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(raw, 9))
        + _png_chunk(b"IEND", b"")
    )


def extract_image_bytes(resp) -> bytes:
    """API 응답에서 이미지 바이트를 뽑아낸다(카드 8-3).

    지원 형태:
    1. raw 바이너리 응답(Content-Type: image/*) → `resp.content` 그대로.
    2. JSON 내 base64 이미지(`images[].data` / `data` / `b64_json`) → 디코딩.
    3. JSON 내 이미지 URL(`images[].url` / `url` / `image_url`) → GET 다운로드.
    """
    content_type = (resp.headers or {}).get("Content-Type", "")
    if content_type.startswith("image/"):
        return resp.content

    body = resp.json()
    item = body
    images = body.get("images") if isinstance(body, dict) else None
    if isinstance(images, list) and images:
        item = images[0]

    if isinstance(item, dict):
        for b64_key in ("data", "b64_json", "image_base64"):
            if item.get(b64_key):
                return base64.b64decode(item[b64_key])
        for url_key in ("url", "image_url", "link"):
            if item.get(url_key):
                dl = requests.get(item[url_key], timeout=30)
                return dl.content

    raise ValueError("응답에서 이미지 데이터를 찾을 수 없습니다.")


def save_image_bytes(data: bytes, path: str | Path) -> Path:
    """이미지 바이트를 PNG로 디스크에 저장한다(카드 10 통과 기준).

    저장 전 PNG 매직넘버를 검증해 깨진 바이너리가 산출물을 오염시키지 않게 한다.
    """
    if not is_valid_png(data):
        raise ValueError("PNG 매직넘버가 없는 바이너리는 저장할 수 없습니다.")
    dst = Path(path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)
    return dst


def request_image(
    prompt: str,
    *,
    width: int = 100,
    height: int = 50,
    save_path: str | Path,
    api_key: str | None = None,
    endpoint: str | None = None,
    model: str | None = None,
    timeout: int = 60,
) -> dict:
    """VARCO Art API로 이미지를 생성해 PNG로 저장한다. 실패 시 fallback으로 전환한다.

    반환 dict:
    - ok            : 라이브 API로 온전한 PNG를 저장했는지 여부
    - status_code   : HTTP 상태코드(호출 성공 시)
    - used_fallback : placeholder fallback을 사용했는지 여부(카드 12)
    - path          : 저장된 PNG 경로
    - reason        : 실패/fallback 사유(있을 때)
    """
    api_key = api_key or os.getenv("NC_VARCO_API_KEY")
    endpoint = resolve_varco_endpoint(url=endpoint)
    model = model or os.getenv("NC_VARCO_MODEL")
    dst = Path(save_path)

    if not api_key:
        return _fallback(dst, width, height, reason="NC_VARCO_API_KEY 미설정")

    try:
        resp = requests.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=build_generation_payload(
                prompt, width=width, height=height, model=model
            ),
            timeout=timeout,
        )
    except requests.exceptions.RequestException as exc:
        return _fallback(dst, width, height, reason=f"네트워크 에러: {type(exc).__name__}")

    if resp.status_code not in (200, 201):
        return _fallback(
            dst, width, height, reason=f"HTTP {resp.status_code}", status_code=resp.status_code
        )

    try:
        image_bytes = extract_image_bytes(resp)
        save_image_bytes(image_bytes, dst)
    except (ValueError, requests.exceptions.RequestException) as exc:
        return _fallback(
            dst, width, height, reason=f"응답 처리 실패: {type(exc).__name__}",
            status_code=resp.status_code,
        )

    return {
        "ok": True,
        "status_code": resp.status_code,
        "used_fallback": False,
        "path": str(dst),
        "reason": None,
    }


def _fallback(
    dst: Path, width: int, height: int, *, reason: str, status_code: int | None = None
) -> dict:
    """카드 12항: [가정] 기각 후 placeholder PNG를 저장하고 결과를 보고한다."""
    save_image_bytes(make_placeholder_png(width, height, color=(0, 0, 255)), dst)
    return {
        "ok": False,
        "status_code": status_code,
        "used_fallback": True,
        "path": str(dst),
        "reason": reason,
    }
