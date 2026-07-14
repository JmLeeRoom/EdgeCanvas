"""T-702: 자가 수정 루프(Self-healing) 재진입 및 라운드 제어기 — 단위 테스트.

단위구현계획서.md 제5장 [T-702] 10항 절차를 코드로 검증한다.
- 준비: 1회차 컴파일 에러 상태 로그 객체 제공.
- 실행: `pytest tests/test_healing_controller.py`
- 통과 기준: 반환된 차회차 LLM 전송용 컨텍스트에 직전 발생 에러 정보 문자열이
  명시 포함되어 있으며, 자가 수정 5회째 호출 시 에이전트 기동이 실패 판정과
  함께 정상 탈출 복귀한다.

카드 12항 실패 대처(3라운드 연속 실패 시 초기 템플릿 백업 복원)도 검증한다.
"""
from __future__ import annotations

from src.agent.healing_controller import (
    HW_ROUND_MAX,
    SIM_ROUND_MAX,
    HealingController,
    HealingResult,
)
from src.builder.error_parser import parse_compiler_log


# 1회차 컴파일 에러 상태 로그 (카드 10항 준비물)
ROUND1_COMPILE_LOG = (
    "main/ui_screens.c:42:5: error: expected ';' before 'lv_obj_set_size'\n"
    "main/ui_screens.c:42:5: note: to match this '('\n"
)


def test_healing_context_includes_previous_error_string():
    """차회차 LLM 컨텍스트에 직전 에러 문자열이 명시 포함된다."""
    ctrl = HealingController(
        mode="sim",
        initial_code_backup="/* template backup */\nint ui_init(void) { return 0; }\n",
    )
    result = ctrl.step(
        compile_log=ROUND1_COMPILE_LOG,
        vision_annotations="위젯 누락: btn_start at (120,80)",
        current_code="int ui_init(void) { lv_obj_set_size(btn 120, 80) return 0; }\n",
    )

    assert isinstance(result, HealingResult)
    assert result.exit_loop is False
    assert result.verdict is None
    assert result.round == 1
    assert ROUND1_COMPILE_LOG.strip() in result.llm_context or (
        "expected ';' before 'lv_obj_set_size'" in result.llm_context
    )
    assert "이전" in result.llm_context or "previous" in result.llm_context.lower() or (
        "직전" in result.llm_context
    ) or ("error" in result.llm_context.lower())
    # Self-healing 유도: N번째 라인 수정 지시
    assert "42" in result.llm_context
    assert "수정" in result.llm_context or "fix" in result.llm_context.lower()
    # 비전 어노테이션 환류
    assert "btn_start" in result.llm_context or "위젯" in result.llm_context


def test_fifth_sim_round_fails_and_exits_cleanly():
    """시뮬 자가 수정 5회째 호출 시 FAIL 판정 + 정상 탈출."""
    ctrl = HealingController(mode="sim", initial_code_backup="/* backup */\n")
    last: HealingResult | None = None

    for i in range(SIM_ROUND_MAX):
        last = ctrl.step(
            compile_log=(
                f"main/ui_screens.c:{40 + i}:1: error: syntax error round {i + 1}\n"
            ),
            vision_annotations=f"OCR mismatch round {i + 1}",
            current_code=f"/* broken code round {i + 1} */\n",
        )

    assert last is not None
    assert last.round == SIM_ROUND_MAX
    assert last.exit_loop is True
    assert last.verdict == "FAIL"
    assert last.force_exit is True
    # 상한 도달 후에도 직전 에러 문자열은 컨텍스트에 남긴다
    assert "syntax error round 5" in last.llm_context or "round 5" in last.llm_context


def test_sixth_call_after_max_still_exits_fail():
    """라운드 상한 이후 추가 호출도 FAIL 탈출을 유지한다 (idempotent exit)."""
    ctrl = HealingController(mode="sim", initial_code_backup="/* backup */\n")
    for i in range(SIM_ROUND_MAX):
        ctrl.step(
            compile_log=f"err:{i + 1}\n",
            current_code="broken",
        )
    again = ctrl.step(compile_log="err:overflow\n", current_code="broken")
    assert again.exit_loop is True
    assert again.verdict == "FAIL"
    assert again.round == SIM_ROUND_MAX


def test_hw_mode_max_two_rounds():
    """self_correct_hw 최대 2회 분리 제어."""
    ctrl = HealingController(mode="hw", initial_code_backup="/* hw backup */\n")
    r1 = ctrl.step(compile_log="hw err 1\n", current_code="c1")
    assert r1.exit_loop is False
    assert r1.round == 1

    r2 = ctrl.step(compile_log="hw err 2\n", current_code="c2")
    assert r2.round == HW_ROUND_MAX
    assert r2.exit_loop is True
    assert r2.verdict == "FAIL"


def test_three_consecutive_failures_restores_template_backup():
    """카드 12항: 3라운드 연속 실패 시 초기 템플릿 백업을 강제 복원한 뒤 재시도."""
    backup = "/* INITIAL TEMPLATE */\nvoid ui_create(void) { lv_obj_t *scr = lv_scr_act(); }\n"
    ctrl = HealingController(mode="sim", initial_code_backup=backup)

    r1 = ctrl.step(
        compile_log="main/a.c:1:1: error: bad1\n",
        current_code="/* mutated 1 */\n",
    )
    assert r1.restored_from_backup is False
    assert r1.code_for_retry != backup

    r2 = ctrl.step(
        compile_log="main/a.c:2:1: error: bad2\n",
        current_code="/* mutated 2 */\n",
    )
    assert r2.restored_from_backup is False

    r3 = ctrl.step(
        compile_log="main/a.c:3:1: error: bad3\n",
        current_code="/* mutated 3 */\n",
    )
    assert r3.restored_from_backup is True
    assert r3.code_for_retry == backup
    assert "템플릿" in r3.llm_context or "backup" in r3.llm_context.lower() or (
        "복원" in r3.llm_context
    )


def test_prompt_engine_uses_parsed_line_number():
    """에러 파서 연동: 진단 line이 있으면 'N번째 라인 수정' 형태의 프롬프트를 만든다."""
    diagnostics = parse_compiler_log(ROUND1_COMPILE_LOG)
    assert diagnostics and diagnostics[0].line == 42

    ctrl = HealingController(mode="sim", initial_code_backup="/* t */\n")
    prompt = ctrl.build_healing_prompt(
        compile_log=ROUND1_COMPILE_LOG,
        vision_annotations="missing label lbl_temp",
        previous_error="expected ';' before 'lv_obj_set_size'",
    )
    assert "42" in prompt
    assert "라인" in prompt or "line" in prompt.lower()
    assert "lv_obj_set_size" in prompt or "expected" in prompt
    assert "lbl_temp" in prompt or "missing label" in prompt


def test_success_resets_consecutive_fail_streak():
    """중간 PASS(성공) 시 연속 실패 카운터가 리셋되어 백업 복원이 지연된다."""
    backup = "/* backup ok */\n"
    ctrl = HealingController(mode="sim", initial_code_backup=backup)

    ctrl.step(compile_log="e1\n", current_code="m1", failed=True)
    ctrl.step(compile_log="e2\n", current_code="m2", failed=True)
    # 성공으로 스트릭 리셋
    ctrl.mark_success()
    r = ctrl.step(compile_log="e3\n", current_code="m3", failed=True)
    assert r.restored_from_backup is False
    assert r.round == 3


def test_round_transitions_log_shape():
    """검증 기록용 라운드 로그 항목에 필수 필드가 있다."""
    ctrl = HealingController(mode="sim", initial_code_backup="/* b */\n")
    ctrl.step(compile_log=ROUND1_COMPILE_LOG, current_code="c0")
    log = ctrl.round_log()
    assert len(log) == 1
    entry = log[0]
    assert entry["round"] == 1
    assert "previous_error" in entry
    assert "llm_context" in entry
    assert "code_snapshot" in entry
