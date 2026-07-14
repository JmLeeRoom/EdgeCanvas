@echo off
REM T-904: EdgeCanvas 개발 환경 부트스트랩 (Windows)
REM Card 12: Git/Python 미충족 시 다운로드 링크 출력 후 즉시 중단
setlocal EnableExtensions
cd /d "%~dp0"

echo [T-904] EdgeCanvas install.bat

where git >nul 2>&1
if errorlevel 1 (
  echo [T-904] Git 이 PATH 에서 발견되지 않았습니다.
  echo Download: https://git-scm.com/downloads
  exit /b 1
)

where python >nul 2>&1
if errorlevel 1 (
  echo [T-904] Python 이 PATH 에서 발견되지 않았습니다.
  echo Python 3.10+ 필요 ^(권장 3.13.x, 3.14+ 는 langchain-upstage 충돌 가능^).
  echo Download: https://www.python.org/downloads/
  exit /b 1
)

REM 상세 가드 + .venv / pip / .env 부트스트랩 (src.common.install_bootstrap)
set PYTHONPATH=%CD%;%PYTHONPATH%
python -m src.common.install_bootstrap
set EXITCODE=%ERRORLEVEL%
if not "%EXITCODE%"=="0" (
  echo [T-904] install_bootstrap 실패 ^(exit %EXITCODE%^).
  echo Python 최소 버전 미달이면: https://www.python.org/downloads/
  echo Git 미설치면: https://git-scm.com/downloads
  exit /b %EXITCODE%
)

echo [T-904] 설치 완료. README.md 의 "Quick start" 를 이어 진행하세요.
exit /b 0
