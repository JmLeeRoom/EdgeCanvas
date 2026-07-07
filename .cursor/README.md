# .cursor/ — P10_Manufacturing 에이전트 설정

이 폴더는 Cursor 에이전트가 이 저장소에서 일관되게 일하도록 하는 규칙·스킬·서브에이전트·프롬프트를 담는다.

## 구조

```
.cursor/
├── rules/                      # 자동 주입되는 지침 (.mdc)
│   ├── task-workflow.mdc        # (always) Task 단위 개발 표준 — TDD/2-pass/머지
│   ├── coding-standards.mdc     # (*.py,*.c,*.h) 시뮬 우선·LangGraph·Vision·LVGL 규칙
│   └── github-ops.mdc           # 이슈·브랜치·커밋·PR·라벨·마일스톤 운영
├── skills/                     # 명시 호출 스킬 (SKILL.md)
│   ├── task-kickoff/            # T-xxx 착수: 카드 로딩·선행/WIP 점검·브랜치 생성
│   └── plan-consistency-check/  # 계획서 3종 논리 정합성 검증
├── agents/                     # 서브에이전트 (readonly 검토자)
│   ├── task-reviewer.md         # Pass 2 시니어 코드 리뷰어
│   └── plan-auditor.md          # 계획 문서 정합성 감사자
└── prompts/                    # 사람이 붙여넣는 3-pass 킥오프 프롬프트
    ├── README.md
    ├── pass1_sonnet_kickoff.md
    ├── pass2_opus_review.md
    └── task_closeout.md
```

## 언제 무엇을 쓰나

| 상황 | 사용 |
|---|---|
| Task 1개 착수 준비 | `task-kickoff` 스킬 → 이후 `prompts/`의 3-pass |
| 구현 리뷰(별도 관점) | `task-reviewer` 서브에이전트 또는 `pass2_opus_review.md` |
| 계획 문서 수정 후 회귀 점검 | `plan-consistency-check` 스킬 또는 `plan-auditor` 서브에이전트 |
| 코드 작성 중 규칙 | `coding-standards.mdc`(파일 열면 자동), `github-ops.mdc` |

## 우선순위

규칙 충돌 시 `GITHUB_워크플로_가이드.md` > `task-workflow.mdc` > 기타 규칙. 계획 근거는 항상 `단위구현계획서.md` 제5장 Task 카드가 기준이다.
