"""T-001: 저장소 구조 및 Python 가상환경 구축 — 단위 테스트.

단위구현계획서.md 제5장 [T-001] 10항 절차를 코드로 검증한다.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_DIRS = ["src", "tests", "docs", "config"]
REQUIRED_PACKAGES = [
    "typer",
    "pydantic",
    "langchain-upstage",
    "opencv-python",
    "requests",
    "pytest",
    "black",
    "flake8",
]


def test_required_directories_exist():
    """8-1: 루트에 src/, tests/, docs/, config/ 디렉토리가 존재해야 한다."""
    missing = [d for d in REQUIRED_DIRS if not (ROOT / d).is_dir()]
    assert not missing, f"누락된 디렉토리: {missing}"


def test_requirements_file_lists_required_packages():
    """8-3, 9: requirements.txt에 필수 패키지가 명시되어야 한다."""
    req_path = ROOT / "requirements.txt"
    assert req_path.is_file(), "requirements.txt 파일이 없습니다."
    content = req_path.read_text(encoding="utf-8").lower()
    missing = [p for p in REQUIRED_PACKAGES if p.lower() not in content]
    assert not missing, f"requirements.txt에 누락된 패키지: {missing}"


def test_gitignore_covers_venv_and_build_artifacts():
    """8-4, 9: .gitignore가 .venv/, __pycache__/, build/, *.bin 을 포함해야 한다."""
    gi_path = ROOT / ".gitignore"
    assert gi_path.is_file(), ".gitignore 파일이 없습니다."
    content = gi_path.read_text(encoding="utf-8")
    required_patterns = [".venv", "__pycache__", "build", "*.bin"]
    missing = [p for p in required_patterns if p not in content]
    assert not missing, f".gitignore에 누락된 패턴: {missing}"


def test_python_version_is_3_10_or_higher():
    """10: 통과 기준 — Python 3.10+ 버전이 실행되어야 한다."""
    import sys

    assert sys.version_info >= (3, 10), f"Python 3.10+ 필요, 현재: {sys.version}"


def test_requirements_check_detects_missing_package(tmp_path):
    """12: 실패 시 대처 — 패키지가 누락된 requirements.txt는 검증에서 걸러져야 한다."""
    incomplete = tmp_path / "requirements_incomplete.txt"
    incomplete.write_text("typer\npydantic\n", encoding="utf-8")
    content = incomplete.read_text(encoding="utf-8").lower()
    missing = [p for p in REQUIRED_PACKAGES if p.lower() not in content]
    assert missing == [
        "langchain-upstage",
        "opencv-python",
        "requests",
        "pytest",
        "black",
        "flake8",
    ]
