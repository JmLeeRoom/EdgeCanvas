"""T-101: Typer CLI 명령어 엔트리포인트 — 단위 테스트.

단위구현계획서.md 제5장 [T-101] 10~12항 절차를 코드로 검증한다.
- 준비: 가상환경 실행 상태.
- 실행: python src/cli/main.py run --help
- 통과 기준: Typer 자동 헬프 메시지 및 옵션(pdf-path, spec-path, target,
  그리고 코딩 표준의 --mode {sim|hw})이 정상 구조로 표출된다.
- 11항: 지정 매개변수 유효성 검사 루틴이 반영된다.
- 12항: 파일 입력값을 os.path.abspath로 정규화된 절대경로로 확보한다.
"""

import os

from typer.testing import CliRunner

from src.cli.main import app, normalize_path

runner = CliRunner()


def test_run_help_exposes_documented_options():
    """10항: run --help이 pdf-path, spec-path, target 옵션을 표출해야 한다."""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0, result.output
    for option in ("--pdf-path", "--spec-path", "--target"):
        assert option in result.output, f"{option} 옵션이 헬프에 없습니다."


def test_run_help_exposes_mode_option_with_sim_hw():
    """코딩 표준: run은 --mode {sim|hw} 형태를 유지해야 한다."""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0, result.output
    assert "--mode" in result.output
    assert "sim" in result.output
    assert "hw" in result.output


def test_top_level_help_lists_all_three_commands():
    """8항: run/evaluate/cleanup 3종 명령이 등록되어야 한다."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0, result.output
    for command in ("run", "evaluate", "cleanup"):
        assert command in result.output, f"{command} 명령이 등록되지 않았습니다."


def test_run_rejects_invalid_mode():
    """11항: --mode에 sim|hw 이외 값을 주면 검증 실패로 거부되어야 한다."""
    result = runner.invoke(
        app,
        ["run", "--mode", "prod", "--pdf-path", "x.pdf", "--spec-path", "x.txt",
         "--target", "esp32-p4"],
    )
    assert result.exit_code != 0


def test_run_rejects_nonexistent_pdf_path(tmp_path):
    """11항: 존재하지 않는 PDF 경로는 유효성 검사에서 거부되어야 한다."""
    spec = tmp_path / "spec.txt"
    spec.write_text("요구사항", encoding="utf-8")
    result = runner.invoke(
        app,
        ["run", "--mode", "sim",
         "--pdf-path", str(tmp_path / "missing.pdf"),
         "--spec-path", str(spec),
         "--target", "esp32-p4"],
    )
    assert result.exit_code != 0


def test_run_rejects_nonexistent_spec_path(tmp_path):
    """11항: 존재하지 않는 요구사항 경로는 유효성 검사에서 거부되어야 한다."""
    pdf = tmp_path / "sheet.pdf"
    pdf.write_bytes(b"%PDF-1.4 dummy")
    result = runner.invoke(
        app,
        ["run", "--mode", "sim",
         "--pdf-path", str(pdf),
         "--spec-path", str(tmp_path / "missing.txt"),
         "--target", "esp32-p4"],
    )
    assert result.exit_code != 0


def test_run_accepts_valid_inputs(tmp_path):
    """정상 입력이면 run 명령이 성공(exit_code 0)해야 한다."""
    pdf = tmp_path / "sheet.pdf"
    pdf.write_bytes(b"%PDF-1.4 dummy")
    spec = tmp_path / "spec.txt"
    spec.write_text("요구사항", encoding="utf-8")
    result = runner.invoke(
        app,
        ["run", "--mode", "sim",
         "--pdf-path", str(pdf),
         "--spec-path", str(spec),
         "--target", "esp32-p4"],
    )
    assert result.exit_code == 0, result.output


def test_normalize_path_returns_absolute_from_relative():
    """12항: 상대경로 입력이 os.path.abspath로 절대경로화되어야 한다."""
    normalized = normalize_path("some/relative/file.pdf")
    assert os.path.isabs(normalized)
    assert normalized == os.path.abspath("some/relative/file.pdf")


def test_run_normalizes_pdf_path_to_absolute(tmp_path, monkeypatch):
    """12항: run 실행 시 상대경로 PDF가 절대경로로 정규화되어 출력에 반영된다."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "sheet.pdf").write_bytes(b"%PDF-1.4 dummy")
    (tmp_path / "spec.txt").write_text("요구사항", encoding="utf-8")
    result = runner.invoke(
        app,
        ["run", "--mode", "sim",
         "--pdf-path", "sheet.pdf",
         "--spec-path", "spec.txt",
         "--target", "esp32-p4"],
    )
    assert result.exit_code == 0, result.output
    assert os.path.abspath("sheet.pdf") in result.output


def test_evaluate_help_available():
    """evaluate 명령이 헬프를 제공해야 한다."""
    result = runner.invoke(app, ["evaluate", "--help"])
    assert result.exit_code == 0, result.output


def test_cleanup_help_available():
    """cleanup 명령이 헬프를 제공해야 한다."""
    result = runner.invoke(app, ["cleanup", "--help"])
    assert result.exit_code == 0, result.output
