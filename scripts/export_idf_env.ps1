<#
.SYNOPSIS
  T-003 ESP-IDF v5.3+ 환경변수보내기 스크립트.

.DESCRIPTION
  Espressif Windows Installer 기본 경로의 export.ps1(또는 export.bat)을 호출해
  현재 PowerShell 세션에 IDF_PATH, PATH(크로스 컴파일러 포함)를 바인딩한다.

  사용법 (PowerShell):
    . .\scripts\export_idf_env.ps1

  새 터미널마다 한 번씩 dot-source 하거나, $PROFILE에 아래 한 줄을 추가한다:
    . D:\EdgeCanvas\scripts\export_idf_env.ps1

.EXITCODE
  0 = export 성공
  1 = ESP-IDF 루트 또는 export 스크립트 없음
  2 = export 실행 후 idf.py 미검출(환경 미적용)
#>
[CmdletBinding()]
param(
    [string]$IdfRoot = "C:\Espressif\frameworks\esp-idf-v5.3"
)

$ErrorActionPreference = "Stop"

function Write-IdfExportStatus([string]$Message) {
    Write-Host "[T-003] $Message"
}

if (-not (Test-Path -LiteralPath $IdfRoot)) {
    Write-Error @"
ESP-IDF 설치 디렉터리를 찾을 수 없습니다: $IdfRoot
1. https://docs.espressif.com/projects/esp-idf/en/v5.3/esp32/get-started/windows-setup.html
   에서 ESP-IDF v5.3 Windows Installer를 받아 설치하세요.
2. 설치 경로를 C:\Espressif\frameworks\esp-idf-v5.3 로 맞추세요.
3. 설치 완료 후 이 스크립트를 다시 실행하세요.
"@
    exit 1
}

$exportPs1 = Join-Path $IdfRoot "export.ps1"
$exportBat = Join-Path $IdfRoot "export.bat"

if (Test-Path -LiteralPath $exportPs1) {
    Write-IdfExportStatus "export.ps1 소싱: $exportPs1"
    . $exportPs1
} elseif (Test-Path -LiteralPath $exportBat) {
    Write-IdfExportStatus "export.bat 실행: $exportBat"
    & cmd.exe /c "`"$exportBat`" && set" | ForEach-Object {
        if ($_ -match '^(?<key>[^=]+)=(?<value>.*)$') {
            Set-Item -Path "env:$($Matches.key)" -Value $Matches.value
        }
    }
} else {
    Write-Error "export.ps1/export.bat 을 찾을 수 없습니다: $IdfRoot"
    exit 1
}

$idfPy = Get-Command idf.py -ErrorAction SilentlyContinue
if (-not $idfPy) {
    Write-Warning "export 후에도 idf.py 가 PATH에 없습니다. 터미널을 재시작하거나 설치를 확인하세요."
    exit 2
}

Write-IdfExportStatus "idf.py: $($idfPy.Source)"
Write-IdfExportStatus "IDF_PATH: $env:IDF_PATH"
Write-IdfExportStatus "xtensa / riscv 컴파일러 확인:"
$xtensa = Get-Command xtensa-esp32-elf-gcc -ErrorAction SilentlyContinue
$riscv  = Get-Command riscv32-esp-elf-gcc -ErrorAction SilentlyContinue
Write-Host ("  xtensa-esp32-elf-gcc : " + ($(if ($xtensa) { $xtensa.Source } else { "NOT FOUND" })))
Write-Host ("  riscv32-esp-elf-gcc  : " + ($(if ($riscv) { $riscv.Source } else { "NOT FOUND" })))

exit 0
