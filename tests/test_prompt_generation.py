"""T-302: Solar Pro 3 LVGL UI 레이아웃 생성 프롬프트 — 단위 테스트.

단위구현계획서.md 제5장 [T-302] 10항 절차를 코드로 검증한다.
- 오프라인(API 불필요): `build_layout_generation_prompt`가 만들어낸 프롬프트
  문자열 자체를 검증한다(해상도 동적 매핑, Few-Shot C 코드 블록 >=3개,
  LVGL 9.x 위젯 함수 명명법, 금지어/대체 리스트, ui_screens.c 전용 출력 지시).
- 라이브(@REQUIRES_LIVE_API): 실제 Solar Pro에 프롬프트를 전송해 응답이
  ```c 코드 블록, ui_init() 함수, LVGL 9.x 위젯 함수를 포함하는지 판정한다.
"""
from __future__ import annotations

import os
import re

import pytest
from dotenv import load_dotenv

load_dotenv()

from src.agent.prompts.layout_generator import (  # noqa: E402
    FORBIDDEN_LEGACY_API,
    build_layout_generation_prompt,
)
from src.common.schema import TechnologyKB  # noqa: E402

REQUIRES_LIVE_API = pytest.mark.skipif(
    not os.getenv("UPSTAGE_API_KEY"),
    reason="UPSTAGE_API_KEY가 .env에 설정되어 있지 않습니다.",
)

SAMPLE_REQUIREMENT = (
    "상단에 제목 라벨, 중앙에 온도 표시 라벨, 하단에 설정 화면으로 이동하는 "
    "버튼이 있는 홈 화면을 만들어 주세요."
)


def _count_c_code_blocks(text: str) -> int:
    """```c ... ``` Markdown C 코드 블록 개수를 센다."""
    return len(re.findall(r"```c\b", text))


# ---------------------------------------------------------------------------
# 오프라인 프롬프트 문자열 검증 (API 불필요)
# ---------------------------------------------------------------------------
def test_prompt_embeds_default_resolution():
    """DoD 11-a: 기본 해상도(1024x600) 제약이 프롬프트에 명시돼야 한다."""
    prompt = build_layout_generation_prompt(SAMPLE_REQUIREMENT)
    assert "1024" in prompt
    assert "600" in prompt
    assert "1024x600" in prompt or "1024 x 600" in prompt


def test_prompt_resolution_is_dynamic_via_kb():
    """DoD 11-a: 해상도가 하드코딩이 아니라 런타임 입력으로 동적 매핑돼야 한다.

    기본이 아닌 해상도(800x480)를 주면 그 값이 프롬프트에 나타나고
    기본값(1024x600)은 나타나지 않아야 한다.
    """
    kb = TechnologyKB(resolution=(800, 480))
    prompt = build_layout_generation_prompt(SAMPLE_REQUIREMENT, tech_kb=kb)
    assert "800" in prompt
    assert "480" in prompt
    assert "1024x600" not in prompt


def test_prompt_resolution_dynamic_via_explicit_tuple():
    """TechnologyKB 없이 resolution 인자만으로도 동적 매핑돼야 한다."""
    prompt = build_layout_generation_prompt(
        SAMPLE_REQUIREMENT, resolution=(1280, 720)
    )
    assert "1280" in prompt
    assert "720" in prompt


def test_prompt_contains_user_requirement():
    """사용자 UI 요구사항 텍스트가 프롬프트 컨텍스트에 포함돼야 한다."""
    prompt = build_layout_generation_prompt(SAMPLE_REQUIREMENT)
    assert SAMPLE_REQUIREMENT in prompt


def test_prompt_contains_at_least_three_c_code_blocks():
    """카드 8-3: 최소 3개의 Few-Shot C 코드 블록 예시를 포함해야 한다."""
    prompt = build_layout_generation_prompt(SAMPLE_REQUIREMENT)
    assert _count_c_code_blocks(prompt) >= 3


def test_prompt_contains_lvgl9_widget_naming():
    """카드 8-2: LVGL 9.x 위젯 생성 함수 명명법이 명시돼야 한다."""
    prompt = build_layout_generation_prompt(SAMPLE_REQUIREMENT)
    for fn in ("lv_obj_create", "lv_button_create", "lv_label_create"):
        assert fn in prompt


def test_prompt_defines_layout_and_event_rules():
    """카드 8-2: Flex/Grid 레이아웃 규칙과 화면 전환 이벤트 연결 양식이 있어야 한다."""
    prompt = build_layout_generation_prompt(SAMPLE_REQUIREMENT)
    assert "Flex" in prompt or "flex" in prompt
    assert "Grid" in prompt or "grid" in prompt
    assert "lv_obj_add_event_cb" in prompt


def test_prompt_enforces_ui_screens_only_output():
    """DoD 11-b: main 함수/헤더 중복을 배제하고 ui_screens.c 전용 출력을 지시해야 한다."""
    prompt = build_layout_generation_prompt(SAMPLE_REQUIREMENT)
    assert "ui_screens.c" in prompt
    assert "main" in prompt  # "main 함수 금지" 문구
    assert "ui_init" in prompt


# ---------------------------------------------------------------------------
# 카드 12항 실패 시 대처: LVGL 9.x API 금지어 및 대체 리스트
# ---------------------------------------------------------------------------
def test_prompt_contains_forbidden_legacy_api_list():
    """카드 12: 프롬프트 최상단에 LVGL 8.x 금지어/대체 리스트가 명시돼야 한다."""
    prompt = build_layout_generation_prompt(SAMPLE_REQUIREMENT)
    assert "금지" in prompt
    # 레거시 8.x API가 금지어로 실제 언급돼야 한다.
    assert "lv_btn_set_fit" in prompt


def test_forbidden_legacy_api_maps_to_9x_replacement():
    """금지어 리스트가 (레거시 -> 9.x 대체) 매핑을 제공해야 한다."""
    assert len(FORBIDDEN_LEGACY_API) >= 1
    # 대표적 레거시 API가 매핑에 존재하고 9.x 대체가 비어있지 않아야 한다.
    assert "lv_btn_set_fit" in FORBIDDEN_LEGACY_API
    for legacy, replacement in FORBIDDEN_LEGACY_API.items():
        assert legacy and replacement


def test_forbidden_api_list_rendered_near_top():
    """카드 12: 금지어 리스트가 사용자 요구사항 컨텍스트보다 앞(최상단)에 배치돼야 한다."""
    prompt = build_layout_generation_prompt(SAMPLE_REQUIREMENT)
    assert prompt.index("lv_btn_set_fit") < prompt.index(SAMPLE_REQUIREMENT)


# ---------------------------------------------------------------------------
# 라이브 API 검증 — 카드 10 통과 기준 판정
# ---------------------------------------------------------------------------
@REQUIRES_LIVE_API
def test_solar_generates_lvgl9_c_code_live():
    """카드 10: 실제 Solar Pro 응답이 ```c 코드 블록, ui_init() 함수,
    LVGL 9.x 규격 위젯 함수를 포함해야 한다."""
    from src.common.upstage_client import UpstageClient

    prompt = build_layout_generation_prompt(SAMPLE_REQUIREMENT)
    client = UpstageClient()
    response = client.chat(prompt)

    assert response is not None and len(response) > 0
    assert "```c" in response, "응답에 Markdown C 코드 블록이 없습니다."
    assert "ui_init" in response, "응답에 ui_init() 함수가 없습니다."
    assert re.search(r"lv_\w+_create", response), (
        "응답에 LVGL 9.x 위젯 생성 함수가 없습니다."
    )
    print(f"[T-302] 라이브 응답 길이 {len(response)}자")
