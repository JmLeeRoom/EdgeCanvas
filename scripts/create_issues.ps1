$ErrorActionPreference = "Stop"
$gh = "C:\Program Files\GitHub CLI\gh.exe"
$repo = "JmLeeRoom/EdgeCanvas"

$msMap = @{
  "M1" = "M1: Sim loop"
  "M2" = "M2: Sim E2E"
  "M3" = "M3: HW HIL"
}

# 이미 생성된 이슈 제목 수집 (중복 방지)
$existing = & $gh issue list --repo $repo --state all --limit 200 --json title --jq ".[].title"
$existingSet = @{}
foreach ($e in $existing) { $existingSet[$e] = $true }

$json = python scripts\gh_issues.py | Out-String
$tasks = $json | ConvertFrom-Json

$planUrl = "https://github.com/JmLeeRoom/EdgeCanvas/blob/main/%EB%8B%A8%EC%9C%84%EA%B5%AC%ED%98%84%EA%B3%84%ED%9A%8D%EC%84%9C.md"
$count = 0
$skipped = 0
foreach ($t in $tasks) {
  if ($existingSet.ContainsKey($t.title)) { $skipped++; continue }
  $tid = $t.title.Split(']')[0].TrimStart('[')
  $body = @"
자동 생성된 Task 이슈입니다. 상세 카드(목적/구현/테스트/DoD/검증 기록)는 계획서 제5장 ``$tid`` 항목을 참조하세요.

- 계획서: [단위구현계획서.md]($planUrl)
- 워크플로: GITHUB_워크플로_가이드.md

작업 착수 시 ``status:todo`` → ``status:in-progress`` 로 라벨을 변경하고, 브랜치 ``feature/$($tid.ToLower())-slug`` 를 생성하세요.
"@

  $labelArgs = @()
  foreach ($l in $t.labels) { $labelArgs += @("--label", $l) }

  $args = @("issue", "create", "--repo", $repo, "--title", $t.title, "--body", $body) + $labelArgs
  if ($t.milestone) { $args += @("--milestone", $msMap[$t.milestone]) }

  $url = & $gh @args
  $count++
  Write-Output "[$count] $($t.title) -> $url"
}
Write-Output "TOTAL_CREATED=$count SKIPPED=$skipped"

