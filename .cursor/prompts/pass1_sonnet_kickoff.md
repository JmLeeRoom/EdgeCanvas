# Pass 1 킥오프 프롬프트 (Cursor 모델: Sonnet-max)

Cursor 모델 선택기를 **Sonnet-max**로 맞춘 뒤, `T-xxx`를 실제 Task ID로 바꿔서 채팅에 붙여넣는다.

---

Task ID: T-xxx

지금부터 `.cursor/rules/task-workflow.mdc`의 0~4단계(WIP 확인 -> 컨텍스트 로딩 -> 브랜치 -> TDD Red -> Pass 1 구현)를 순서대로 수행해줘.

1. 다른 Task가 `status:in-progress`로 진행 중이 아닌지 먼저 확인해줘.
2. `단위구현계획서.md` 제5장에서 T-xxx 카드를 전부 읽고 목적/구현 내용/DoD/실패 시 대처를 요약해서 먼저 보여줘.
3. 카드 6항 선행 task가 `main`에 머지되어 있는지 확인하고, 안 되어 있으면 멈추고 알려줘.
4. GitHub Issue 존재 여부를 확인해줘. 없으면 생성 절차(제목/라벨)를 알려줘. 있으면 라벨을 `status:in-progress`로 갱신해줘.
5. `feature/T-xxx-slug` 브랜치를 `main`에서 새로 만들어줘.
6. 카드 10항 테스트를 먼저 작성해서 Red 상태(실패 원인이 "기능 없음"인지)를 보여준 다음, 카드 8항 범위만 구현해서 Green으로 만들어줘. 12항 실패 케이스도 최소 1개 테스트로 커버해줘.
7. 통과하면 커밋하고(아직 push는 하지 않음), 13항 경로에 테스트 결과를 저장해줘.
8. 끝나면 Pass 1 완료 요약과 "Opus-4.8-max로 전환해 Pass 2 시작" 안내를 보여줘.
