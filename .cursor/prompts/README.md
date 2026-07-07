# Cursor Task 개발 프롬프트 사용법

Task 1개(`T-xxx`)를 끝까지 진행하는 순서: 아래 3개 프롬프트를 **순서대로** Cursor 채팅에 붙여넣는다. 공통 규칙은 `.cursor/rules/task-workflow.mdc`에 항상 적용되어 있으므로 프롬프트 자체는 짧게 유지했다.

1. [`pass1_sonnet_kickoff.md`](pass1_sonnet_kickoff.md) — 모델을 **Sonnet-max**로 두고 실행. 브랜치 생성 -> TDD Red -> 최소 구현 Green.
2. [`pass2_opus_review.md`](pass2_opus_review.md) — 모델을 **Opus-4.8-max**로 바꾸고 실행. 리뷰/보강, 범위 밖 이슈는 새 Issue로만 제안.
3. [`task_closeout.md`](task_closeout.md) — 이슈 정리 -> push -> PR -> squash merge -> 다음 Task 후보 제안.

각 프롬프트의 `T-xxx`를 실제 Task ID로 바꿔서 사용한다.

## 전제조건

- GitHub CLI(`gh`)가 설치·인증(`gh auth login`)되어 있어야 Issue/PR 생성과 머지를 에이전트가 직접 수행할 수 있다. 이 저장소 환경에는 아직 `gh`가 설치되어 있지 않으므로, 설치 전까지는 Issue/PR 관련 단계는 GitHub 웹 UI로 사용자가 직접 수행하고 에이전트에게는 "무엇을 만들지" 텍스트만 받는 방식으로 대체한다.
- `단위구현계획서.md` 제5장 Task 카드와 `GITHUB_워크플로_가이드.md`가 최신 상태여야 한다.

## 왜 3단계인가

- **Pass 1(Sonnet)**: 빠르게 최소 구현을 TDD로 완성 — 구현자 역할.
- **Pass 2(Opus)**: 별도 시점·별도 모델로 diff를 다시 읽어 리뷰 — 구현자와 분리된 리뷰어 역할. 팀에 리뷰어가 따로 없는 상태에서 이 2-패스 구조 자체가 "셀프 코드리뷰" 역할을 한다.
- **마무리**: 리뷰까지 끝난 코드만 이슈 정리/머지 대상이 되도록 게이트를 건다.
