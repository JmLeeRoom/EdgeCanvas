"""T-304: 에이전트 컨텍스트 토큰 예산 관리 — 단위 테스트.

단위구현계획서.md 제5장 [T-304] 10항 절차를 코드로 검증한다.
- 준비: 15,000자 분량의 모의 긴 에러 메시지 프롬프트 입력.
- 실행: `pytest tests/test_token_manager.py`
- 통과 기준: 트리밍 후 전체 토큰 ≤ 10,000, 핵심 컴파일러 에러 마지막 줄 보존.

카드 12항 실패 대처(트리밍 우선순위)도 함께 검증한다.
"""
from __future__ import annotations

import pytest

from src.agent.token_manager import (
    CRITICAL_SECTION,
    DUPLICATE_ERROR_SECTION,
    SUCCESS_LOG_SECTION,
    SYSTEM_EXAMPLE_SECTION,
    TokenManager,
)

# 핵심 컴파일러 에러 마지막 줄 — 트리밍 후에도 반드시 남아야 한다.
CRITICAL_LAST_LINE = (
    "error: 'lv_label_set_text' undeclared (first use in this function) "
    "at ui_screens.c:42"
)


def _repeat_to_chars(unit: str, min_chars: int) -> str:
    """unit을 반복해 최소 min_chars 길이를 만든다."""
    if not unit:
        raise ValueError("unit must be non-empty")
    n = (min_chars // len(unit)) + 1
    return (unit * n)[:min_chars]


def _build_long_error_body(min_chars: int = 15_000) -> str:
    """15,000자 이상 모의 긴 에러 메시지 본문."""
    line = (
        "compile failed: undefined reference to `lv_obj_align' "
        "in linking stage for ui_screens.o ; diagnostic filler pad "
    )
    return _repeat_to_chars(line, min_chars)


def _build_section(marker: str, body: str) -> str:
    return f"{marker}\n{body}"


def _build_oversized_prompt(*, force_over_10k: bool = True) -> str:
    """섹션 마커가 포함된 비대 프롬프트.

    에러 본문만으로도 15,000자 이상이며, force_over_10k면 토큰이
    10,000을 넘도록 다른 섹션을 충분히 채운다.
    """
    error_body = _build_long_error_body(15_000)
    assert len(error_body) >= 15_000

    critical = _build_section(
        CRITICAL_SECTION,
        error_body + "\n" + CRITICAL_LAST_LINE,
    )

    if force_over_10k:
        # 다양한 토큰을 만들어 cl100k 기준 10k+ 토큰이 되도록 패딩.
        pad_unit = (
            "Project configured successfully and flashed OK with checksum verified. "
        )
        success = _build_section(
            SUCCESS_LOG_SECTION,
            _repeat_to_chars(pad_unit, 40_000),
        )
        dup = _build_section(
            DUPLICATE_ERROR_SECTION,
            _repeat_to_chars(
                "duplicate error: previous round failed with same linker symbol missing. ",
                40_000,
            ),
        )
        example = _build_section(
            SYSTEM_EXAMPLE_SECTION,
            _repeat_to_chars(
                "// system example: lv_obj_t *btn = lv_button_create(scr);\n",
                40_000,
            ),
        )
        return "\n\n".join([success, dup, example, critical])

    return critical


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def manager() -> TokenManager:
    return TokenManager(max_tokens=16_000, trim_target=10_000)


@pytest.fixture
def oversized_prompt() -> str:
    return _build_oversized_prompt(force_over_10k=True)


# ---------------------------------------------------------------------------
# 토큰 계측
# ---------------------------------------------------------------------------


def test_count_tokens_positive_for_nonempty(manager: TokenManager) -> None:
    text = "Hello Solar Pro 3 token budget"
    count = manager.count_tokens(text)
    assert isinstance(count, int)
    assert count > 0


def test_count_tokens_empty_is_zero(manager: TokenManager) -> None:
    assert manager.count_tokens("") == 0


def test_count_tokens_grows_with_length(manager: TokenManager) -> None:
    short = manager.count_tokens("abc")
    long = manager.count_tokens("abc " * 500)
    assert long > short


# ---------------------------------------------------------------------------
# 임계치 감시 (예: 16k)
# ---------------------------------------------------------------------------


def test_exceeds_threshold_false_under_budget(manager: TokenManager) -> None:
    small = "short prompt under budget"
    assert manager.count_tokens(small) < manager.max_tokens
    assert manager.exceeds_threshold(small) is False


def test_exceeds_threshold_true_when_over_16k(manager: TokenManager) -> None:
    # 16k 토큰을 확실히 넘는 긴 텍스트 (반복 단어도 압축 인코딩되므로 여유 있게)
    bulky = _repeat_to_chars(
        "threshold watch padding token sequence alpha beta gamma. ",
        200_000,
    )
    assert manager.count_tokens(bulky) > 16_000
    assert manager.exceeds_threshold(bulky) is True


def test_needs_trim_when_over_trim_target(
    manager: TokenManager, oversized_prompt: str
) -> None:
    assert manager.count_tokens(oversized_prompt) > manager.trim_target
    assert manager.needs_trim(oversized_prompt) is True


# ---------------------------------------------------------------------------
# 카드 10항: 15,000자 에러 프롬프트 → 트리밍 후 ≤10k 토큰 + 마지막 줄 보존
# ---------------------------------------------------------------------------


def test_long_error_prompt_is_at_least_15000_chars(oversized_prompt: str) -> None:
    assert len(oversized_prompt) >= 15_000
    # 에러 본문 구간이 15,000자 요건을 충족
    assert CRITICAL_SECTION in oversized_prompt


def test_trim_reduces_to_at_most_10000_tokens(
    manager: TokenManager, oversized_prompt: str
) -> None:
    before = manager.count_tokens(oversized_prompt)
    assert before > 10_000

    trimmed = manager.trim(oversized_prompt)
    after = manager.count_tokens(trimmed)
    assert after <= 10_000
    assert after < before


def test_trim_preserves_critical_compiler_error_last_line(
    manager: TokenManager, oversized_prompt: str
) -> None:
    trimmed = manager.trim(oversized_prompt)
    assert CRITICAL_LAST_LINE in trimmed


# ---------------------------------------------------------------------------
# 카드 12항: 트리밍 우선순위 (단계적 소거, 최신 핵심 에러는 유지)
# ---------------------------------------------------------------------------


def test_trim_priority_drops_success_logs_first(manager: TokenManager) -> None:
    """1순위: 이전 빌드 정상 로그만 제거해도 예산 내면, 이후 섹션은 유지."""
    critical = _build_section(
        CRITICAL_SECTION,
        "short error body\n" + CRITICAL_LAST_LINE,
    )
    # 성공 로그만 크게 — 제거하면 충분히 작아지고, 나머지 섹션은 소량 유지
    success = _build_section(
        SUCCESS_LOG_SECTION,
        _repeat_to_chars("build succeeded checksum ok. ", 120_000),
    )
    dup = _build_section(DUPLICATE_ERROR_SECTION, "dup err once")
    example = _build_section(SYSTEM_EXAMPLE_SECTION, "lv_label_create(scr);")
    prompt = "\n\n".join([success, dup, example, critical])

    assert manager.count_tokens(prompt) > manager.trim_target
    trimmed = manager.trim(prompt)

    assert CRITICAL_LAST_LINE in trimmed
    assert SUCCESS_LOG_SECTION not in trimmed or "build succeeded" not in trimmed
    # 2·3순위 콘텐츠는 예산이 허용되면 남긴다
    assert "dup err once" in trimmed
    assert "lv_label_create(scr);" in trimmed
    assert manager.count_tokens(trimmed) <= manager.trim_target


def test_trim_priority_then_drops_duplicate_errors(manager: TokenManager) -> None:
    """2순위: 성공 로그 제거 후에도 초과면 중복 에러 로그를 소거."""
    critical = _build_section(
        CRITICAL_SECTION,
        "short error body\n" + CRITICAL_LAST_LINE,
    )
    # 성공만 제거해도 아직 초과하도록 중복 섹션을 충분히 크게
    success = _build_section(
        SUCCESS_LOG_SECTION,
        _repeat_to_chars("build succeeded. ", 80_000),
    )
    dup = _build_section(
        DUPLICATE_ERROR_SECTION,
        _repeat_to_chars("duplicate linker error from prior round. ", 120_000),
    )
    example = _build_section(SYSTEM_EXAMPLE_SECTION, "example_src_keep_me_please();")
    prompt = "\n\n".join([success, dup, example, critical])

    trimmed = manager.trim(prompt)

    assert CRITICAL_LAST_LINE in trimmed
    assert "duplicate linker error" not in trimmed
    assert "example_src_keep_me_please" in trimmed
    assert manager.count_tokens(trimmed) <= manager.trim_target


def test_trim_priority_then_drops_system_example(manager: TokenManager) -> None:
    """3순위: 성공·중복 제거 후에도 초과면 시스템 예제 소스를 소거.

    최신 핵심 에러 문맥은 절대 버리지 않는다.
    """
    critical_body = _repeat_to_chars("critical diagnostic line. ", 5_000)
    critical = _build_section(
        CRITICAL_SECTION,
        critical_body + "\n" + CRITICAL_LAST_LINE,
    )
    success = _build_section(
        SUCCESS_LOG_SECTION,
        _repeat_to_chars("build succeeded. ", 80_000),
    )
    dup = _build_section(
        DUPLICATE_ERROR_SECTION,
        _repeat_to_chars("duplicate error blob. ", 80_000),
    )
    example = _build_section(
        SYSTEM_EXAMPLE_SECTION,
        _repeat_to_chars("system example source line for trimming. ", 120_000),
    )
    prompt = "\n\n".join([success, dup, example, critical])

    trimmed = manager.trim(prompt)

    assert CRITICAL_LAST_LINE in trimmed
    assert "system example source line" not in trimmed
    assert manager.count_tokens(trimmed) <= manager.trim_target


def test_trim_never_drops_latest_critical_error_even_if_still_large(
    manager: TokenManager,
) -> None:
    """핵심 에러만으로도 큰 경우 — 가능하면 축소하되 마지막 줄은 보존."""
    # 마커 없는 / 핵심만 있는 초장문: 꼬리(마지막 줄)는 유지
    body = _repeat_to_chars("huge critical dump line xyz. ", 80_000)
    prompt = body + "\n" + CRITICAL_LAST_LINE
    assert manager.count_tokens(prompt) > manager.trim_target

    trimmed = manager.trim(prompt)
    assert CRITICAL_LAST_LINE in trimmed
    # 마커가 없으면 꼬리 보존 + 앞에서부터 잘라 목표에 맞춤
    assert manager.count_tokens(trimmed) <= manager.trim_target
