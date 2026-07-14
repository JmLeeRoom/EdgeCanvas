"""T-503: GCC/Clang 컴파일러 에러 로그 구문 분석기 — 단위 테스트.

단위구현계획서.md 제5장 [T-503] 10항 절차를 코드로 검증한다.
- 준비: 고의로 세미콜론을 빠뜨린 모의 GCC 에러 텍스트
  (`tests/data/gcc_missing_semicolon.log`).
- 실행: `pytest tests/test_compiler_error_parser.py`
- 통과 기준: 파서 결과 객체에 파일 경로, 라인 번호(int), 에러 내용 문자열이
  정밀 매핑 복구된다.

카드 11항 DoD(GCC 컴파일 에러 인식, warning/error severity)와
카드 12항 폴백(링커 `undefined reference to...`) 시나리오를 함께 검증한다.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.builder.error_parser import ParsedDiagnostic, parse_compiler_log

DATA_DIR = Path(__file__).parent / "data"
MISSING_SEMICOLON_LOG = DATA_DIR / "gcc_missing_semicolon.log"


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def semicolon_log() -> str:
    return MISSING_SEMICOLON_LOG.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 카드 10항: GCC 표준 포맷 file:line:col: error: message
# ---------------------------------------------------------------------------

def test_gcc_error_extracts_file_line_message():
    log = "main/app_main.c:12:5: error: expected ';' before 'return'\n"
    results = parse_compiler_log(log)

    assert len(results) == 1
    d = results[0]
    assert isinstance(d, ParsedDiagnostic)
    assert d.file == "main/app_main.c"
    assert d.line == 12
    assert isinstance(d.line, int)
    assert d.column == 5
    assert d.severity == "error"
    assert "expected ';' before 'return'" in d.message


def test_missing_semicolon_fixture_maps_file_line_message(semicolon_log: str):
    results = parse_compiler_log(semicolon_log)
    errors = [d for d in results if d.severity == "error" and d.file]

    assert len(errors) >= 1
    d = errors[0]
    assert d.file == "main/ui_screens.c"
    assert d.line == 42
    assert isinstance(d.line, int)
    assert "expected ';' before 'lv_obj_set_size'" in d.message


def test_parsed_diagnostics_are_json_serializable(semicolon_log: str):
    results = parse_compiler_log(semicolon_log)
    payload = [d.model_dump(mode="json") for d in results]
    text = json.dumps({"diagnostics": payload}, ensure_ascii=False, indent=2)
    restored = json.loads(text)

    assert "diagnostics" in restored
    assert restored["diagnostics"][0]["file"] == "main/ui_screens.c"
    assert restored["diagnostics"][0]["line"] == 42


# ---------------------------------------------------------------------------
# 카드 11항 DoD: warning vs error severity
# ---------------------------------------------------------------------------

def test_severity_distinguishes_warning_and_error():
    log = (
        "main/foo.c:10:3: warning: unused variable 'x' [-Wunused-variable]\n"
        "main/foo.c:20:1: error: undeclared identifier 'bar'\n"
    )
    results = parse_compiler_log(log)

    assert len(results) == 2
    assert results[0].severity == "warning"
    assert results[0].file == "main/foo.c"
    assert results[0].line == 10
    assert "unused variable" in results[0].message

    assert results[1].severity == "error"
    assert results[1].line == 20
    assert "undeclared identifier" in results[1].message


def test_fixture_includes_warning_severity(semicolon_log: str):
    results = parse_compiler_log(semicolon_log)
    warnings = [d for d in results if d.severity == "warning"]

    assert len(warnings) >= 1
    assert warnings[0].file == "main/ui_screens.c"
    assert warnings[0].line == 45
    assert "unused variable" in warnings[0].message


# ---------------------------------------------------------------------------
# 카드 12항: 링커 undefined reference 분기
# ---------------------------------------------------------------------------

def test_linker_undefined_reference_is_parsed():
    log = (
        "c:/esp/xtensa-esp-elf/bin/ld.exe: "
        "esp-idf/main/libmain.a(app_main.c.obj):(.text.app_main+0x20): "
        "undefined reference to `lv_label_create'\n"
    )
    results = parse_compiler_log(log)

    assert len(results) >= 1
    d = results[0]
    assert d.severity == "error"
    assert "undefined reference" in d.message.lower()
    assert d.symbol == "lv_label_create"
    assert d.function == "app_main" or d.file is not None


def test_linker_and_compile_errors_in_same_log():
    log = (
        "main/ui.c:8:1: error: expected '}' at end of input\n"
        "ld.exe: main/ui.c.obj:(.text.create_screen+0x10): "
        "undefined reference to `missing_symbol'\n"
    )
    results = parse_compiler_log(log)

    compile_errs = [d for d in results if d.file == "main/ui.c" and d.line == 8]
    linker_errs = [d for d in results if d.symbol == "missing_symbol"]

    assert len(compile_errs) == 1
    assert compile_errs[0].severity == "error"
    assert len(linker_errs) == 1
    assert linker_errs[0].severity == "error"


# ---------------------------------------------------------------------------
# 함수/심볼 속성 분리 (구현내용 3항)
# ---------------------------------------------------------------------------

def test_extracts_function_from_in_function_context(semicolon_log: str):
    results = parse_compiler_log(semicolon_log)
    with_func = [d for d in results if d.function == "create_home_screen"]

    assert len(with_func) >= 1
    assert with_func[0].line == 42
