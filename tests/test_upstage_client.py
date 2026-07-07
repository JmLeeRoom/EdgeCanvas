"""T-002: Upstage API 연동 및 공통 모듈 구현 — 단위 테스트.

단위구현계획서.md 제5장 [T-002] 10항 절차를 코드로 검증한다.
"""
import os

import pytest
from dotenv import load_dotenv

load_dotenv()

from src.common.upstage_client import UpstageClient  # noqa: E402

REQUIRES_LIVE_API = pytest.mark.skipif(
    not os.getenv("UPSTAGE_API_KEY"),
    reason="UPSTAGE_API_KEY가 .env에 설정되어 있지 않습니다.",
)


def test_env_loader_reads_upstage_api_key(monkeypatch):
    """11-1: 환경변수 로더가 .env 파일을 정상 파싱해야 한다."""
    monkeypatch.setenv("UPSTAGE_API_KEY", "test-key-12345")
    client = UpstageClient()
    assert client.api_key == "test-key-12345"


def test_client_instantiation_raises_without_api_key(monkeypatch):
    """12: 실패 시 대처 — API 키가 없으면 인스턴스화 시점에 명확한 예외를 던져야 한다."""
    monkeypatch.delenv("UPSTAGE_API_KEY", raising=False)
    with pytest.raises(ValueError, match="UPSTAGE_API_KEY"):
        UpstageClient()


def test_client_instantiation_does_not_raise_with_valid_key(monkeypatch):
    """11-2: Upstage API 클라이언트가 인스턴스화 시 예외를 발생시키지 않아야 한다."""
    monkeypatch.setenv("UPSTAGE_API_KEY", "test-key-12345")
    client = UpstageClient()
    assert client is not None


@REQUIRES_LIVE_API
def test_solar_api_call_returns_success():
    """10, 11-3: 통과 기준 — Hello World 텍스트에 대한 Solar API 응답이 성공해야 한다."""
    client = UpstageClient()
    response = client.chat("Hello World")
    assert response is not None
    assert len(response) > 0
