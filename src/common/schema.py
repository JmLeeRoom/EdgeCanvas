"""T-203: Technology KB Pydantic 스키마.

단위구현계획서.md 제5장 [T-203] 8-1항 구현 내용을 따른다.
분석된 데이터시트 핵심 스펙(T-202 산출물)을 코드 생성기(T-301/302)와
보드 프로필 매퍼가 손쉽게 읽을 수 있도록 표준화된 구조로 정의한다.

12항 실패 시 대처: 필수 정보(해상도 등)가 누락돼도 인스턴스화가 실패하지
않도록, Waveshare 기본 사양(1024x600)을 Default Factory로 제공한다.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

DEFAULT_RESOLUTION: tuple[int, int] = (1024, 600)


class TechnologyKB(BaseModel):
    """표준화된 기술 지식 베이스(Technology KB) 스키마.

    필드는 단위구현계획서.md [T-203] 8-1항이 명시한 5개로 고정된다.
    display_controller/color_depth/touch_ic는 정보가 없으면 빈 문자열,
    resolution은 Waveshare 기본 사양(1024x600), pin_config는 빈 dict로
    안전하게 폴백한다(12항 대책).
    """

    display_controller: str = ""
    resolution: tuple[int, int] = Field(default_factory=lambda: DEFAULT_RESOLUTION)
    color_depth: str = ""
    touch_ic: str = ""
    pin_config: dict = Field(default_factory=dict)
