"""T-904: 설치 사전조건(Git/Python/API 키) 가드.

install.bat / install.sh 가 호출한다. 단위 테스트는 which·version·env 를
주입해 Card 12 실패 분기(다운로드 링크 출력 후 중단)를 검증한다.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Sequence

MIN_PYTHON: tuple[int, int] = (3, 10)
PYTHON_DOWNLOAD_URL = "https://www.python.org/downloads/"
GIT_DOWNLOAD_URL = "https://git-scm.com/downloads"
REQUIRED_API_KEYS: tuple[str, ...] = ("UPSTAGE_API_KEY", "NC_VARCO_API_KEY")

Printer = Callable[[str], None]
WhichFn = Callable[[str], str | None]


@dataclass(frozen=True)
class InstallGuardResult:
    ok: bool
    exit_code: int
    missing: str | None = None
    message: str = ""


@dataclass(frozen=True)
class ApiKeyCheckResult:
    ok: bool
    missing_keys: list[str] = field(default_factory=list)


def check_api_keys(env: Mapping[str, str] | None = None) -> ApiKeyCheckResult:
    """필수 API 키 존재 여부. 값은 로그에 남기지 않는다."""
    source = env if env is not None else os.environ
    missing: list[str] = []
    for key in REQUIRED_API_KEYS:
        value = (source.get(key) or "").strip()
        if not value:
            missing.append(key)
    return ApiKeyCheckResult(ok=not missing, missing_keys=missing)


def run_install_guards(
    *,
    which: WhichFn | None = None,
    python_version: tuple[int, ...] | None = ...,  # type: ignore[assignment]
    env: Mapping[str, str] | None = None,
    printer: Printer | None = None,
) -> InstallGuardResult:
    """Git 유무·Python 최소 버전을 검사하고 미충족 시 다운로드 링크를 출력한다.

    ``python_version`` 기본값(``...``)은 현재 인터프리터 ``sys.version_info`` 를 쓴다.
    테스트에서 ``None`` 을 넘기면 Python 미설치 fixture 로 취급한다.
    """
    lookup = which or shutil.which
    emit = printer or print

    if lookup("git") is None:
        msg = (
            "[T-904] Git 이 PATH 에서 발견되지 않았습니다. "
            "설치 후 터미널을 다시 연 뒤 이 스크립트를 재실행하세요.\n"
            f"Download: {GIT_DOWNLOAD_URL}"
        )
        emit(msg)
        return InstallGuardResult(ok=False, exit_code=1, missing="git", message=msg)

    if python_version is ...:
        resolved_version: tuple[int, ...] | None = tuple(sys.version_info[:3])
    else:
        resolved_version = python_version

    python_on_path = lookup("python") or lookup("python3")
    if resolved_version is None or python_on_path is None:
        msg = (
            "[T-904] Python 이 PATH 에서 발견되지 않았습니다. "
            f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ (권장 3.13.x) 를 설치하세요.\n"
            f"Download: {PYTHON_DOWNLOAD_URL}"
        )
        emit(msg)
        return InstallGuardResult(ok=False, exit_code=1, missing="python", message=msg)

    if len(resolved_version) < 2 or tuple(resolved_version[:2]) < MIN_PYTHON:
        msg = (
            f"[T-904] Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ 가 필요합니다. "
            f"현재: {'.'.join(str(p) for p in resolved_version)}.\n"
            f"Download: {PYTHON_DOWNLOAD_URL}"
        )
        emit(msg)
        return InstallGuardResult(
            ok=False, exit_code=1, missing="python_version", message=msg
        )

    if env is not None:
        api = check_api_keys(env)
        if not api.ok:
            emit(
                "[T-904] 참고: 다음 API 키가 비어 있습니다 (설치는 계속 가능): "
                + ", ".join(api.missing_keys)
                + ". `.env.example` 을 `.env` 로 복사한 뒤 값을 채우세요."
            )

    ok_msg = (
        f"[T-904] 사전조건 OK — Git 및 Python "
        f"{'.'.join(str(p) for p in resolved_version)} (>={MIN_PYTHON[0]}.{MIN_PYTHON[1]})"
    )
    emit(ok_msg)
    return InstallGuardResult(ok=True, exit_code=0, missing=None, message=ok_msg)


def create_venv_and_install(
    root: Path,
    *,
    python_exe: str | None = None,
    runner: Callable[[Sequence[str]], int] | None = None,
    printer: Printer | None = None,
) -> int:
    """`.venv` 생성 후 `requirements.txt` 를 설치한다."""
    emit = printer or print
    run = runner or (lambda cmd: subprocess.call(list(cmd)))
    root = root.resolve()
    venv_dir = root / ".venv"
    req = root / "requirements.txt"
    py = python_exe or sys.executable

    if not venv_dir.is_dir():
        emit(f"[T-904] Creating virtualenv: {venv_dir}")
        code = run([py, "-m", "venv", str(venv_dir)])
        if code != 0:
            emit("[T-904] venv 생성 실패")
            return code
    else:
        emit(f"[T-904] Reusing virtualenv: {venv_dir}")

    if os.name == "nt":
        venv_python = venv_dir / "Scripts" / "python.exe"
        venv_pip = venv_dir / "Scripts" / "pip.exe"
    else:
        venv_python = venv_dir / "bin" / "python"
        venv_pip = venv_dir / "bin" / "pip"

    if not req.is_file():
        emit(f"[T-904] requirements.txt 없음: {req}")
        return 1

    emit("[T-904] pip install -r requirements.txt")
    code = run([str(venv_pip), "install", "-r", str(req)])
    if code != 0:
        emit("[T-904] pip install 실패")
        return code

    env_example = root / ".env.example"
    env_file = root / ".env"
    if env_example.is_file() and not env_file.is_file():
        env_file.write_text(env_example.read_text(encoding="utf-8"), encoding="utf-8")
        emit("[T-904] `.env` 를 `.env.example` 에서 생성했습니다. API 키를 채우세요.")
    elif env_file.is_file():
        emit("[T-904] 기존 `.env` 유지 (덮어쓰지 않음)")

    activate = r".venv\Scripts\activate" if os.name == "nt" else "source .venv/bin/activate"
    emit(f"[T-904] 활성화: {activate}")
    emit('[T-904] 확인: python -c "import cv2; print(cv2.__version__)"')
    emit("[T-904] CLI: python -m src.cli.main --help")
    if runner is None and not venv_python.is_file():
        emit(f"[T-904] 경고: venv python 경로를 확인할 수 없습니다: {venv_python}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI: 가드 실행 후 venv/pip 부트스트랩."""
    args = list(argv if argv is not None else sys.argv[1:])
    root = Path(__file__).resolve().parents[2]
    if args and args[0] == "--root":
        root = Path(args[1])
        args = args[2:]

    guards_only = "--guards-only" in args
    result = run_install_guards()
    if not result.ok:
        return result.exit_code
    if guards_only:
        return 0
    return create_venv_and_install(root)


if __name__ == "__main__":
    raise SystemExit(main())
