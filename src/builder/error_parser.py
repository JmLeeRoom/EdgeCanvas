"""T-503: GCC/Clang 컴파일러 에러 로그 구문 분석기.

`idf.py build` 등에서 나온 GCC/Clang 컴파일·링크 로그를 정규식으로 파싱하여
LLM 피드백용 JSON 리포트 객체(`ParsedDiagnostic`) 목록으로 구조화한다.

Phase A: 모의 GCC 로그 fixture로 검증. Phase HW에서 실제 idf.py 로그 연동.

12항 실패 시 대처: 컴파일 진단(`file:line:col: error|warning:`) 누락되는
링커 에러는 `undefined reference to...` 전용 정규식 분기로 검출한다.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

Severity = Literal["error", "warning"]

# GCC/Clang 표준 진단: file:line:column: error|warning: message
_GCC_DIAG_RE = re.compile(
    r"^(?P<file>.+?):(?P<line>\d+):(?P<column>\d+):\s*"
    r"(?P<severity>error|warning):\s*(?P<message>.+)$"
)

# "In function 'foo':" 컨텍스트 (후속 진단에 function 부착)
_IN_FUNCTION_RE = re.compile(
    r"^(?P<file>.+?):\s*In function\s+'(?P<func>[^']+)':\s*$"
)

# 링커: undefined reference to `symbol'  (백틱/따옴표 모두 허용)
_LINKER_UNDEF_RE = re.compile(
    r"undefined reference to [`'](?P<symbol>[^`']+)[`']",
    re.IGNORECASE,
)

# 링커 라인에서 .text.funcname 또는 file.c 힌트
_LINKER_FUNC_RE = re.compile(r"\.text\.(?P<func>[A-Za-z_][\w]*)")
_LINKER_OBJ_FILE_RE = re.compile(
    r"(?P<file>[A-Za-z0-9_./\\-]+\.(?:c|cpp|cc|S))(?:\.obj)?"
)


class ParsedDiagnostic(BaseModel):
    """구조화된 컴파일/링크 진단 항목 (JSON 직렬화 가능)."""

    file: str | None = None
    line: int | None = None
    column: int | None = None
    severity: Severity = "error"
    message: str = ""
    symbol: str | None = None
    function: str | None = None


def _extract_quoted_ident(message: str) -> str | None:
    """메시지 안 첫 단일따옴표 식별자를 심볼 후보로 추출한다."""
    m = re.search(r"'([A-Za-z_][\w]*)'", message)
    return m.group(1) if m else None


def _parse_linker_line(line: str) -> ParsedDiagnostic | None:
    """링커 `undefined reference to...` 전용 분기."""
    m = _LINKER_UNDEF_RE.search(line)
    if not m:
        return None

    symbol = m.group("symbol")
    func_m = _LINKER_FUNC_RE.search(line)
    file_m = _LINKER_OBJ_FILE_RE.search(line)

    return ParsedDiagnostic(
        file=file_m.group("file") if file_m else None,
        line=None,
        column=None,
        severity="error",
        message=line.strip(),
        symbol=symbol,
        function=func_m.group("func") if func_m else None,
    )


def parse_compiler_log(log_text: str) -> list[ParsedDiagnostic]:
    """GCC/Clang 빌드 로그 문자열을 진단 목록으로 파싱한다.

    분기 체인:
    1. `In function '...'` 컨텍스트 추적
    2. GCC 표준 `file:line:col: error|warning: message`
    3. 링커 `undefined reference to...` (카드 12항)
    """
    results: list[ParsedDiagnostic] = []
    current_function: str | None = None
    current_file: str | None = None

    for raw in log_text.splitlines():
        line = raw.rstrip("\n")
        if not line.strip():
            continue

        in_fn = _IN_FUNCTION_RE.match(line.strip())
        if in_fn:
            current_function = in_fn.group("func")
            current_file = in_fn.group("file")
            continue

        diag_m = _GCC_DIAG_RE.match(line.strip())
        if diag_m:
            message = diag_m.group("message").strip()
            func = current_function
            if current_file and diag_m.group("file") != current_file:
                # 다른 파일로 넘어가면 컨텍스트 리셋
                func = None
            results.append(
                ParsedDiagnostic(
                    file=diag_m.group("file"),
                    line=int(diag_m.group("line")),
                    column=int(diag_m.group("column")),
                    severity=diag_m.group("severity"),  # type: ignore[arg-type]
                    message=message,
                    symbol=_extract_quoted_ident(message),
                    function=func,
                )
            )
            continue

        linker = _parse_linker_line(line)
        if linker is not None:
            results.append(linker)

    return results


def parse_compiler_log_file(path: str | Path) -> list[ParsedDiagnostic]:
    """로그 파일 경로에서 파싱한다."""
    text = Path(path).read_text(encoding="utf-8")
    return parse_compiler_log(text)


def diagnostics_to_report(diagnostics: list[ParsedDiagnostic]) -> dict:
    """검증/LLM 피드백용 JSON 리포트 dict."""
    return {
        "diagnostics": [d.model_dump(mode="json") for d in diagnostics],
        "error_count": sum(1 for d in diagnostics if d.severity == "error"),
        "warning_count": sum(1 for d in diagnostics if d.severity == "warning"),
    }
