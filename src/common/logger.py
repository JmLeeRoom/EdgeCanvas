"""콘솔 및 파일 쓰기를 동시 지원하는 로깅 프레임워크.

단위구현계획서.md 제5장 [T-005] 8항 구현 내용을 따른다.
Run ID별 output/<run_id>/logs/app.log 파일에 로그를 누적 저장하는 동시에
콘솔로도 출력하는 로거를 제공한다.
"""

import logging
from pathlib import Path

from src.common.run_manager import DEFAULT_OUTPUT_DIR

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def get_run_logger(
    run_id: str,
    base_dir: Path | str = DEFAULT_OUTPUT_DIR,
    level: int = logging.INFO,
) -> logging.Logger:
    """Run ID에 해당하는 로거를 생성/재사용한다.

    output/<run_id>/logs/app.log 파일 핸들러와 콘솔(StreamHandler)을
    동시에 부착한다. 같은 run_id로 재호출 시 핸들러가 중복 부착되지 않는다.
    """
    logger = logging.getLogger(f"p10.run.{run_id}")
    logger.setLevel(level)
    logger.propagate = False

    log_path = Path(base_dir) / run_id / "logs" / "app.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(LOG_FORMAT)

    has_file_handler = any(
        isinstance(h, logging.FileHandler)
        and Path(h.baseFilename) == log_path.resolve()
        for h in logger.handlers
    )
    if not has_file_handler:
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    has_stream_handler = any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        for h in logger.handlers
    )
    if not has_stream_handler:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    return logger
