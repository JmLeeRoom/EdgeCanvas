<#
.SYNOPSIS
  T-801 시뮬레이터 빌드 검증 스크립트.
  cmake/컴파일러/SDL2 가용성을 점검하고, 도구가 있으면 실제 빌드를 수행해
  build_sim/bin/lvgl_simulator(.exe) 산출 여부로 성공/실패를 판정한다.

.DESCRIPTION
  C 프로젝트라 pytest 대신 이 스크립트가 카드 10항의 "빌드 성공 여부 판정" 역할을 한다.
  - 도구가 모두 있으면: cmake configure + build 후 실행파일 존재로 PASS/FAIL.
  - 도구가 없으면: 무엇이 없는지 보고하고 exit 2(SKIPPED/미검증)로 종료.

.EXITCODE
  0 = 빌드 성공(실행파일 생성됨)
  1 = 빌드 시도했으나 실패
  2 = 빌드 도구 부재로 검증 불가(SKIPPED)
#>
[CmdletBinding()]
param(
    [string]$SourceDir = "$PSScriptRoot",
    [string]$BuildDir  = "$PSScriptRoot\..\..\build_sim"
)

$ErrorActionPreference = "Stop"

function Test-Tool([string]$name) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source } else { return $null }
}

Write-Host "== T-801 build tool check =="
$cmake = Test-Tool "cmake"
$gcc   = Test-Tool "gcc"
$clang = Test-Tool "clang"
$sdl   = Test-Tool "sdl2-config"

Write-Host ("cmake       : " + ($(if ($cmake) { $cmake } else { "NOT FOUND" })))
Write-Host ("gcc         : " + ($(if ($gcc)   { $gcc }   else { "NOT FOUND" })))
Write-Host ("clang       : " + ($(if ($clang) { $clang } else { "NOT FOUND" })))
Write-Host ("sdl2-config : " + ($(if ($sdl)   { $sdl }   else { "NOT FOUND (SDL2 dev may still be present via CMake config)" })))

$missing = @()
if (-not $cmake)            { $missing += "cmake" }
if (-not $gcc -and -not $clang) { $missing += "C compiler (gcc/clang)" }

if ($missing.Count -gt 0) {
    Write-Host ""
    Write-Warning ("빌드 도구 부재로 실제 빌드/창 팝업 검증을 수행할 수 없습니다: " + ($missing -join ", "))
    Write-Host "설치 가이드는 src/simulator/README.md 를 참고하세요 (MSYS2 + SDL2 + CMake)."
    exit 2
}

Write-Host ""
Write-Host "== cmake configure =="
& cmake -S $SourceDir -B $BuildDir
if ($LASTEXITCODE -ne 0) { Write-Error "cmake configure 실패"; exit 1 }

Write-Host ""
Write-Host "== cmake build =="
& cmake --build $BuildDir
if ($LASTEXITCODE -ne 0) { Write-Error "cmake build 실패"; exit 1 }

$exe1 = Join-Path $BuildDir "bin\lvgl_simulator.exe"
$exe2 = Join-Path $BuildDir "bin/lvgl_simulator"
if ((Test-Path $exe1) -or (Test-Path $exe2)) {
    Write-Host "PASS: lvgl_simulator 실행 파일이 생성되었습니다."
    exit 0
} else {
    Write-Error "FAIL: 빌드는 끝났으나 lvgl_simulator 실행 파일을 찾지 못했습니다."
    exit 1
}
