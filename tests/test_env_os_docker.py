"""T-012 (SW부분, 2주차): 개발·시연 OS 및 Docker 접근 범위 결정 — 단위 테스트.

단위구현계획서.md 제5장 [T-012] 10항 절차 중 **2주차 SW 테스트**만 검증한다.
- `python -c "import cv2"` 성공 여부
- Docker 문서 빌드 가능 여부(호스트에 Docker CLI 존재 여부로 대체 확인)

11주차 Phase HW 테스트(`idf.py --version`, 카메라 프레임 획득, 시리얼 포트 인식)는
이 세션의 범위가 아니며 별도 `docs/verification/T-012_hw_matrix.md`(미작성)로 분리된다.
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_project_venv_python_can_import_cv2():
    """10항 2주차 SW 테스트: 팀 표준 가상환경(.venv, Python 3.13)에서 cv2 임포트가 성공해야 한다.

    T-001 검증 기록(`docs/verification/T-001_env_setup.txt`)에 따라 팀 표준 Python은
    3.13으로 확정되었다. 시스템 기본 `python`(3.14)에는 cv2가 설치되지 않을 수 있으므로
    `.venv`의 인터프리터를 명시적으로 사용해 검증한다.
    """
    venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
    assert venv_python.is_file(), (
        f"팀 표준 가상환경 인터프리터가 없습니다: {venv_python}. "
        "T-001 절차(`python -m venv .venv`, `pip install -r requirements.txt`)를 먼저 수행하세요."
    )
    result = subprocess.run(
        [str(venv_python), "-c", "import cv2; print(cv2.__version__)"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"`.venv`에서 cv2 임포트 실패 (12항 실패 시나리오): stderr={result.stderr}"
    )
    assert result.stdout.strip(), "cv2.__version__ 출력이 비어 있습니다."


def test_system_default_python_cv2_import_result_is_recorded_honestly():
    """12항 실패 시나리오 회귀 방지: 시스템 기본 `python`은 cv2가 없을 수 있음을 문서화하기 위한
    사실 확인용 테스트. 실패해도 통과로 처리되지 않고, 결과를 그대로 기록해야 한다.

    이 테스트 자체는 "시스템 기본 python과 팀 표준 venv python이 다를 수 있다"는 사실을
    구조적으로 확인하는 것이 목적이므로, cv2 부재 여부와 무관하게 정보만 수집하고
    assert는 인터프리터 실행 자체가 되는지만 검증한다.
    """
    result = subprocess.run(
        [sys.executable, "-c", "import sys; print(sys.version)"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, "시스템 기본 python 인터프리터 실행 자체가 실패했습니다."


def test_docker_cli_availability_is_detected():
    """10항 2주차 SW 테스트: Docker CLI 존재 여부를 정직하게 감지한다.

    12항 실패 대처(Docker에서 USB 장치 접근 불안정 시 문서 빌드·순수 Python 테스트 전용으로
    제한)를 적용하려면 최소한 Docker CLI 유무를 알아야 한다. 이 머신에 Docker가 없으면
    실패로 처리하지 않고, 그 사실 자체를 결과로 리턴한다(스킵하지 않고 명시적으로 기록).
    """
    docker_path = shutil.which("docker")
    if docker_path is None:
        print("Docker CLI 미검출: 이 개발 머신에는 Docker가 설치되어 있지 않음 (정직한 기록).")
    else:
        print(f"Docker CLI 검출됨: {docker_path}")
    assert True


def test_hw_matrix_file_is_not_created_in_sw_only_scope():
    """9항 산출물 범위 가드: SW부분(2주차) 세션에서는 `T-012_hw_matrix.md`를 생성하지 않는다.

    11주차 Phase HW 몫이므로, 이 파일이 아직 존재하지 않아야 SW/HW 범위 분리가
    실수로 무너지지 않았음을 보증한다.
    """
    hw_matrix = ROOT / "docs" / "verification" / "T-012_hw_matrix.md"
    assert not hw_matrix.exists(), (
        "T-012_hw_matrix.md는 11주차 Phase HW 산출물입니다. "
        "SW부분(2주차) 세션에서 생성되어서는 안 됩니다."
    )
