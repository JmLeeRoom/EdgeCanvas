"""T-102: PDF/요구사항 입력 검증 모듈(InputValidator) — 단위 테스트.

단위구현계획서.md 제5장 [T-102] 10~12항 절차를 코드로 검증한다.
- 준비: 정상 PDF 파일, 빈 텍스트 파일, 가짜 PDF 확장자 텍스트 파일 준비.
- 실행: pytest tests/test_cli_validator.py
- 통과 기준: 정상 입력은 True를, 결격 입력 파일 검증에 대해서는
  InvalidFileException을 일관되게 반환하며 동작한다.
- 12항: PDF 헤더 검사는 파일 전체를 로드하지 않고 첫 1024바이트만
  스트림으로 읽어 처리해야 한다(대용량 PDF 메모리 지연 방지).
"""

import io

import pytest

from src.cli.validator import InputValidator, InvalidFileException


class TestValidatePdf:
    """PDF 파일 헤더 매직 바이트(%PDF-) 검증."""

    def test_valid_pdf_header_returns_true(self, tmp_path):
        """10항: 정상 PDF 파일(정상 헤더)은 True를 반환해야 한다."""
        pdf = tmp_path / "sheet.pdf"
        pdf.write_bytes(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3 dummy content")
        assert InputValidator.validate_pdf(pdf) is True

    def test_fake_pdf_extension_text_file_raises(self, tmp_path):
        """10항: 가짜 PDF 확장자 텍스트 파일(헤더 위조)은
        InvalidFileException을 발생시켜야 한다."""
        fake_pdf = tmp_path / "fake.pdf"
        fake_pdf.write_text("이것은 PDF가 아닙니다.", encoding="utf-8")
        with pytest.raises(InvalidFileException):
            InputValidator.validate_pdf(fake_pdf)

    def test_missing_pdf_file_raises(self, tmp_path):
        """존재하지 않는 PDF 경로는 InvalidFileException을 발생시켜야 한다."""
        missing = tmp_path / "missing.pdf"
        with pytest.raises(InvalidFileException):
            InputValidator.validate_pdf(missing)

    def test_empty_pdf_file_raises(self, tmp_path):
        """빈 파일(0바이트)은 헤더가 없으므로 InvalidFileException을
        발생시켜야 한다."""
        empty_pdf = tmp_path / "empty.pdf"
        empty_pdf.write_bytes(b"")
        with pytest.raises(InvalidFileException):
            InputValidator.validate_pdf(empty_pdf)

    def test_pdf_header_check_reads_at_most_1024_bytes(self, tmp_path, monkeypatch):
        """12항: 대용량 PDF도 파일 전체를 로드하지 않고 첫 1024바이트
        영역만 스트림으로 읽어 헤더 검증을 처리해야 한다."""
        large_pdf = tmp_path / "large.pdf"
        # 1024바이트를 훌쩍 넘는 대용량 파일이지만 헤더는 정상.
        large_pdf.write_bytes(b"%PDF-1.7\n" + b"A" * (5 * 1024 * 1024))

        read_sizes = []
        real_open = io.open

        def spy_open(*args, **kwargs):
            handle = real_open(*args, **kwargs)
            real_read = handle.read

            def spy_read(size=-1, *r_args, **r_kwargs):
                read_sizes.append(size)
                return real_read(size, *r_args, **r_kwargs)

            handle.read = spy_read
            return handle

        monkeypatch.setattr("builtins.open", spy_open)

        assert InputValidator.validate_pdf(large_pdf) is True
        # read()가 무제한(-1)이나 전체 파일 크기로 호출되지 않고,
        # 1024 이하로 제한된 크기만 요청했는지 확인한다.
        assert read_sizes, "open().read()가 호출되지 않았습니다."
        for size in read_sizes:
            assert 0 < size <= 1024, f"read() 호출 크기가 1024바이트를 초과: {size}"


class TestValidateRequirements:
    """요구사항 텍스트 파일 용량/제어문자 필터링 검증."""

    def test_valid_requirements_file_returns_true(self, tmp_path):
        """10항: 정상 요구사항 텍스트 파일은 True를 반환해야 한다."""
        spec = tmp_path / "spec.txt"
        spec.write_text("LCD 해상도는 1024x600 이어야 한다.", encoding="utf-8")
        assert InputValidator.validate_requirements(spec) is True

    def test_empty_requirements_file_raises(self, tmp_path):
        """10/11항: 빈 요구사항 텍스트 파일은 InvalidFileException을
        발생시켜야 한다(차단 예외 처리)."""
        spec = tmp_path / "empty_spec.txt"
        spec.write_bytes(b"")
        with pytest.raises(InvalidFileException):
            InputValidator.validate_requirements(spec)

    def test_missing_requirements_file_raises(self, tmp_path):
        """존재하지 않는 요구사항 경로는 InvalidFileException을 발생시켜야 한다."""
        missing = tmp_path / "missing.txt"
        with pytest.raises(InvalidFileException):
            InputValidator.validate_requirements(missing)

    def test_requirements_file_with_control_characters_raises(self, tmp_path):
        """8항: 특수 제어문자(NUL 등)를 포함한 파일은 비-스크립트 텍스트로
        간주되지 않아 InvalidFileException을 발생시켜야 한다."""
        spec = tmp_path / "binary_spec.txt"
        spec.write_bytes(b"\x00\x01\x02\x03binary garbage\x00\x00")
        with pytest.raises(InvalidFileException):
            InputValidator.validate_requirements(spec)

    def test_requirements_file_allows_normal_whitespace(self, tmp_path):
        """탭/개행 등 일반적인 공백 제어문자는 허용되어야 한다."""
        spec = tmp_path / "multiline_spec.txt"
        spec.write_text("1행 요구사항\n2행 요구사항\t(탭 포함)\n", encoding="utf-8")
        assert InputValidator.validate_requirements(spec) is True
