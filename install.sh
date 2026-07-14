#!/usr/bin/env bash
# T-904: EdgeCanvas 개발 환경 부트스트랩 (macOS/Linux)
# Card 12: Git/Python 미충족 시 다운로드 링크 출력 후 즉시 중단
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo "[T-904] EdgeCanvas install.sh"

if ! command -v git >/dev/null 2>&1; then
  echo "[T-904] Git 이 PATH 에서 발견되지 않았습니다."
  echo "Download: https://git-scm.com/downloads"
  exit 1
fi

PY=""
if command -v python3 >/dev/null 2>&1; then
  PY="python3"
elif command -v python >/dev/null 2>&1; then
  PY="python"
fi

if [[ -z "${PY}" ]]; then
  echo "[T-904] Python 이 PATH 에서 발견되지 않았습니다."
  echo "Python 3.10+ 필요 (권장 3.13.x, 3.14+ 는 langchain-upstage 충돌 가능)."
  echo "Download: https://www.python.org/downloads/"
  exit 1
fi

# 상세 가드 + .venv / pip / .env 부트스트랩 (src.common.install_bootstrap)
export PYTHONPATH="${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
set +e
"${PY}" -m src.common.install_bootstrap
code=$?
set -e
if [[ "${code}" -ne 0 ]]; then
  echo "[T-904] install_bootstrap 실패 (exit ${code})."
  echo "Python 최소 버전 미달이면: https://www.python.org/downloads/"
  echo "Git 미설치면: https://git-scm.com/downloads"
  exit "${code}"
fi

echo "[T-904] 설치 완료. README.md 의 Quick start 를 이어 진행하세요."
exit 0
