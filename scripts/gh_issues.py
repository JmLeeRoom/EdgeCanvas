"""Generate GitHub issues for all 45 backlog tasks.

Reads task metadata from an embedded table and prints `gh issue create`
argument lines. Run with --emit to produce a JSON list consumed by the
PowerShell wrapper, or --check to validate counts.
"""
import json
import sys

# (id, name, module_label, phase_label, assignee_label, week_num_or_None, is_cut, milestone_key)
# milestone_key: "M1" | "M2" | "M3" | None
TASKS = [
    ("T-001", "저장소 구조 및 Python 가상환경 구축", "infra", "a", "a", 1, False, None),
    ("T-002", "Upstage API 연동 및 공통 모듈 구현", "infra", "a", "a", 1, False, None),
    ("T-003", "ESP-IDF v5.3+ 개발 환경 구축", "infra", "hw", "b", 10, False, "M3"),
    ("T-004", "ESP32-P4 BSP 공식 예제 빌드 및 플래시 검증", "infra", "hw", "b", 10, False, "M3"),
    ("T-005", "로깅 모듈 및 Run ID 기반 산출물 체계 구현", "infra", "a", "a", 1, False, None),
    ("T-006", "M5Stack CoreS3 개발 환경 및 예제 검증", "infra", "hw", "b", None, True, None),
    ("T-007", "[Spike] ESP32-P4 LCD/터치 PSRAM 메모리 최적화 검증", "spike", "hw", "b", 10, False, "M3"),
    ("T-008", "[Spike] Upstage Document Parse 표 추출 성능 검증", "spike", "a", "a", 1, False, None),
    ("T-009", "[Spike] Solar Pro 3 비전 멀티모달 입력 및 판정 실험", "spike", "a", "a", 1, False, None),
    ("T-010", "[Spike] NC AI VARCO Art 이미지 생성 API 접속 검증", "spike", "a", "a", 2, False, None),
    ("T-011", "[Spike] USB 카메라 LCD 촬영 화질 및 반사 제어 전처리 실험", "spike", "hw", "b", 11, False, "M3"),
    ("T-012", "[Spike] 개발·시연 OS 및 Docker/USB/카메라 접근 범위 결정", "spike", "a", "pair", 2, False, None),
    ("T-013", "[Spike] HIL 물리 환경 최소 구성 및 시리얼 포트 매핑 검증", "spike", "hw", "b", 11, False, "M3"),
    ("T-101", "Typer CLI 명령어 엔트리포인트 구현", "cli", "a", "a", 2, False, None),
    ("T-102", "사용자 UI 요구사항 및 PDF 파일 검증 모듈 구현", "cli", "a", "a", 2, False, None),
    ("T-201", "Upstage Document Parse 데이터 파싱 및 텍스트 청킹", "doc", "a", "a", 3, False, None),
    ("T-202", "데이터시트 핵심 스펙(디스플레이, 레지스터, 터치) 분석기", "doc", "a", "a", 3, False, None),
    ("T-203", "기술 지식 베이스(Technology KB) JSON 스키마 변환기", "doc", "a", "a", 4, False, None),
    ("T-301", "보드 프로필 매퍼 및 BSP 고정 템플릿 연동 모듈", "codegen", "a", "b", 4, False, None),
    ("T-302", "Solar Pro 3 LVGL UI 레이아웃 프롬프트 설계", "codegen", "a", "a", 4, False, None),
    ("T-303", "LLM 생성 코드 위젯 트리 및 이벤트 핸들러 파서 구현", "codegen", "a", "a", 5, False, None),
    ("T-304", "에이전트 컨텍스트 토큰 예산 관리 모듈 구현", "codegen", "a", "a", 5, False, None),
    ("T-401", "VARCO Art API 연동 HMI 이미지 생성기 구현", "asset", "a", "a", 5, False, None),
    ("T-402", "GUI 이미지 에셋 LVGL C 배열 변환기(lv_img_conv 연동)", "asset", "a", "b", 6, False, None),
    ("T-501", "BoardTarget 추상클래스 설계 및 ESP32-P4 컴파일 서브프로세스 구현", "build", "hw", "b", 11, False, "M3"),
    ("T-502", "esptool 연동 타깃 보드 펌웨어 플래시 제어 모듈", "build", "hw", "b", 11, False, "M3"),
    ("T-503", "GCC/Clang 컴파일러 에러 로그 구문 분석기 구현", "build", "a", "b", 8, False, "M2"),
    ("T-504", "ESP32-S3(M5Stack CoreS3) 빌드 및 플래시 드라이버 포팅", "build", "hw", "b", None, True, None),
    ("T-601", "USB 카메라 기동 및 물리적 촬영 프레임 캡처 모듈", "vision", "hw", "b", 12, False, "M3"),
    ("T-602", "촬영 이미지 원근 보정 및 UI 영역 전처리 모듈", "vision", "hw", "b", 12, False, "M3"),
    ("T-603", "OpenCV 기반 위젯 크기/위치 정량 PASS/FAIL 판정기", "vision", "a", "b", 6, False, "M1"),
    ("T-604", "OCR 및 Solar Pro 3 비전 기반 텍스트/의미 일치 분석기", "vision", "a", "b", 7, False, "M1"),
    ("T-701", "LangGraph 2단계 상태머신 (Sim + HW) 그래프 구축", "agent", "a", "a", 7, False, "M1"),
    ("T-702", "자가 수정 루프 재진입 및 라운드 제어기 (sim 5회 / hw 2회)", "agent", "a", "a", 8, False, "M2"),
    ("T-703", "체크포인트 세션 저장소 및 최종 검증 보고서 생성기", "agent", "a", "a", 8, False, "M2"),
    ("T-801", "LVGL PC VSCode 시뮬레이터(SDL2) 환경 연동 모듈", "sim", "a", "b", 1, False, None),
    ("T-802", "PC 시뮬레이터 드라이버·스크린샷 캡처 및 자동 구동", "sim", "a", "b", 2, False, None),
    ("T-850", "Emscripten WebAssembly 기반 브라우저 렌더링 파이프라인", "web", "b", "b", 10, False, None),
    ("T-851", "에이전트 통합 제어용 FastAPI 백엔드 서버 구축", "web", "b", "a", 10, False, None),
    ("T-852", "Streamlit/React 기반 UI 대시보드 및 웹 HMI 캔버스 프론트엔드", "web", "b", "a", 11, False, None),
    ("T-901", "Typer CLI 기반 시뮬 E2E 파이프라인 통합 테스트 (--mode sim)", "integration", "a", "a", 9, False, "M2"),
    ("T-902", "평가 지표 4종 자동 정량 측정 (sim 9주 / hw 12주)", "integration", "a", "a", 9, False, "M2"),
    ("T-903", "파이프라인 극한 테스트(예외 입력, 타임아웃, 케이블 단선)", "integration", "hw", "pair", 12, False, "M3"),
    ("T-904", "README 문서, 설치 스크립트 작성 및 비원 개발자 검증", "integration", "a", "b", 8, False, "M2"),
    ("T-905", "시연 부스 설치용 하드웨어 물리 결선 및 최종 시연 리허설", "integration", "hw", "b", 12, False, "M3"),
]


def build():
    out = []
    for tid, name, module, phase, assignee, week, is_cut, ms in TASKS:
        labels = [f"phase:{phase}", f"module:{module}", f"assignee:{assignee}"]
        if is_cut:
            labels.append("status:cut")
        else:
            labels.append("status:todo")
        if week is not None:
            labels.append(f"week:{week:02d}")
        item = {
            "title": f"[{tid}] {name}",
            "labels": labels,
            "milestone": ms,
            "cut": is_cut,
        }
        out.append(item)
    return out


if __name__ == "__main__":
    data = build()
    if "--check" in sys.argv:
        print(f"tasks={len(data)}")
        cut = sum(1 for d in data if d["cut"])
        print(f"cut={cut}")
        for k in ("M1", "M2", "M3"):
            print(f"{k}={sum(1 for d in data if d['milestone']==k)}")
        print(f"no_ms={sum(1 for d in data if d['milestone'] is None)}")
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))
