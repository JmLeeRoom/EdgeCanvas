"""T-005: 로깅 모듈 및 Run ID 기반 산출물 체계 구현 — 단위 테스트.

단위구현계획서.md 제5장 [T-005] 10항 절차를 코드로 검증한다.
- 준비: output 디렉토리가 비어 있는 상태.
- 실행: python -m pytest tests/test_run_manager.py
- 통과 기준: 새 폴더 구조(logs, assets, build)가 자동 생성되고,
  에러 없이 로그 텍스트 파일에 지정된 문구가 누적 저장된다.
"""

import re
import logging

import pytest

from src.common.run_manager import generate_run_id, create_run_dirs
from src.common.logger import get_run_logger

RUN_ID_PATTERN = re.compile(r"^run_\d{8}_[0-9a-f]{4}$")


def test_generate_run_id_matches_expected_format():
    """8-2: Run ID는 run_YYYYMMDD_XXXX(해시 4자리) 형식을 따라야 한다."""
    run_id = generate_run_id()
    assert RUN_ID_PATTERN.match(run_id), f"형식 불일치: {run_id}"


def test_generate_run_id_is_unique_across_calls():
    """11-1: Run ID 생성 시 중복성이 없고 고유성이 확인되어야 한다."""
    ids = {generate_run_id() for _ in range(50)}
    assert len(ids) == 50, "Run ID 충돌(중복)이 발생했습니다."


def test_create_run_dirs_creates_logs_assets_build(tmp_path):
    """11-2: 하위 폴더 3종(logs, assets, build)이 예외 없이 물리 생성되어야 한다."""
    run_id = "run_20260703_abcd"
    run_path = create_run_dirs(run_id, base_dir=tmp_path)

    assert run_path == tmp_path / run_id
    for sub in ("logs", "assets", "build"):
        subdir = run_path / sub
        assert subdir.is_dir(), f"{sub} 폴더가 생성되지 않았습니다."


def test_create_run_dirs_is_idempotent(tmp_path):
    """같은 run_id로 두 번 호출해도 예외 없이 동작해야 한다."""
    run_id = "run_20260703_abcd"
    create_run_dirs(run_id, base_dir=tmp_path)
    run_path = create_run_dirs(run_id, base_dir=tmp_path)
    assert (run_path / "logs").is_dir()


def test_create_run_dirs_permission_error_raises_clear_message(monkeypatch, tmp_path):
    """12: 실패 시 대처 — 디렉토리 생성 권한 문제(Access Denied) 시
    사용자가 쓰기 권한이 있는 경로로 output 위치를 조정하도록 안내하는
    명확한 예외를 발생시켜야 한다.
    """
    from pathlib import Path

    def _raise_permission_error(self, *args, **kwargs):
        raise PermissionError("Access is denied")

    monkeypatch.setattr(Path, "mkdir", _raise_permission_error)

    with pytest.raises(PermissionError, match="쓰기 권한"):
        create_run_dirs("run_20260703_abcd", base_dir=tmp_path)


def test_get_run_logger_writes_to_file(tmp_path):
    """10: 통과 기준 — 로그 텍스트 파일에 지정된 문구가 에러 없이 저장된다."""
    run_id = "run_20260703_abcd"
    create_run_dirs(run_id, base_dir=tmp_path)

    logger = get_run_logger(run_id, base_dir=tmp_path)
    logger.info("hello from T-005 test")

    for handler in logger.handlers:
        handler.flush()

    log_file = tmp_path / run_id / "logs" / "app.log"
    assert log_file.is_file()
    content = log_file.read_text(encoding="utf-8")
    assert "hello from T-005 test" in content


def test_get_run_logger_accumulates_multiple_messages(tmp_path):
    """통과 기준: 여러 번 로깅해도 기존 내용을 덮어쓰지 않고 누적되어야 한다."""
    run_id = "run_20260703_abcd"
    create_run_dirs(run_id, base_dir=tmp_path)

    logger = get_run_logger(run_id, base_dir=tmp_path)
    logger.info("first message")
    logger.info("second message")

    for handler in logger.handlers:
        handler.flush()

    log_file = tmp_path / run_id / "logs" / "app.log"
    content = log_file.read_text(encoding="utf-8")
    assert "first message" in content
    assert "second message" in content


def test_get_run_logger_also_logs_to_console(tmp_path, capsys):
    """8-1: 콘솔 및 파일 쓰기를 동시 지원해야 한다."""
    run_id = "run_20260703_abcd"
    create_run_dirs(run_id, base_dir=tmp_path)

    logger = get_run_logger(run_id, base_dir=tmp_path)
    has_stream_handler = any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        for h in logger.handlers
    )
    assert has_stream_handler, "콘솔(StreamHandler) 출력이 구성되어 있지 않습니다."
