"""T-702: 자가 수정 루프(Self-healing) 재진입 및 라운드 제어기.

이전 빌드 실패(C 컴파일러 에러)와 렌더링 검증 실패(위젯/OCR) 내역을
Solar Pro 3 코드 생성 노드 입력으로 환류한다.

라운드 상한: sim `self_correct` 최대 5회 / `self_correct_hw` 최대 2회.
카드 12항: 3라운드 연속 실패 시 초기 템플릿 백업을 강제 복원한 뒤 재시도.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from src.builder.error_parser import ParsedDiagnostic, parse_compiler_log

SIM_ROUND_MAX = 5
HW_ROUND_MAX = 2
CONSECUTIVE_FAIL_RESTORE = 3

RunMode = Literal["sim", "hw"]
Verdict = Literal["PASS", "FAIL"]


@dataclass
class HealingResult:
    """한 번의 healing step 결과 — LLM 재진입 컨텍스트와 탈출 판정."""

    round: int
    llm_context: str
    previous_error: str
    code_for_retry: str
    exit_loop: bool = False
    force_exit: bool = False
    verdict: Verdict | None = None
    restored_from_backup: bool = False
    mode: RunMode = "sim"


@dataclass
class HealingController:
    """Self-healing 프롬프트 엔진 + sim/hw 분리 라운드 카운터.

    orchestrator.py의 `self_correct` / `self_correct_hw` 노드에서 호출한다.
    """

    mode: RunMode = "sim"
    initial_code_backup: str = ""
    sim_max: int = SIM_ROUND_MAX
    hw_max: int = HW_ROUND_MAX
    _round: int = field(default=0, init=False, repr=False)
    _consecutive_fails: int = field(default=0, init=False, repr=False)
    _exited: bool = field(default=False, init=False, repr=False)
    _log: list[dict[str, Any]] = field(default_factory=list, init=False, repr=False)
    _last_error: str = field(default="", init=False, repr=False)

    @property
    def round_max(self) -> int:
        return self.hw_max if self.mode == "hw" else self.sim_max

    @property
    def current_round(self) -> int:
        return self._round

    def mark_success(self) -> None:
        """검증 PASS 시 연속 실패 스트릭을 리셋한다."""
        self._consecutive_fails = 0

    def build_healing_prompt(
        self,
        *,
        compile_log: str,
        vision_annotations: str = "",
        previous_error: str = "",
    ) -> str:
        """에러 로그 + 비전 어노테이션 → Self-healing 유도 프롬프트."""
        diagnostics = parse_compiler_log(compile_log) if compile_log.strip() else []
        lines: list[str] = [
            "# Self-healing Feedback for Solar Pro 3",
            "",
            "이전 빌드/검증이 실패했습니다. 아래 피드백을 참고하여 UI 코드를 수정하세요.",
            "",
        ]

        if previous_error.strip():
            lines.extend(
                [
                    "## 직전(previous) 발생 에러",
                    previous_error.strip(),
                    "",
                ]
            )

        lines.append("## 컴파일 에러")
        if diagnostics:
            for d in diagnostics:
                lines.append(self._format_diagnostic_fix_hint(d))
            lines.append("")
            lines.append("### 원문 로그")
            lines.append(compile_log.strip())
        elif compile_log.strip():
            lines.append(compile_log.strip())
        else:
            lines.append("(컴파일 에러 없음)")
        lines.append("")

        if vision_annotations.strip():
            lines.extend(
                [
                    "## 비전 판정 어노테이션",
                    vision_annotations.strip(),
                    "",
                ]
            )

        primary_line = self._primary_fix_line(diagnostics)
        if primary_line is not None:
            lines.append(
                f"다음 컴파일 에러를 참고해 코드의 {primary_line}번째 라인을 수정하라."
            )
        else:
            lines.append(
                "다음 컴파일 에러와 비전 판정을 참고해 관련 코드 라인을 수정하라."
            )

        return "\n".join(lines)

    @staticmethod
    def _primary_fix_line(diagnostics: list[ParsedDiagnostic]) -> int | None:
        for d in diagnostics:
            if d.severity == "error" and d.line is not None:
                return d.line
        for d in diagnostics:
            if d.line is not None:
                return d.line
        return None

    @staticmethod
    def _format_diagnostic_fix_hint(d: ParsedDiagnostic) -> str:
        loc = d.file or "<unknown>"
        if d.line is not None:
            loc = f"{loc}:{d.line}"
            if d.column is not None:
                loc = f"{loc}:{d.column}"
        msg = d.message or ""
        if d.line is not None:
            return (
                f"- [{d.severity}] {loc}: {msg} "
                f"→ fix line {d.line} / {d.line}번째 라인을 수정하라"
            )
        return f"- [{d.severity}] {loc}: {msg}"

    def step(
        self,
        *,
        compile_log: str = "",
        vision_annotations: str = "",
        current_code: str = "",
        failed: bool = True,
    ) -> HealingResult:
        """힐링 라운드를 1회 진행하고 LLM 재진입 컨텍스트를 반환한다.

        라운드 상한 도달 시 `verdict=FAIL`, `exit_loop=True`로 정상 탈출한다.
        3회 연속 실패 시 `initial_code_backup`을 강제 복원한다.
        """
        if self._exited:
            return HealingResult(
                round=self._round,
                llm_context=self._last_context_or_exit(compile_log, vision_annotations),
                previous_error=self._last_error or compile_log.strip(),
                code_for_retry=self.initial_code_backup or current_code,
                exit_loop=True,
                force_exit=True,
                verdict="FAIL",
                restored_from_backup=False,
                mode=self.mode,
            )

        self._round += 1
        previous_error = self._extract_error_summary(compile_log) or compile_log.strip()
        self._last_error = previous_error

        restored = False
        code_for_retry = current_code

        if failed:
            self._consecutive_fails += 1
            if self._consecutive_fails >= CONSECUTIVE_FAIL_RESTORE:
                code_for_retry = self.initial_code_backup
                restored = True
                self._consecutive_fails = 0
        else:
            self._consecutive_fails = 0

        hit_max = self._round >= self.round_max
        if hit_max:
            self._exited = True

        llm_context = self.build_healing_prompt(
            compile_log=compile_log,
            vision_annotations=vision_annotations,
            previous_error=previous_error,
        )
        if restored:
            llm_context += (
                "\n\n## 정책: 템플릿 백업 복원\n"
                "3라운드 연속 실패로 초기 템플릿 백업 코드원본을 강제 복원했다. "
                "이 백업을 기준으로 다시 수정을 시도하라.\n"
            )

        result = HealingResult(
            round=self._round,
            llm_context=llm_context,
            previous_error=previous_error,
            code_for_retry=code_for_retry,
            exit_loop=hit_max,
            force_exit=hit_max,
            verdict="FAIL" if hit_max else None,
            restored_from_backup=restored,
            mode=self.mode,
        )

        self._log.append(
            {
                "round": result.round,
                "mode": self.mode,
                "previous_error": result.previous_error,
                "llm_context": result.llm_context,
                "code_snapshot": code_for_retry,
                "restored_from_backup": restored,
                "exit_loop": result.exit_loop,
                "verdict": result.verdict,
            }
        )
        return result

    def _last_context_or_exit(self, compile_log: str, vision_annotations: str) -> str:
        if self._log:
            return str(self._log[-1].get("llm_context", ""))
        return self.build_healing_prompt(
            compile_log=compile_log,
            vision_annotations=vision_annotations,
            previous_error=compile_log.strip(),
        )

    @staticmethod
    def _extract_error_summary(compile_log: str) -> str:
        diagnostics = parse_compiler_log(compile_log) if compile_log.strip() else []
        errors = [d for d in diagnostics if d.severity == "error"]
        if not errors:
            return compile_log.strip()
        parts: list[str] = []
        for d in errors:
            loc = d.file or ""
            if d.line is not None:
                loc = f"{loc}:{d.line}" if loc else str(d.line)
            parts.append(f"{loc}: {d.message}".strip(": "))
        return "\n".join(parts)

    def round_log(self) -> list[dict[str, Any]]:
        """검증 기록용 라운드별 코드/컨텍스트 변천 로그."""
        return list(self._log)

    def to_state_update(self, result: HealingResult) -> dict[str, Any]:
        """HMIAgentState 병합용 부분 dict (orchestrator 연동 헬퍼)."""
        key = "hw_round" if self.mode == "hw" else "sim_round"
        update: dict[str, Any] = {
            key: result.round,
            "generated_code": result.code_for_retry,
        }
        if result.exit_loop:
            update["verdict"] = result.verdict or "FAIL"
            update["force_exit"] = True
        return update
