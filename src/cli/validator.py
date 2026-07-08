"""사용자 입력(PDF 데이터시트/요구사항 텍스트) 사전 검증 모듈.

단위구현계획서.md 제5장 [T-102] 8항 구현 내용을 따른다.

- ``InputValidator``: PDF 헤더 매직 바이트 검사 및 요구사항 텍스트 파일의
  용량/제어문자 필터링을 제공하는 정적 검증 클래스.
- 결격 입력은 ``InvalidFileException``을 일관되게 발생시킨다(10항 통과 기준).

12항(실패 시 대처) 대응: 대용량 PDF 로드로 인한 메모리 지연을 막기 위해
파일 전체를 로드하지 않고 첫 1024바이트 영역만 스트림으로 읽어 헤더를
검증한다.
"""

from pathlib import Path
from typing import Union

from pydantic import BaseModel

PDF_MAGIC_BYTES = b"%PDF-"
PDF_HEADER_READ_SIZE = 1024

# 공백류(탭/개행/캐리지리턴)는 허용하고 그 외 제어문자(0x00-0x08, 0x0B,
# 0x0C, 0x0E-0x1F)는 바이너리/스크립트 파일의 흔적으로 간주해 차단한다.
_ALLOWED_WHITESPACE_CONTROL_CODES = frozenset({0x09, 0x0A, 0x0D})


class InvalidFileException(Exception):
    """PDF/요구사항 입력 파일이 사전 검증을 통과하지 못했을 때 발생한다."""


class RequirementsFileCheckResult(BaseModel):
    """요구사항 파일 검증 결과를 구조화하는 Pydantic 모델.

    Technology KB 등 후속 파이프라인 단계에서 검증 근거(파일 크기,
    제어문자 포함 여부)를 함께 소비할 수 있도록 구조화된 값으로 남긴다.
    """

    path: str
    size_bytes: int
    has_forbidden_control_chars: bool


class InputValidator:
    """PDF 데이터시트/요구사항 텍스트 파일의 사전 검증을 담당한다."""

    @staticmethod
    def validate_pdf(pdf_path: Union[str, Path]) -> bool:
        """PDF 파일의 헤더 매직 바이트(``%PDF-``)를 검증한다.

        파일 전체를 로드하지 않고 첫 ``PDF_HEADER_READ_SIZE`` 바이트만
        스트림으로 읽어 검사한다(12항 대처).

        Raises:
            InvalidFileException: 파일이 없거나, 헤더에 ``%PDF-`` 매직
                바이트가 없을 때.
        """
        path = Path(pdf_path)
        if not path.is_file():
            raise InvalidFileException(f"PDF 파일이 존재하지 않습니다: {path}")

        with open(path, "rb") as handle:
            header = handle.read(PDF_HEADER_READ_SIZE)

        if not header.startswith(PDF_MAGIC_BYTES):
            raise InvalidFileException(
                f"PDF 헤더 매직 바이트({PDF_MAGIC_BYTES!r})를 찾을 수 없습니다: {path}"
            )
        return True

    @staticmethod
    def validate_requirements(spec_path: Union[str, Path]) -> bool:
        """요구사항 텍스트 파일의 용량/제어문자 여부를 검증한다.

        - 빈 파일(0바이트)은 차단한다.
        - 공백류(탭/개행/캐리지리턴)를 제외한 제어문자(예: NUL)를 포함하면
          비-스크립트 텍스트 파일로 보지 않고 차단한다.

        Raises:
            InvalidFileException: 파일이 없거나, 비어 있거나, 금지된
                제어문자를 포함할 때.
        """
        path = Path(spec_path)
        if not path.is_file():
            raise InvalidFileException(f"요구사항 파일이 존재하지 않습니다: {path}")

        size_bytes = path.stat().st_size
        if size_bytes == 0:
            raise InvalidFileException(f"요구사항 파일이 비어 있습니다: {path}")

        content = path.read_bytes()
        has_forbidden_control_chars = InputValidator._contains_forbidden_control_chars(
            content
        )

        result = RequirementsFileCheckResult(
            path=str(path),
            size_bytes=size_bytes,
            has_forbidden_control_chars=has_forbidden_control_chars,
        )

        if result.has_forbidden_control_chars:
            raise InvalidFileException(
                f"요구사항 파일에 허용되지 않는 제어문자가 포함되어 있습니다: {path}"
            )
        return True

    @staticmethod
    def _contains_forbidden_control_chars(content: bytes) -> bool:
        """탭/개행/캐리지리턴을 제외한 제어문자(0x00-0x1F, 0x7F)를 포함하는지 검사한다."""
        for byte in content:
            if byte in _ALLOWED_WHITESPACE_CONTROL_CODES:
                continue
            if byte < 0x20 or byte == 0x7F:
                return True
        return False
