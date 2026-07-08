"""P10_Manufacturing HMI 자동 생성/검증 CLI 엔트리포인트.

단위구현계획서.md 제5장 [T-101] 8항 구현 내용을 따른다.
Typer로 단일 진입점(`p10`)을 구성하고 3종 명령을 매핑한다:

- ``run``      : E2E 파이프라인 기동 (코딩 표준상 ``--mode {sim|hw}`` 유지)
- ``evaluate`` : 지표 측정
- ``cleanup``  : 임시 run ID 정리

12항(실패 시 대처) 대응: 파일 입력값은 파이프라인에 전달하기 전에
``os.path.abspath``로 정규화된 절대경로를 확보해 윈도우 경로/인코딩
문제를 예방한다. 실제 파이프라인 오케스트레이션은 후속 Task(T-701 등)의
소관이므로 여기서는 명확한 스텁으로 남긴다.
"""

import os
from enum import Enum
from pathlib import Path

import typer

app = typer.Typer(
    name="p10",
    help="P10_Manufacturing HMI 자동 생성/검증 CLI.",
    add_completion=False,
    no_args_is_help=True,
)


class RunMode(str, Enum):
    """파이프라인 실행 모드. 코딩 표준(`p10 run --mode {sim|hw}`)을 따른다."""

    SIM = "sim"
    HW = "hw"


def normalize_path(raw_path: str) -> str:
    """입력 경로를 정규화된 절대경로로 변환한다 (12항 대처).

    윈도우 경로/인코딩 인식 문제를 예방하기 위해 파일 입력값을
    받는 즉시 ``os.path.abspath``로 절대경로를 확보한다.
    """
    return os.path.abspath(raw_path)


def _require_existing_file(raw_path: str, label: str) -> Path:
    """경로를 절대경로로 정규화하고 실제 파일 존재 여부를 검증한다 (11항).

    Raises:
        typer.BadParameter: 파일이 존재하지 않거나 디렉토리일 때.
    """
    absolute = normalize_path(raw_path)
    path = Path(absolute)
    if not path.is_file():
        raise typer.BadParameter(f"{label} 경로에 파일이 없습니다: {absolute}")
    return path


@app.command()
def run(
    pdf_path: str = typer.Option(
        ..., "--pdf-path", help="데이터시트 PDF 파일 경로."
    ),
    spec_path: str = typer.Option(
        ..., "--spec-path", help="요구사항 텍스트 파일 경로."
    ),
    target: str = typer.Option(
        ..., "--target", help="타깃 보드명 (예: esp32-p4)."
    ),
    mode: RunMode = typer.Option(
        RunMode.SIM, "--mode", help="실행 모드: sim(시뮬) 또는 hw(실기)."
    ),
) -> None:
    """E2E HMI 자동 생성/검증 파이프라인을 기동한다."""
    pdf = _require_existing_file(pdf_path, "데이터시트 PDF")
    spec = _require_existing_file(spec_path, "요구사항 파일")

    typer.echo(f"[run] mode={mode.value} target={target}")
    typer.echo(f"[run] pdf-path={pdf}")
    typer.echo(f"[run] spec-path={spec}")
    # TODO(T-701): LangGraph 오케스트레이션 파이프라인과 연결한다.
    typer.echo("[run] 파이프라인 연결은 후속 Task에서 구현됩니다.")


@app.command()
def evaluate(
    target: str = typer.Option(
        ..., "--target", help="지표를 측정할 타깃 보드명."
    ),
    run_id: str = typer.Option(
        None, "--run-id", help="측정 대상 Run ID (미지정 시 최신 실행)."
    ),
) -> None:
    """생성된 HMI 결과물의 지표를 측정한다."""
    typer.echo(f"[evaluate] target={target} run_id={run_id or '(latest)'}")
    # TODO(T-9xx): 지표 측정 로직과 연결한다.
    typer.echo("[evaluate] 지표 측정 로직은 후속 Task에서 구현됩니다.")


@app.command()
def cleanup(
    run_id: str = typer.Option(
        None, "--run-id", help="정리할 특정 Run ID (미지정 시 임시 run 전체)."
    ),
) -> None:
    """임시 run ID 산출물을 정리한다."""
    typer.echo(f"[cleanup] target run_id={run_id or '(all temporary)'}")
    # TODO(T-005 연계): output/<run_id>/ 정리 로직과 연결한다.
    typer.echo("[cleanup] 정리 로직은 후속 Task에서 구현됩니다.")


if __name__ == "__main__":
    app()
