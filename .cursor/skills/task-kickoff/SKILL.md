---
name: task-kickoff
description: P10_Manufacturing에서 특정 Task(T-xxx) 착수를 준비한다. 단위구현계획서 제5장 카드를 로딩하고, 선행 완료·WIP·컷 여부를 점검하고, GitHub 이슈 라벨을 status:in-progress로 바꾸고 feature 브랜치를 만든다. "T-xxx 시작", "다음 태스크 착수", "T-301 작업하자" 같은 요청에 사용한다.
disable-model-invocation: true
---

# Task 착수 (task-kickoff)

`.cursor/rules/task-workflow.mdc`의 0~2단계를 이 스킬로 자동화한다. Task ID(`T-xxx`)를 입력받아 실행한다.

## 체크리스트

```
- [ ] 1. WIP=1 확인 (다른 status:in-progress 이슈 없음)
- [ ] 2. 카드 로딩 (제5장 T-xxx 1~13항 요약)
- [ ] 3. 선행 Task main 머지 확인
- [ ] 4. 컷 대상(T-006/T-504) 여부 확인
- [ ] 5. 이슈 라벨 status:in-progress + assign
- [ ] 6. feature/T-xxx-slug 브랜치 생성
```

## 1. WIP 확인

```powershell
& "C:\Program Files\GitHub CLI\gh.exe" issue list --repo JmLeeRoom/EdgeCanvas --label "status:in-progress" --state open
```

진행 중 이슈가 있으면 멈추고 사용자에게 알린다.

## 2. 카드 로딩

`단위구현계획서.md` 제5장에서 `### [T-xxx]` 카드를 읽고 **목적(7)·구현(8)·산출물(9)·테스트(10)·DoD(11)·실패대처(12)·검증기록(13)**을 요약해 보여준다.

## 3. 선행 확인

카드 **6. 선행 task**의 각 ID가 `main`에 머지됐는지 `git log main --oneline | Select-String "T-YYY"`로 확인한다. 미완료면 착수를 멈춘다.

## 4. 컷 확인

`T-006`, `T-504`는 기본 컷. 별도 지시 없으면 착수하지 않는다.

## 5. 이슈 라벨

해당 T-xxx 이슈 번호를 찾아 라벨을 바꾼다.

```powershell
$gh = "C:\Program Files\GitHub CLI\gh.exe"
& $gh issue edit <num> --repo JmLeeRoom/EdgeCanvas --add-label "status:in-progress" --remove-label "status:todo"
```

## 6. 브랜치

```powershell
git checkout main; git pull origin main; git checkout -b feature/T-xxx-slug
```

## 종료

완료 후 "Sonnet-max로 `pass1_sonnet_kickoff.md`를 실행해 TDD 구현을 시작하세요"라고 안내한다. 상세 구현/리뷰/머지는 `.cursor/prompts/`의 3-pass 프롬프트와 `task-workflow.mdc`를 따른다.
