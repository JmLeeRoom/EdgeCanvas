"""T-304: 에이전트 컨텍스트 토큰 예산 관리 모듈.

단위구현계획서.md 제5장 [T-304]의 8항 구현 내용을 따른다.
API 전송 전 프롬프트 토큰을 tiktoken으로 실측하고, 임계치(기본 16k)를
감시하며, 초과 조짐 시 우선순위 정책에 따라 컨텍스트를 트리밍한다.

트리밍 우선순위 (카드 12항)
----------------------------
1) 이전 빌드 정상 로그 (SUCCESS_LOG_SECTION)
2) 중복 빌드 에러 로그 (DUPLICATE_ERROR_SECTION)
3) 시스템 예제 소스 (SYSTEM_EXAMPLE_SECTION)

최신 핵심 컴파일러 에러(CRITICAL_SECTION / 마지막 줄)는 소거하지 않는다.
섹션 마커가 없는 비구조 텍스트는 꼬리(마지막 줄)를 보존한 채 앞에서부터 자른다.
"""
from __future__ import annotations

from dataclasses import dataclass

import tiktoken

# ---------------------------------------------------------------------------
# section markers — 프롬프트 조립 시 삽입, 트리밍 정책이 이 경계를 인식한다
# ---------------------------------------------------------------------------

SUCCESS_LOG_SECTION = "===PREVIOUS_SUCCESS_LOG==="
DUPLICATE_ERROR_SECTION = "===DUPLICATE_ERROR_LOG==="
SYSTEM_EXAMPLE_SECTION = "===SYSTEM_EXAMPLE_SOURCE==="
CRITICAL_SECTION = "===CRITICAL_COMPILER_ERROR==="

# 제거 우선순위 (앞일수록 먼저 버림)
_TRIM_PRIORITY: tuple[str, ...] = (
    SUCCESS_LOG_SECTION,
    DUPLICATE_ERROR_SECTION,
    SYSTEM_EXAMPLE_SECTION,
)

_ALL_MARKERS: tuple[str, ...] = (
    SUCCESS_LOG_SECTION,
    DUPLICATE_ERROR_SECTION,
    SYSTEM_EXAMPLE_SECTION,
    CRITICAL_SECTION,
)

_DEFAULT_ENCODING = "cl100k_base"
_DEFAULT_MAX_TOKENS = 16_000
_DEFAULT_TRIM_TARGET = 10_000


@dataclass
class TrimResult:
    """트리밍 결과 요약 (검증/로그용)."""

    text: str
    tokens_before: int
    tokens_after: int
    dropped_sections: list[str]


class TokenManager:
    """프롬프트 토큰 계측 · 임계치 감시 · 우선순위 컨텍스트 트리밍."""

    def __init__(
        self,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
        trim_target: int = _DEFAULT_TRIM_TARGET,
        encoding_name: str = _DEFAULT_ENCODING,
    ) -> None:
        if max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if trim_target <= 0:
            raise ValueError("trim_target must be positive")
        if trim_target > max_tokens:
            raise ValueError("trim_target must be <= max_tokens")

        self.max_tokens = max_tokens
        self.trim_target = trim_target
        self._encoding = tiktoken.get_encoding(encoding_name)

    # ------------------------------------------------------------------ #
    # public — 계측 / 감시
    # ------------------------------------------------------------------ #
    def count_tokens(self, text: str) -> int:
        """API 전송 전 프롬프트의 토큰 수를 실측한다."""
        if not text:
            return 0
        return len(self._encoding.encode(text))

    def exceeds_threshold(self, text: str) -> bool:
        """최대 허용량(예: 16k)을 초과했는지 감시한다."""
        return self.count_tokens(text) > self.max_tokens

    def needs_trim(self, text: str) -> bool:
        """trim_target을 넘어 트리밍이 필요한지 여부."""
        return self.count_tokens(text) > self.trim_target

    # ------------------------------------------------------------------ #
    # public — 트리밍
    # ------------------------------------------------------------------ #
    def trim(self, text: str, target_tokens: int | None = None) -> str:
        """우선순위에 따라 컨텍스트를 소거해 target_tokens 이하로 만든다.

        target_tokens 기본값은 self.trim_target (카드 10항: 10,000).
        """
        return self.trim_detailed(text, target_tokens=target_tokens).text

    def trim_detailed(
        self, text: str, target_tokens: int | None = None
    ) -> TrimResult:
        """trim()과 동일하되 드롭된 섹션·토큰 수치를 함께 반환한다."""
        target = self.trim_target if target_tokens is None else target_tokens
        if target <= 0:
            raise ValueError("target_tokens must be positive")

        before = self.count_tokens(text)
        if before <= target:
            return TrimResult(
                text=text,
                tokens_before=before,
                tokens_after=before,
                dropped_sections=[],
            )

        sections = self._split_sections(text)
        dropped: list[str] = []

        if sections is not None:
            # 구조화 프롬프트: 우선순위에 따라 섹션 본문을 단계적으로 비운다.
            for marker in _TRIM_PRIORITY:
                if self.count_tokens(self._join_sections(sections)) <= target:
                    break
                if marker in sections and sections[marker].strip():
                    sections[marker] = ""
                    dropped.append(marker)

            assembled = self._join_sections(sections)
            if self.count_tokens(assembled) > target:
                # 예산이 여전히 넘치면 핵심 섹션 본문을 꼬리 보존 방식으로 축소.
                # CRITICAL 마커와 마지막 줄은 유지한다.
                critical_body = sections.get(CRITICAL_SECTION, "")
                sections[CRITICAL_SECTION] = self._truncate_preserving_tail(
                    critical_body,
                    max_tokens=max(1, target - self._overhead_tokens(sections)),
                )
                assembled = self._join_sections(sections)
        else:
            # 비구조 텍스트: 앞에서부터 버리고 꼬리(마지막 줄) 보존.
            assembled = self._truncate_preserving_tail(text, max_tokens=target)

        after = self.count_tokens(assembled)
        # 최후 안전망 — 그래도 초과하면 꼬리만 강제 축소
        if after > target:
            assembled = self._truncate_preserving_tail(assembled, max_tokens=target)
            after = self.count_tokens(assembled)

        return TrimResult(
            text=assembled,
            tokens_before=before,
            tokens_after=after,
            dropped_sections=dropped,
        )

    # ------------------------------------------------------------------ #
    # private
    # ------------------------------------------------------------------ #
    def _split_sections(self, text: str) -> dict[str, str] | None:
        """마커 기준으로 섹션을 분리. 마커가 하나도 없으면 None."""
        positions: list[tuple[int, str]] = []
        for marker in _ALL_MARKERS:
            idx = text.find(marker)
            if idx >= 0:
                positions.append((idx, marker))

        if not positions:
            return None

        positions.sort(key=lambda x: x[0])
        sections: dict[str, str] = {m: "" for m in _ALL_MARKERS}
        preamble_end = positions[0][0]
        preamble = text[:preamble_end].strip()

        for i, (pos, marker) in enumerate(positions):
            start = pos + len(marker)
            end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
            sections[marker] = text[start:end].strip("\n")

        # 마커 앞 프리앰블은 CRITICAL에 붙이지 않고 별도 보관용으로 preamble 키 사용
        if preamble:
            sections["_preamble"] = preamble
        return sections

    def _join_sections(self, sections: dict[str, str]) -> str:
        parts: list[str] = []
        preamble = sections.get("_preamble", "").strip()
        if preamble:
            parts.append(preamble)

        for marker in _ALL_MARKERS:
            body = sections.get(marker, "")
            if body.strip():
                parts.append(f"{marker}\n{body.strip()}")
        return "\n\n".join(parts)

    def _overhead_tokens(self, sections: dict[str, str]) -> int:
        """CRITICAL을 제외한 잔여 섹션·마커 오버헤드 토큰 수."""
        probe = dict(sections)
        probe[CRITICAL_SECTION] = ""
        return self.count_tokens(self._join_sections(probe)) + self.count_tokens(
            CRITICAL_SECTION + "\n"
        )

    def _truncate_preserving_tail(self, text: str, max_tokens: int) -> str:
        """마지막 비어 있지 않은 줄을 보존하며 앞에서부터 잘라 max_tokens 이하로."""
        if max_tokens <= 0:
            return ""
        if self.count_tokens(text) <= max_tokens:
            return text

        lines = text.splitlines()
        last_line = ""
        for line in reversed(lines):
            if line.strip():
                last_line = line
                break

        last_tokens = self.count_tokens(last_line)
        if last_tokens >= max_tokens:
            # 마지막 줄만으로도 예산 초과 → 줄 자체를 뒤에서부터 토큰 자른다.
            return self._decode_tail_tokens(last_line, max_tokens)

        # 마지막 줄 직전까지를 head로 취급
        if last_line and text.rstrip().endswith(last_line):
            head = text[: text.rstrip().rfind(last_line)].rstrip()
        else:
            head = text

        if not head:
            return last_line

        # "\n" 결합 토큰을 예산에 반영해 off-by-one을 피한다.
        sep = "\n"
        sep_tokens = self.count_tokens(sep)
        budget_for_head = max_tokens - last_tokens - sep_tokens
        if budget_for_head <= 0:
            return last_line

        head_trimmed = self._decode_tail_tokens(head, budget_for_head)
        if head_trimmed:
            candidate = head_trimmed.rstrip() + sep + last_line
            # 인코딩 경계로 1토큰 넘을 수 있어 재검증
            if self.count_tokens(candidate) <= max_tokens:
                return candidate
            return self._decode_tail_tokens(candidate, max_tokens)
        return last_line

    def _decode_tail_tokens(self, text: str, max_tokens: int) -> str:
        """텍스트의 뒤쪽 max_tokens개 토큰만 남긴다 (머리 절단)."""
        if max_tokens <= 0:
            return ""
        tokens = self._encoding.encode(text)
        if len(tokens) <= max_tokens:
            return text
        return self._encoding.decode(tokens[-max_tokens:])
