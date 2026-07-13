"""T-010 스파이크: NC AI VARCO Art 이미지 생성 API 접속 검증.

단위구현계획서.md 제5장 [T-010] 8항 구현 내용을 따른다.
"100x50 파란색 사각형 전송 버튼 이미지" 프롬프트를 VARCO 이미지(3D) 생성 REST API에
`requests`로 POST 하고, 응답(JSON 링크/base64 또는 raw 바이너리)을 로컬 PNG로 저장한다.

기본 엔드포인트: ``https://openapi.ai.nc.com/3d/varco/v1/image-to-3d``
(다른 NC OpenAPI 예: ``https://openapi.ai.nc.com/mt/chat-content/v1/translate``)

카드 12항(Placeholder Fallback): 권한 미획득/서비스 중단 등 네트워크 에러 시 [가정]을
기각하고, 단순 색상 채우기 placeholder PNG를 로컬에서 생성해 파이프라인을 잇는다.

설정은 모두 환경변수로 읽는다(코딩표준: 키/엔드포인트를 코드·로그에 남기지 않는다):
- NC_VARCO_API_KEY     : 인증 토큰 (없으면 라이브 호출 스킵 → fallback)
- NC_VARCO_AUTH_HEADER : 인증 헤더 이름 (기본 ``OPENAPI_KEY``; NC OpenAPI 규격)
- NC_VARCO_API_URL     : 전체 엔드포인트 URL 오버라이드 (최우선)
- NC_VARCO_API_BASE    : 베이스 URL만 오버라이드 (``NC_VARCO_API_URL`` 미설정 시 path와 조합)
- NC_VARCO_MODEL       : 사용 모델 식별자(선택)
- NC_VARCO_POLL_INTERVAL : 202 비동기 폴링 간격 초 (기본 2)
- NC_VARCO_POLL_TIMEOUT  : 202 비동기 폴링 최대 대기 초 (기본 120)
- NC_VARCO_POLL_URL_TEMPLATE : 폴링 URL 템플릿. ``{job_id}`` ``{request_id}``
  ``{endpoint}`` ``{base}`` 치환. 응답 본문/Location에 poll URL이 없을 때만 사용.
"""
from __future__ import annotations

import base64
import os
import struct
import time
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

# NC OpenAPI (openapi.ai.nc.com) 기본 인증 헤더. Bearer는 레거시/테스트용 오버라이드만.
DEFAULT_AUTH_HEADER = "OPENAPI_KEY"

# 비동기 작업 완료/실패로 간주하는 status 문자열 (소문자 비교).
_ASYNC_COMPLETED_STATUSES = frozenset({"completed", "success", "done", "succeeded"})
_ASYNC_FAILED_STATUSES = frozenset({"failed", "error", "cancelled", "canceled"})


class VarcoJobFailedError(RuntimeError):
    """비동기 VARCO 작업이 failed/error 등 종료 상태로 끝났을 때."""

    def __init__(self, status: str, *, detail: str | None = None) -> None:
        self.status = status
        self.detail = detail
        msg = f"VARCO async job {status!r}"
        if detail:
            msg = f"{msg}: {detail}"
        super().__init__(msg)


class VarcoPollTimeoutError(TimeoutError):
    """비동기 VARCO 작업 폴링이 제한 시간 내에 완료되지 않았을 때."""

    def __init__(self, poll_url: str, timeout: float) -> None:
        self.poll_url = poll_url
        self.timeout = timeout
        super().__init__(f"VARCO async poll timed out after {timeout}s")


def default_poll_interval() -> float:
    """환경변수 ``NC_VARCO_POLL_INTERVAL`` (기본 2초)."""
    return float(os.getenv("NC_VARCO_POLL_INTERVAL", "2"))


def default_poll_timeout() -> float:
    """환경변수 ``NC_VARCO_POLL_TIMEOUT`` (기본 120초)."""
    return float(os.getenv("NC_VARCO_POLL_TIMEOUT", "120"))


def build_auth_headers(
    api_key: str,
    *,
    auth_header: str | None = None,
) -> dict[str, str]:
    """NC OpenAPI 인증 헤더를 구성한다.

    기본은 ``OPENAPI_KEY: <token>`` (openapi.ai.nc.com). ``NC_VARCO_AUTH_HEADER``로
    헤더 이름을 오버라이드할 수 있다. ``Authorization``을 지정하면 Bearer 스킴을 붙인다.
    """
    header_name = (auth_header or os.getenv("NC_VARCO_AUTH_HEADER") or DEFAULT_AUTH_HEADER).strip()
    if header_name.lower() == "authorization":
        return {"Authorization": f"Bearer {api_key}"}
    return {header_name: api_key}


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


def _job_status_from_body(body: object) -> str | None:
    """JSON 본문에서 비동기 작업 상태 문자열을 추출한다."""
    if not isinstance(body, dict):
        return None
    for key in ("status", "state", "job_status", "task_status"):
        value = body.get(key)
        if value is not None:
            return str(value).lower()
    return None


def _response_has_extractable_image(resp) -> bool:
    """응답에서 PNG 이미지 바이트를 즉시 추출할 수 있는지 검사한다."""
    content_type = (resp.headers or {}).get("Content-Type", "")
    if content_type.startswith("image/"):
        return is_valid_png(resp.content)
    if resp.status_code not in (200, 201):
        return False
    try:
        data = extract_image_bytes(resp)
    except (ValueError, requests.exceptions.RequestException):
        return False
    return is_valid_png(data)


def _poll_url_from_template(
    job_id: str,
    *,
    endpoint: str | None = None,
    api_base: str | None = None,
) -> str | None:
    """``NC_VARCO_POLL_URL_TEMPLATE`` 환경변수로 폴링 URL을 구성한다."""
    template = os.getenv("NC_VARCO_POLL_URL_TEMPLATE", "").strip()
    if not template:
        return None
    base = (api_base or os.getenv("NC_VARCO_API_BASE") or DEFAULT_API_BASE).rstrip("/")
    ep = (endpoint or resolve_varco_endpoint()).rstrip("/")
    return template.format(
        job_id=job_id,
        request_id=job_id,
        endpoint=ep,
        base=base,
    )


def parse_async_job(
    resp,
    *,
    endpoint: str | None = None,
    api_base: str | None = None,
) -> dict[str, str | None]:
    """202 Accepted 응답에서 job id와 폴링 URL을 추출한다.

    우선순위:
    1. ``Location`` 헤더
    2. JSON 본문 ``poll_url`` / ``status_url`` / ``result_url`` / ``url``
    3. JSON 본문 ``requestId`` / ``job_id`` / ``task_id`` / ``id`` + ``NC_VARCO_POLL_URL_TEMPLATE``

    라이브 probe(2026-07-13): 본문 키는 ``message``, ``requestId``, ``requestTime`` 뿐이며
    poll URL은 응답에 포함되지 않는다. 템플릿 미설정 시 ``poll_url``은 ``None``이다.
    """
    headers = resp.headers or {}
    poll_url = headers.get("Location") or headers.get("location")

    body: dict | None = None
    content_type = headers.get("Content-Type", "")
    if "json" in content_type:
        try:
            parsed = resp.json()
            if isinstance(parsed, dict):
                body = parsed
        except ValueError:
            body = None

    if body and not poll_url:
        for key in ("poll_url", "status_url", "result_url", "url"):
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                poll_url = value.strip()
                break

    job_id: str | None = None
    if body:
        for key in ("requestId", "request_id", "job_id", "task_id", "id"):
            value = body.get(key)
            if value is not None and str(value).strip():
                job_id = str(value).strip()
                break

    if not poll_url and job_id:
        poll_url = _poll_url_from_template(
            job_id, endpoint=endpoint, api_base=api_base
        )

    return {"job_id": job_id, "poll_url": poll_url}


def poll_until_complete(
    poll_url: str,
    headers: dict[str, str],
    timeout: float,
    poll_interval: float,
    *,
    get_fn=None,
) -> requests.Response:
    """폴링 URL을 주기적으로 조회해 이미지 또는 완료 상태가 될 때까지 대기한다.

    - 200/201 + image/* 또는 추출 가능한 PNG → 완료
    - JSON ``status``/``state`` 가 completed/success/done → 완료(이미지 추출은 호출자)
    - failed/error → ``VarcoJobFailedError``
    - ``timeout`` 초과 → ``VarcoPollTimeoutError``
    """
    if get_fn is None:
        get_fn = requests.get
    deadline = time.monotonic() + timeout
    last_status: str | None = None

    while time.monotonic() < deadline:
        resp = get_fn(poll_url, headers=headers, timeout=30)

        if resp.status_code in (200, 201) and _response_has_extractable_image(resp):
            return resp

        if resp.status_code in (200, 201, 202):
            try:
                body = resp.json()
            except ValueError:
                body = None
            if isinstance(body, dict):
                status = _job_status_from_body(body)
                if status:
                    last_status = status
                    if status in _ASYNC_COMPLETED_STATUSES:
                        if _response_has_extractable_image(resp):
                            return resp
                        return resp
                    if status in _ASYNC_FAILED_STATUSES:
                        detail = body.get("message") or body.get("error") or body.get("reason")
                        raise VarcoJobFailedError(status, detail=str(detail) if detail else None)

        time.sleep(poll_interval)

    raise VarcoPollTimeoutError(poll_url, timeout)


def handle_varco_response(
    resp,
    headers: dict[str, str],
    *,
    poll_interval: float | None = None,
    poll_timeout: float | None = None,
    get_fn=None,
    endpoint: str | None = None,
    api_base: str | None = None,
) -> bytes:
    """VARCO API 응답을 처리해 PNG 이미지 바이트를 반환한다.

  - 200/201: 즉시 ``extract_image_bytes``
  - 202: ``parse_async_job`` → ``poll_until_complete`` → ``extract_image_bytes``
    """
    if get_fn is None:
        get_fn = requests.get
    if resp.status_code in (200, 201):
        return extract_image_bytes(resp)

    if resp.status_code == 202:
        job = parse_async_job(resp, endpoint=endpoint, api_base=api_base)
        poll_url = job.get("poll_url")
        if not poll_url:
            job_id = job.get("job_id") or "unknown"
            raise ValueError(
                f"async 202 without poll URL (job_id={job_id}); "
                "set NC_VARCO_POLL_URL_TEMPLATE if NC provides a status endpoint"
            )
        interval = default_poll_interval() if poll_interval is None else poll_interval
        timeout = default_poll_timeout() if poll_timeout is None else poll_timeout
        final = poll_until_complete(
            poll_url,
            headers,
            timeout,
            interval,
            get_fn=get_fn,
        )
        return extract_image_bytes(final)

    raise ValueError(f"unexpected HTTP {resp.status_code}")


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
                **build_auth_headers(api_key),
                "Content-Type": "application/json",
            },
            json=build_generation_payload(
                prompt, width=width, height=height, model=model
            ),
            timeout=timeout,
        )
    except requests.exceptions.RequestException as exc:
        return _fallback(dst, width, height, reason=f"네트워크 에러: {type(exc).__name__}")

    if resp.status_code not in (200, 201, 202):
        return _fallback(
            dst, width, height, reason=f"HTTP {resp.status_code}", status_code=resp.status_code
        )

    auth_headers = {
        **build_auth_headers(api_key),
        "Content-Type": "application/json",
    }
    try:
        image_bytes = handle_varco_response(
            resp,
            auth_headers,
            endpoint=endpoint,
        )
        save_image_bytes(image_bytes, dst)
    except VarcoPollTimeoutError as exc:
        return _fallback(
            dst,
            width,
            height,
            reason=f"async poll timeout ({exc.timeout}s)",
            status_code=resp.status_code,
        )
    except VarcoJobFailedError as exc:
        return _fallback(
            dst,
            width,
            height,
            reason=f"async job failed: {exc.status}",
            status_code=resp.status_code,
        )
    except (ValueError, requests.exceptions.RequestException) as exc:
        return _fallback(
            dst, width, height, reason=f"응답 처리 실패: {exc}",
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
