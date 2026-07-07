# 마무리 킥오프 프롬프트 (이슈 정리 -> push -> PR -> 머지)

Pass 2가 green으로 끝난 뒤 실행한다. 모델은 Sonnet/Opus 상관없이 사용 가능. `T-xxx`를 실제 Task ID로 바꿔서 채팅에 붙여넣는다.

---

Task ID: T-xxx

`.cursor/rules/task-workflow.mdc`의 7단계(마무리)를 수행해줘.

1. Issue의 DoD 체크박스를 갱신하고 검증 기록 경로/결과를 코멘트로 남겨줘. 라벨을 `status:testing`으로 바꿔줘.
2. `feature/T-xxx-slug`를 push 해줘.
3. `GITHUB_워크플로_가이드.md` 5.3절 템플릿으로 PR을 만들어줘 (`Closes #<issue-number>` 포함).
4. 테스트·DoD가 모두 충족됐으면 squash merge 해줘. 애매하거나 다른 담당자 코드와 겹치면 머지 전에 먼저 물어봐.
5. 머지 후 `main`으로 돌아와 pull하고 로컬 feature 브랜치를 정리해줘. Issue가 자동 Close 됐는지, 라벨이 `status:done`인지 확인해줘.
6. 마일스톤(M1/M2/M3) 대상 Task라면 태깅(`GITHUB_워크플로_가이드.md` 14절) 여부를 물어봐줘.
7. `단위구현계획서.md` 제3장 의존성 그래프 기준으로 다음에 진행 가능한 Task 후보를 1~2개 제안해줘.
