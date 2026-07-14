"""T-904: README·설치 스크립트 — 단위 테스트.

Task/Task29.md / 단위구현계획서.md [T-904] 10항·12항.
- Red: Git/Python 누락 fixture → 즉시 중단 + 다운로드 링크.
- Green: mock command runner로 가드 통과, README 명령 블록 순서 검증.
- 제3자 60분 수동 검증은 docs/verification/T-904_user_verification.txt 슬롯.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.common.install_bootstrap import (
    GIT_DOWNLOAD_URL,
    MIN_PYTHON,
    PYTHON_DOWNLOAD_URL,
    check_api_keys,
    run_install_guards,
)

ROOT = Path(__file__).resolve().parents[1]


def test_missing_git_aborts_with_download_link():
    """Red/Card12: Git 미설치 fixture면 중단하고 git-scm 링크를 출력한다."""
    printed: list[str] = []

    def fake_which(name: str) -> str | None:
        if name == "git":
            return None
        if name in ("python", "python3"):
            return "/usr/bin/python3"
        return None

    result = run_install_guards(
        which=fake_which,
        python_version=(3, 13, 0),
        env={},
        printer=printed.append,
    )

    assert result.ok is False
    assert result.exit_code != 0
    assert result.missing == "git"
    joined = "\n".join(printed)
    assert GIT_DOWNLOAD_URL in joined


def test_missing_python_aborts_with_download_link():
    """Red/Card12: Python 미설치 fixture면 중단하고 python.org 링크를 출력한다."""
    printed: list[str] = []

    def fake_which(name: str) -> str | None:
        if name == "git":
            return "/usr/bin/git"
        return None

    result = run_install_guards(
        which=fake_which,
        python_version=None,
        env={},
        printer=printed.append,
    )

    assert result.ok is False
    assert result.exit_code != 0
    assert result.missing == "python"
    joined = "\n".join(printed)
    assert PYTHON_DOWNLOAD_URL in joined


def test_python_below_minimum_aborts_with_download_link():
    """Red/Card12: Python 최소 버전 미달이면 중단하고 다운로드 링크를 출력한다."""
    printed: list[str] = []

    def fake_which(name: str) -> str | None:
        mapping = {"git": "/usr/bin/git", "python": "/usr/bin/python", "python3": "/usr/bin/python3"}
        return mapping.get(name)

    result = run_install_guards(
        which=fake_which,
        python_version=(3, 9, 18),
        env={},
        printer=printed.append,
    )

    assert result.ok is False
    assert result.exit_code != 0
    assert result.missing == "python_version"
    joined = "\n".join(printed)
    assert PYTHON_DOWNLOAD_URL in joined
    assert str(MIN_PYTHON[0]) in joined
    assert str(MIN_PYTHON[1]) in joined


def test_guards_pass_with_mock_runner_and_api_keys():
    """Green: mock runner로 Git/Python/API key 검사를 통과한다."""
    printed: list[str] = []

    def fake_which(name: str) -> str | None:
        mapping = {"git": "/usr/bin/git", "python": "/usr/bin/python", "python3": "/usr/bin/python3"}
        return mapping.get(name)

    env = {
        "UPSTAGE_API_KEY": "up_test_key_not_secret",
        "NC_VARCO_API_KEY": "varco_test_key_not_secret",
    }
    result = run_install_guards(
        which=fake_which,
        python_version=(3, 13, 1),
        env=env,
        printer=printed.append,
    )

    assert result.ok is True
    assert result.exit_code == 0
    assert result.missing is None

    api = check_api_keys(env)
    assert api.ok is True
    assert api.missing_keys == []


def test_api_key_check_reports_missing_keys():
    """Green: API 키 누락 시 누락 목록을 반환한다(하드코딩 없음)."""
    api = check_api_keys({"UPSTAGE_API_KEY": "", "NC_VARCO_API_KEY": "  "})
    assert api.ok is False
    assert "UPSTAGE_API_KEY" in api.missing_keys
    assert "NC_VARCO_API_KEY" in api.missing_keys


def test_install_scripts_exist_and_contain_card12_guards():
    """산출물: install.bat / install.sh에 Python·Git 가드와 다운로드 링크가 있다."""
    for name in ("install.bat", "install.sh"):
        path = ROOT / name
        assert path.is_file(), f"{name} 이(가) 없습니다."
        text = path.read_text(encoding="utf-8")
        assert GIT_DOWNLOAD_URL in text, f"{name}: Git 다운로드 링크 누락"
        assert PYTHON_DOWNLOAD_URL in text, f"{name}: Python 다운로드 링크 누락"
        assert "install_bootstrap" in text or "run_install_guards" in text or "MIN_PYTHON" in text


def test_readme_exists_with_required_sections_and_command_order():
    """Green: README에 결선/API/IDF/Python 가이드와 설치 순서 명령 블록이 있다."""
    readme = ROOT / "README.md"
    assert readme.is_file(), "README.md 가 없습니다."
    text = readme.read_text(encoding="utf-8")

    required_phrases = [
        "하드웨어",
        "결선",
        "UPSTAGE_API_KEY",
        "NC_VARCO_API_KEY",
        "ESP-IDF",
        "5.3",
        "Python",
        "install.bat",
        "install.sh",
        ".env",
    ]
    missing = [p for p in required_phrases if p not in text]
    assert not missing, f"README 누락 문구: {missing}"

    # Quick start 내부 설치 순서: clone/install → venv → .env → CLI
    qs_start = text.index("## Quick start")
    qs_end = text.index("## Python 환경")
    qs = text[qs_start:qs_end]
    order_markers = [
        r"install\.(bat|sh)",
        r"\.venv",
        r"\.env\.example|\.env",
        r"src\.cli\.main|p10\s+run|--mode\s+sim",
    ]
    positions: list[int] = []
    for pattern in order_markers:
        match = re.search(pattern, qs, flags=re.IGNORECASE)
        assert match is not None, f"Quick start 순서 마커 없음: {pattern}"
        positions.append(match.start())
    assert positions == sorted(positions), f"README Quick start 명령 순서가 어긋남: {positions}"


def test_verification_slot_documents_manual_third_party_trial():
    """검증 기록: 자동화 대체 명시 + 제3자 60분 수동 피드백 템플릿이 있다."""
    path = ROOT / "docs" / "verification" / "T-904_user_verification.txt"
    assert path.is_file(), "docs/verification/T-904_user_verification.txt 가 없습니다."
    text = path.read_text(encoding="utf-8")
    assert "60" in text
    assert "수동" in text or "manual" in text.lower()
    assert "피드백" in text or "feedback" in text.lower()
    assert "pytest" in text.lower() or "자동화" in text
