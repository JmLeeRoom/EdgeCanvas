"""Run ID 생성 및 실행 산출물 디렉토리 체계 관리.

단위구현계획서.md 제5장 [T-005] 8항 구현 내용을 따른다.
각 실행(Run)마다 유일한 Run ID를 발급하고, output/<run_id>/ 하위에
logs/, assets/, build/ 폴더를 생성하는 헬퍼를 제공한다.
"""

import secrets
from datetime import datetime
from pathlib import Path

DEFAULT_OUTPUT_DIR = Path("output")
RUN_SUBDIRS = ("logs", "assets", "build")


def generate_run_id(now: datetime | None = None) -> str:
    """타임스탬프와 해시 기반의 Run ID를 생성한다.

    형식: run_YYYYMMDD_XXXX (XXXX는 4자리 16진 랜덤 해시)
    예: run_20260703_abcd
    """
    timestamp = (now or datetime.now()).strftime("%Y%m%d")
    suffix = secrets.token_hex(2)
    return f"run_{timestamp}_{suffix}"


def create_run_dirs(run_id: str, base_dir: Path | str = DEFAULT_OUTPUT_DIR) -> Path:
    """output/<run_id>/ 하위에 logs/, assets/, build/ 폴더를 생성한다.

    이미 존재하는 폴더는 건너뛰므로 같은 run_id로 여러 번 호출해도 안전하다(idempotent).

    Raises:
        PermissionError: OS 쓰기 권한이 없어 디렉토리를 생성할 수 없을 때,
            사용자가 쓰기 권한이 있는 경로로 output 위치를 조정하도록 안내하는
            메시지와 함께 다시 발생시킨다.
    """
    run_path = Path(base_dir) / run_id
    try:
        for sub in RUN_SUBDIRS:
            (run_path / sub).mkdir(parents=True, exist_ok=True)
    except PermissionError as exc:
        raise PermissionError(
            f"'{run_path}' 경로에 디렉토리를 생성할 쓰기 권한이 없습니다. "
            "사용자 쓰기 권한이 허용된 루트 디렉토리 내부의 상대 경로로 "
            "output 위치를 재설정하세요."
        ) from exc
    return run_path
