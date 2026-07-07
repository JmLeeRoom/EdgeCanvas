# -*- coding: utf-8 -*-
"""Generate reorganized 단위구현계획서.md from template patches."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
ORIG = ROOT / "단위구현계획서.md"
OUT = ROOT / "단위구현계획서.md"
BACKUP = ROOT / "단위구현계획서_재정렬전.md"

# Task metadata: phase, week, predecessors, owner (owner unchanged from orig)
TASK_META = {
    "T-001": ("Phase A", "1주차", "없음"),
    "T-002": ("Phase A", "1주차", "T-001"),
    "T-003": ("Phase HW", "10주차", "T-703"),
    "T-004": ("Phase HW", "10주차", "T-003"),
    "T-005": ("Phase A", "1주차", "T-002"),
    "T-006": ("Phase HW", "컷(2단계)", "T-003"),
    "T-007": ("Phase HW", "10주차", "T-004"),
    "T-008": ("Phase A", "1주차", "T-002"),
    "T-009": ("Phase A", "1주차", "T-002"),
    "T-010": ("Phase A", "2주차", "T-002"),
    "T-011": ("Phase HW", "11주차", "T-004"),
    "T-012": ("Phase A/HW", "2주차(SW)·11주차(HW)", "T-001"),
    "T-013": ("Phase HW", "11주차", "T-011, T-012"),
    "T-101": ("Phase A", "2주차", "T-005"),
    "T-102": ("Phase A", "2주차", "T-101"),
    "T-201": ("Phase A", "3주차", "T-008, T-102"),
    "T-202": ("Phase A", "3주차", "T-201"),
    "T-203": ("Phase A", "4주차", "T-202"),
    "T-301": ("Phase A", "4주차", "T-203"),
    "T-302": ("Phase A", "4주차", "T-203, T-009"),
    "T-303": ("Phase A", "5주차", "T-302"),
    "T-304": ("Phase A", "5주차", "T-303"),
    "T-401": ("Phase A", "5주차", "T-010, T-303"),
    "T-402": ("Phase A", "6주차", "T-401"),
    "T-501": ("Phase HW", "11주차", "T-301, T-402, T-703"),
    "T-502": ("Phase HW", "11주차", "T-501"),
    "T-503": ("Phase A", "8주차", "없음(모의 로그)"),
    "T-504": ("Phase HW", "컷(2단계)", "T-006, T-502"),
    "T-601": ("Phase HW", "12주차", "T-011, T-502"),
    "T-602": ("Phase HW", "12주차", "T-601"),
    "T-603": ("Phase A", "6주차", "T-802, T-303"),
    "T-604": ("Phase A", "7주차", "T-603, T-009"),
    "T-701": ("Phase A", "7주차", "T-304, T-802, T-603, T-604"),
    "T-702": ("Phase A", "8주차", "T-701"),
    "T-703": ("Phase A", "8주차", "T-702"),
    "T-801": ("Phase A", "1주차", "T-001"),
    "T-802": ("Phase A", "2주차", "T-801"),
    "T-850": ("Phase B", "10주차(선택)", "T-802, M2통과"),
    "T-851": ("Phase B", "10주차(선택)", "T-703"),
    "T-852": ("Phase B", "11주차(선택)", "T-850, T-851"),
    "T-901": ("Phase A", "9주차", "T-703"),
    "T-902": ("Phase A", "9주차·12주차", "T-901"),
    "T-903": ("Phase HW", "12주차", "T-901, T-502"),
    "T-904": ("Phase A", "8주차", "T-802"),
    "T-905": ("Phase HW", "12주차", "T-903, T-904"),
}

RELOCATION_LOG = """| Task ID | 기존 주차 | 신규 주차 | 재배치 사유 |
|---|---|---|---|
| T-003 | 1주차 | 10주차 | ESP-IDF 툴체인은 Phase HW 실기 착수 시점으로 이동 |
| T-004 | 1주차 | 10주차 | BSP 빌드/플래시 조기 Go/No-Go 스파이크 제거 |
| T-006 | 2주차 | 컷(2단계) | CoreS3 보조 타깃, 실기 공수 압축을 위해 기본 컷 |
| T-007 | 1주차 | 10주차 | PSRAM 실측은 보드 확보 후 Phase HW에서 수행 |
| T-011 | 2주차 | 11주차 | 카메라 반사 실험은 HIL 구성과 함께 후반 이동 |
| T-012 | 1주차 | 2주차(SW)·11주차(HW) | OS/Docker는 초반, USB/카메라/플래시는 HW 분리 |
| T-013 | 2주차 | 11주차 | HIL 물리 환경은 실기 트랙 전용 |
| T-301 | 4주차 | 4주차 | 선행 T-007 제거, 데이터시트 기반 프로필만 사용 |
| T-402 | 6주차 | 6주차 | 담당 B 지원, T-401 완료 후 진행 |
| T-501 | 6주차 | 11주차 | 빌드 서브프로세스는 시뮬 E2E(M2) 완료 후 |
| T-502 | 6주차 | 11주차 | 플래시는 Phase HW |
| T-503 | 7주차 | 8주차 | 모의 컴파일 로그로 시뮬 루프 선행 개발 |
| T-504 | 7주차 | 컷(2단계) | CoreS3 포팅 기본 컷 |
| T-601~602 | 7~8주차 | 12주차 | 실카메라 캡처/원근보정은 최종 HIL |
| T-603 | 8주차 | 6주차 | 시뮬 스크린샷 입력으로 Vision 로직 선개발 |
| T-604 | 8주차 | 7주차 | 시뮬 이미지 OCR/VLM 선개발 |
| T-701 | 9주차 | 7주차 | 시뮬 2단계 그래프, T-802/603/604 선행 |
| T-702~703 | 9주차 | 8주차 | 시뮬 자가수정 루프 완성을 앞당김 |
| T-801 | 10주차 | 1주차 | PC SDL2 시뮬레이터를 Phase A 코어로 격상 |
| T-802 | 10주차 | 2주차 | 시뮬 드라이버·스크린샷 캡처 조기 구축 |
| T-850~852 | 10~11주차 | 10~11주차(선택) | M2 통과 시에만 Phase B 착수 |
| T-901 | 12주차 | 9주차 | `p10 run --mode sim` 소프트웨어 E2E |
| T-902 | 12주차 | 9주차·12주차 | sim 지표(9주)·hw 지표(12주) 분리 |
| T-903~905 | 12주차 | 12주차 | 실기 극한 테스트·시연은 최종 주차 유지 |
"""

CHAPTER1 = """# 단위구현계획서 - 프로젝트 P10_Manufacturing

> **재정렬 버전**: `단위구현계획서_재정렬_프롬프트.md` 원칙 적용 — 실물 장비 작업은 PC 시뮬레이터 기반 자가수정 루프가 안정화된 후 **Phase HW(10~12주차)** 에서만 착수합니다. 상세 분석은 [재정렬_분석보고.md](재정렬_분석보고.md)를 참조하십시오.

## 제1장: 계획 총괄

### 1.1 개발 인원 및 가용 공수 계산
* **참여 인원**: 2명
  * **개발자 A (Python/에이전트 개발)**: Python 백엔드, AI API 연동, LangGraph 오케스트레이션 및 웹 대시보드 담당.
  * **개발자 B (임베디드/하드웨어 개발)**: Phase A 기간 — PC SDL2 시뮬레이터, LVGL/C 파서 지원, OpenCV Vision 모듈. Phase HW 기간 — ESP-IDF, 보드 플래시, USB 카메라 HIL.
* **전체 기간**: 12주 (총 60영업일)
* **총 가용 공수**: $2 \\text{인} \\times 12 \\text{주} \\times 5 \\text{일} = 120 \\text{인-일}$
* **실제 가용 공수 (20% 버퍼 차감)**: $120 \\text{일} \\times 0.8 = 96 \\text{인-일}$
  * *차감 사유*: 주간 회의, 스크럼 스탠드업, 문서 작업 및 **Phase HW 집중 구간(10~12주)** 트러블슈팅/캘리브레이션 시간을 대비한 안전 마진.
* **WBS 계획 공수**: 총 55.5인-일 (개발자 A 단독: 26.5인일, 개발자 B 단독: 27.0인일, A+B 페어: 2.0인일)
  * *공수 계산 원칙*: 모든 공수는 인일 기준으로 계산한다. A+B 페어 작업을 1일 수행하면 2인일로 계산한다.
  * *여유 버퍼*: $96 \\text{일} - 55.5 \\text{일} = 40.5 \\text{일}$ (가용 공수 대비 약 42%의 안전 버퍼. Phase HW 막판 리스크 대응에 우선 투입).
  * *주차별 과부하 기준*: A와 B 각각 주 4인일을 넘기지 않는 것을 원칙으로 하며, 초과 시 Phase B 또는 CoreS3(T-006/T-504)를 컷한다.

### 1.2 Phase별 공수 배분표
| Phase | 주요 과업 범위 | 목표 비율 | 계획 공수 (일) |
|---|---|---|---|
| **Phase A** | 시뮬레이션 기반 소프트웨어 파이프라인 필수 코어 (CLI, AI, SDL2 시뮬, Sim LangGraph, Vision 판정) | 필수 | 32.5인일 |
| **Phase B** | WebAssembly, FastAPI, Streamlit/React 등 선택형 웹 대시보드 확장 | 선택 확장 | 5.5인일 |
| **Phase HW** | ESP-IDF·보드 플래시·카메라 HIL·실기 자가수정·시연 리허설 (10~12주차) | 필수(최종) | 15.5인일 |
| **Cut 보류** | CoreS3 보조 타깃 T-006/T-504 기본 컷 | 범위 축소 | 2.0인일 |
| **합계** | - | - | 55.5인일 |

*Phase A에 T-801/T-802(2.5인일)가 포함되어 기존 "Phase B 시뮬레이터" 역할을 흡수합니다.*

### 1.3 일정 지연 시 컷라인(Cut-line) 시나리오
일정 지연 및 기술적 병목 발생 시 프로젝트 성패를 담보하기 위한 단계적 과업 축소 정책을 다음과 같이 정의합니다.

1. **1단계 컷라인 (FastAPI 및 웹 대시보드 포기)**:
   * *영향*: T-851, T-852 과업 생략.
   * *이유*: CLI + 시뮬 E2E 리포트만으로도 M2(소프트웨어 MVP) 요건을 충족하기 때문입니다.
2. **2단계 컷라인 (M5Stack CoreS3 보조 타깃 지원 포기)** — **기본 적용**:
   * *영향*: T-006, T-504 과업 생략.
   * *이유*: Phase HW 3주(10~12주) 공수 압축. ESP32-P4 단일 타깃에 집중합니다.
3. **3단계 컷라인 (Emscripten WebAssembly 브라우저 렌더링 포기)**:
   * *영향*: T-850 과업 생략.
   * *이유*: PC SDL2 시뮬레이터(T-801, T-802)만으로 UI 검증이 충분합니다.
4. **절대 포기 불가 과업 (Core MVP)**:
   * **Phase A**: `p10 run --mode sim` — 문서 파싱 → 코드 생성 → SDL2 시뮬 → OpenCV/OCR Vision 판정 → 자가수정 루프 → `report.md`.
   * **Phase HW**: ESP32-P4 플래시 + USB 카메라 HIL 최종 검증 1회 이상 성공 (M3). 실패 시 시뮬 E2E + 시뮬 스크린샷 리포트로 시연 대체(실기 기동률 "미측정" 명시).

### 1.4 입력 문서 충돌 처리 로그

| 충돌 항목 | 채택한 기준 | 버린 기준 | 이유 |
|---|---|---|---|
| 실기 vs 시뮬 우선순위 | `단위구현계획서_재정렬_프롬프트.md` — 장비는 마지막 | `Gemini_단위구현계획서_프롬프트.md` 1~2주차 조기 HW 스파이크 | 팀 확정 원칙. 조기 Go/No-Go 스파이크 리스크는 위험 로그로만 관리 |
| Phase B 시뮬레이터 | Phase A 필수 코어로 격상 (T-801/802, 1~2주차) | 기존 Phase B "실용 확장" | 시뮬이 자가수정 루프의 검증 엔진이므로 코어에 포함 |
| 웹 대시보드 | Phase B 선택 확장 | Phase A 필수 | M2 미통과 시 즉시 컷 |
| Solar Pro 3 비전 | [가정] 및 T-009 (fixture 이미지) | 실기 촬영 전제 조기 검증 | 장비 없이 1주차 검증 가능 |
| 개발·시연 OS | T-012 SW 부분 2주차 | T-012 HW(USB/카메라) 1주차 일괄 | HW 접근 검증은 11주차 Phase HW로 분리 |

### 1.5 계획 품질 자체 점검 요약

| 점검 항목 | 현재 값 | 판정 |
|---|---:|---|
| Task 총개수 | 45개 | 적정 |
| 총 공수 | 55.5인일 | 96인일 상한 이내 |
| 2인일 초과 task | 0개 | 적정 |
| Phase HW 10~12주차 실행 공수 | 15.5인일(컷 2.0 제외) | 조건부 적합(A 지원+버퍼 1일 사용) |
| 시뮬→실기 2단계 LangGraph | T-701/702 반영 | 완료 |
| [가정] 검증 기한 | HW 가정 10~11주차로 갱신 | 완료 |

### 1.6 위험 로그 (조기 HW 스파이크 제거)

| 리스크 ID | 설명 | 완화책 |
|---|---|---|
| R-HW-01 | 10주차 BSP/PSRAM 치명 실패 발견 | M2에서 Phase B 즉시 컷; Waveshare 고정 BSP 버전 문서 사전 조사; Phase HW 3주 전담 |
| R-HW-02 | 카메라 반사/지그 실패 | T-603 시뮬 검증 로직 재사용; T-011/T-013 11주차 집중; 암막 후드 |
| R-HW-03 | Phase HW 일정 압박 | CoreS3(T-006/T-504) 기본 컷; T-603/604 핵심은 6~7주차 시뮬 완료; 12주차 T-903/T-905는 A+B 페어와 버퍼 1일로 압축 |
| R-HW-04 | 시뮬≠실기 렌더링 차이 | M3 실기 캘리브레이션; `self_correct_hw` 최대 2라운드 |
| R-HW-05 | 11주차 말 플래시 실패 | 비상 시연: 시뮬 E2E + 스크린샷 리포트 |

---

## 제2장: Task 백로그 총괄표

"""

BACKLOG_ROWS = """| Task ID | Task Name | 분류/모듈 | Phase | 담당 | 공수(일) | 선행 태스크 | 주차 |
|---|---|---|---|---|---|---|---|
| **T-001** | 저장소 구조 및 Python 가상환경 구축 | 공통/인프라 | Phase A | A | 0.5 | 없음 | 1주차 |
| **T-002** | Upstage API 연동 및 공통 모듈 구현 | 공통/인프라 | Phase A | A | 0.5 | T-001 | 1주차 |
| **T-003** | ESP-IDF v5.3+ 개발 환경 구축 | 공통/인프라 | Phase HW | B | 1.0 | T-703 | 10주차 |
| **T-004** | ESP32-P4 BSP 공식 예제 빌드 및 플래시 검증 | 공통/인프라 | Phase HW | B | 1.5 | T-003 | 10주차 |
| **T-005** | 로깅 모듈 및 Run ID 기반 산출물 체계 구현 | 공통/인프라 | Phase A | A | 0.5 | T-002 | 1주차 |
| **T-006** | M5Stack CoreS3 개발 환경 및 예제 검증 | 공통/인프라 | Phase HW(컷) | B | 1.0 | T-003 | 컷(2단계) |
| **T-007** | **[Spike]** ESP32-P4 LCD/터치 PSRAM 메모리 최적화 검증 | 스파이크 | Phase HW | B | 1.0 | T-004 | 10주차 |
| **T-008** | **[Spike]** Upstage Document Parse 표 추출 성능 검증 | 스파이크 | Phase A | A | 1.0 | T-002 | 1주차 |
| **T-009** | **[Spike]** Solar Pro 3 비전 멀티모달 입력 및 판정 실험 | 스파이크 | Phase A | A | 1.0 | T-002 | 1주차 |
| **T-010** | **[Spike]** NC AI VARCO Art 이미지 생성 API 접속 검증 | 스파이크 | Phase A | A | 1.0 | T-002 | 2주차 |
| **T-011** | **[Spike]** USB 카메라 LCD 촬영 화질 및 반사 제어 전처리 실험 | 스파이크 | Phase HW | B | 1.0 | T-004 | 11주차 |
| **T-012** | **[Spike]** 개발·시연 OS 및 Docker/USB/카메라 접근 범위 결정 | 스파이크 | Phase A/HW | A+B | 2.0 | T-001 | 2주차(SW)·11주차(HW) |
| **T-013** | **[Spike]** HIL 물리 환경 최소 구성 및 시리얼 포트 매핑 검증 | 스파이크 | Phase HW | B | 1.0 | T-011, T-012 | 11주차 |
| **T-101** | Typer CLI 명령어 엔트리포인트 구현 | 입력 처리 | Phase A | A | 1.0 | T-005 | 2주차 |
| **T-102** | 사용자 UI 요구사항 및 PDF 파일 검증 모듈 구현 | 입력 처리 | Phase A | A | 0.5 | T-101 | 2주차 |
| **T-201** | Upstage Document Parse 데이터 파싱 및 텍스트 청킹 | 문서 이해 | Phase A | A | 1.0 | T-008, T-102 | 3주차 |
| **T-202** | 데이터시트 핵심 스펙(디스플레이, 레지스터, 터치) 분석기 | 문서 이해 | Phase A | A | 1.5 | T-201 | 3주차 |
| **T-203** | 기술 지식 베이스(Technology KB) JSON 스키마 변환기 | 문서 이해 | Phase A | A | 1.0 | T-202 | 4주차 |
| **T-301** | 보드 프로필 매퍼 및 BSP 고정 템플릿 연동 모듈 | 코드 생성 | Phase A | B | 1.0 | T-203 | 4주차 |
| **T-302** | Solar Pro 3 LVGL UI 레이아웃 프롬프트 설계 | 코드 생성 | Phase A | A | 1.5 | T-203, T-009 | 4주차 |
| **T-303** | LLM 생성 코드 위젯 트리 및 이벤트 핸들러 파서 구현 | 코드 생성 | Phase A | A | 1.5 | T-302 | 5주차 |
| **T-304** | 에이전트 컨텍스트 토큰 예산 관리 모듈 구현 | 코드 생성 | Phase A | A | 1.0 | T-303 | 5주차 |
| **T-401** | VARCO Art API 연동 HMI 이미지 생성기 구현 | 시각 에셋 | Phase A | A | 1.5 | T-010, T-303 | 5주차 |
| **T-402** | GUI 이미지 에셋 LVGL C 배열 변환기(lv_img_conv 연동) | 시각 에셋 | Phase A | B | 1.0 | T-401 | 6주차 |
| **T-501** | BoardTarget 추상클래스 설계 및 ESP32-P4 컴파일 서브프로세스 구현 | 빌드/플래시 | Phase HW | B | 1.5 | T-301, T-402, T-703 | 11주차 |
| **T-502** | esptool 연동 타깃 보드 펌웨어 플래시 제어 모듈 | 빌드/플래시 | Phase HW | B | 1.0 | T-501 | 11주차 |
| **T-503** | GCC/Clang 컴파일러 에러 로그 구문 분석기 구현 | 빌드/플래시 | Phase A | B | 1.0 | 없음(모의 로그) | 8주차 |
| **T-504** | ESP32-S3(M5Stack CoreS3) 빌드 및 플래시 드라이버 포팅 | 빌드/플래시 | Phase HW(컷) | B | 1.0 | T-006, T-502 | 컷(2단계) |
| **T-601** | USB 카메라 기동 및 물리적 촬영 프레임 캡처 모듈 | 실기 검증 | Phase HW | B | 1.0 | T-011, T-502 | 12주차 |
| **T-602** | 촬영 이미지 원근 보정 및 UI 영역 전처리 모듈 | 실기 검증 | Phase HW | B | 1.5 | T-601 | 12주차 |
| **T-603** | OpenCV 기반 위젯 크기/위치 정량 PASS/FAIL 판정기 | Vision(시뮬+실기) | Phase A | B | 1.5 | T-802, T-303 | 6주차 |
| **T-604** | OCR 및 Solar Pro 3 비전 기반 텍스트/의미 일치 분석기 | Vision(시뮬+실기) | Phase A | B | 2.0 | T-603, T-009 | 7주차 |
| **T-701** | LangGraph 2단계 상태머신 (Sim + HW) 그래프 구축 | 오케스트레이션 | Phase A | A | 1.5 | T-304, T-802, T-603, T-604 | 7주차 |
| **T-702** | 자가 수정 루프 재진입 및 라운드 제어기 (sim 5회 / hw 2회) | 오케스트레이션 | Phase A | A | 1.5 | T-701 | 8주차 |
| **T-703** | 체크포인트 세션 저장소 및 최종 검증 보고서 생성기 | 오케스트레이션 | Phase A | A | 1.0 | T-702 | 8주차 |
| **T-801** | LVGL PC VSCode 시뮬레이터(SDL2) 환경 연동 모듈 | 시뮬레이터 | Phase A | B | 1.5 | T-001 | 1주차 |
| **T-802** | PC 시뮬레이터 드라이버·스크린샷 캡처 및 자동 구동 | 시뮬레이터 | Phase A | B | 1.0 | T-801 | 2주차 |
| **T-850** | Emscripten WebAssembly 기반 브라우저 렌더링 파이프라인 | 웹 대시보드 | Phase B | B | 2.0 | T-802, M2통과 | 10주차(선택) |
| **T-851** | 에이전트 통합 제어용 FastAPI 백엔드 서버 구축 | 웹 대시보드 | Phase B | A | 1.5 | T-703 | 10주차(선택) |
| **T-852** | Streamlit/React 기반 UI 대시보드 및 웹 HMI 캔버스 프론트엔드 | 웹 대시보드 | Phase B | A | 2.0 | T-850, T-851 | 11주차(선택) |
| **T-901** | Typer CLI 기반 시뮬 E2E 파이프라인 통합 테스트 (`--mode sim`) | 통합/시연 | Phase A | A | 1.5 | T-703 | 9주차 |
| **T-902** | 평가 지표 4종 자동 정량 측정 (sim 9주 / hw 12주) | 통합/시연 | Phase A/HW | A | 1.5 | T-901 | 9주차·12주차 |
| **T-903** | 파이프라인 극한 테스트(예외 입력, 타임아웃, 케이블 단선) | 통합/시연 | Phase HW | B | 2.0 | T-901, T-502 | 12주차 |
| **T-904** | README 문서, 설치 스크립트 작성 및 비원 개발자 검증 | 통합/시연 | Phase A | B | 1.0 | T-802 | 8주차 |
| **T-905** | 시연 부스 설치용 하드웨어 물리 결선 및 최종 시연 리허설 | 통합/시연 | Phase HW | B | 1.5 | T-903, T-904 | 12주차 |

---

### 2.2 Task 재배치 로그

""" + RELOCATION_LOG + """

### 2.1 설계 요구사항-Task 추적표

| 요구사항 ID | 요구사항 내용 | 출처 문서 | 관련 Task ID | 검증 방법 | 누락 여부 |
|---|---|---|---|---|---|
| REQ-CORE-01 | 사용자는 단일 CLI 진입점으로 파이프라인을 실행한다. | 통합프로그램 설계 방향 | T-101, T-901 | `p10 run --mode sim` 또는 `p10 run --mode hw` | 없음 |
| REQ-CORE-02 | 실행마다 run ID 기반 산출물 폴더에 로그, 코드, 이미지, 리포트를 모은다. | 통합프로그램 설계 방향 | T-005, T-703, T-901 | run 폴더에 `report.md`, 시뮬/실기 캡처 PNG 존재 | 없음 |
| REQ-AI-01 | Upstage Document Parse로 PDF 일부를 파싱하고 결과 품질을 검증한다. | Gemini 프롬프트 | T-008, T-201, T-202 | 테스트 PDF 표/텍스트 추출 | 없음 |
| REQ-AI-02 | Solar Pro 3 이미지 입력은 fixture로 조기 검증한다. | 보강 프롬프트 | T-009, T-604 | fixture 이미지 실험 evidence | 없음 |
| REQ-AI-03 | VARCO Art API 접근 실패 시 정적 에셋 폴백. | 보강 프롬프트 | T-010, T-401, T-402 | 폴백 경로 동작 확인 | 없음 |
| REQ-SIM-01 | PC SDL2 시뮬레이터로 UI 1차 검증 및 자가수정 루프를 수행한다. | 재정렬 프롬프트 | T-801, T-802, T-701 | 시뮬 스크린샷 + PASS/FAIL 리포트 | **신규** |
| REQ-HW-01 | ESP32-P4에서 LVGL 화면 표시 (Phase HW). | 구현설계서 | T-004, T-007, T-501, T-502 | 플래시 로그 + 화면 사진 | 없음 |
| REQ-HW-02 | OS/Docker(SW) 초기 확정, USB/카메라(HW) Phase HW 확정. | 재정렬 프롬프트 | T-012 | 2주차 SW matrix + 11주차 HW matrix | 없음 |
| REQ-HW-03 | HIL 물리 환경 (Phase HW). | 보강 프롬프트 | T-011, T-013, T-905 | 지그·포트 매핑 evidence | 없음 |
| REQ-VISION-01 | OpenCV 정량 비교 (시뮬 PNG 우선, 실기 캡처 후순위). | 통합프로그램 설계 | T-603, T-602 | sim/hw 모드 비교 리포트 | 없음 |
| REQ-AGENT-01 | LangGraph 자가수정: sim 최대 5회, hw 최대 2회. | 구현설계서 | T-701, T-702 | 라운드 상한 테스트 | 없음 |
| REQ-EVAL-01 | 4종 지표 (sim 9주, hw 12주 분리 측정). | 제안서 | T-902 | `metrics_sim.json`, `metrics_hw.json` | 없음 |
| REQ-DEMO-01 | README 기반 60분 내 sim 환경 구축. | 제품성 | T-904 | 제3자 설치 테스트 | 없음 |

"""

MERMAID = """## 제3장: 의존성 그래프

```mermaid
flowchart TD
  subgraph phaseA_infra [PhaseA_소프트웨어_1to2주]
    T001[T-001: venv] --> T002[T-002: Upstage]
    T002 --> T005[T-005: Run ID]
    T002 --> T008[T-008: Doc Parse spike]
    T002 --> T009[T-009: Solar vision spike]
    T002 --> T010[T-010: VARCO spike]
    T001 --> T012sw[T-012: OS/Docker SW]
  end

  subgraph phaseA_sim [PhaseA_시뮬_코어]
    T001 --> T801[T-801: SDL2 시뮬 스캐폴딩]
    T801 --> T802[T-802: sim_driver 캡처]
    T303[T-303: 위젯 파서] --> T603[T-603: OpenCV 판정]
    T802 --> T603
    T603 --> T604[T-604: OCR/VLM]
    T304[T-304: 토큰 예산] --> T701[T-701: LangGraph 2단계]
    T802 --> T701
    T604 --> T701
    T701 --> T702[T-702: self_correct]
    T702 --> T703[T-703: report]
    T703 --> T901sim[T-901: E2E sim]
  end

  subgraph phaseA_doc [PhaseA_문서_코드]
    T005 --> T101[T-101: CLI]
    T101 --> T102[T-102: validator]
    T008 --> T201[T-201: PDF 청킹]
    T102 --> T201
    T201 --> T202[T-202: 스펙 분석] --> T203[T-203: Technology KB]
    T203 --> T301[T-301: 보드 프로필]
    T203 --> T302[T-302: UI 프롬프트]
    T302 --> T303
    T303 --> T304
    T010 --> T401[T-401: VARCO 에셋]
    T303 --> T401
    T401 --> T402[T-402: img conv]
  end

  subgraph phaseHW [PhaseHW_10to12주]
    T703 --> T003[T-003: ESP-IDF]
    T003 --> T004[T-004: P4 BSP]
    T004 --> T007[T-007: PSRAM]
    T004 --> T011[T-011: 카메라 spike]
    T011 --> T013[T-013: HIL]
    T301 --> T501[T-501: idf build]
    T402 --> T501
    T703 --> T501
    T501 --> T502[T-502: flash]
    T502 --> T601[T-601: 카메라]
    T601 --> T602[T-602: 원근보정]
    T602 --> T603hw[T-603 hw 캘리브레이션]
    T901sim --> T903[T-903: chaos test]
    T502 --> T903
    T903 --> T905[T-905: 시연 리허설]
  end

  T703 -.->|sim_gate_passed| T003
  T901sim --> T902sim[T-902 sim metrics]
```

*점선: M2(9주차) 시뮬 게이트 통과 후 Phase HW 착수. T-701 내부에 `verify_simulation` → (게이트) → `build_and_flash` → `verify_physical` 2단계 그래프가 구현됩니다.*

---

"""

CHAPTER4 = """## 제4장: 주차별 실행 계획 (12주)

### 4.1 주차별 세부 계획

#### 1주차
* **주간 목표**: Python 환경 + API 스파이크 + **PC SDL2 시뮬레이터 착수**.
* **배정 Task**: T-001, T-002, T-005, T-008, T-009 (A) | T-801 (B, 빈 템플릿 UI로 SDL2/CMake 스캐폴딩 검증)
* **주말 체크포인트**:
  * Q1. Upstage Document Parse가 PDF 표를 추출하는가?
  * Q2. Solar Pro 3 fixture 이미지 3종 실험이 완료되었는가?
  * Q3. SDL2 + CMake 시뮬레이터 빌드가 1024×600 창을 띄우는가? (hello UI)

#### 2주차
* **주간 목표**: CLI 입력 + VARCO 스파이크 + **시뮬 드라이버** + OS/Docker(SW) 확정.
* **배정 Task**: T-010, T-101, T-102, T-012(SW부분) (A/A+B) | T-802 (B)
* **주말 체크포인트**:
  * Q1. `sim_driver`가 시뮬 창을 5초 기동 후 스크린샷 PNG를 저장하는가?
  * Q2. Typer CLI가 PDF/요구사항을 접수하는가?
  * Q3. `docs/environment_decision.md`에 Python/Docker 범위가 기록되었는가? (HW 검증은 아직 미수행)

#### 3주차
* **주간 목표**: 데이터시트 파싱 고도화.
* **배정 Task**: T-201, T-202 (A) | T-303 C/LVGL 파서 지원 (B)
* **주말 체크포인트**:
  * Q1. MCU/디스플레이 스펙이 청킹되는가?
  * Q2. 위젯 파서 프로토타입이 샘플 `ui_screens.c`를 파싱하는가?

#### 4주차
* **주간 목표**: Technology KB + 보드 프로필(데이터시트 기반) + UI 프롬프트.
* **배정 Task**: T-203, T-302 (A) | T-301 (B)
* **주말 체크포인트**:
  * Q1. JSON KB 스키마가 생성되는가?
  * Q2. `board_config.h`가 1024×600으로 합성되는가? (실기 없이)

#### 5주차
* **주간 목표**: 위젯 파서·토큰 예산·VARCO 에셋.
* **배정 Task**: T-303, T-304, T-401 (A)
* **주말 체크포인트**:
  * Q1. 위젯 트리 JSON이 복원되는가?
  * Q2. VARCO/폴백 PNG가 준비되는가?

#### 6주차
* **주간 목표**: 이미지 C변환 + **시뮬 스크린샷 Vision 판정**.
* **배정 Task**: T-402 (B) | T-603 (B, T-802 PNG와 T-303 위젯 매니페스트 입력)
* **주말 체크포인트**:
  * Q1. T-603이 시뮬 PNG에서 위젯 PASS/FAIL을 반환하는가?

#### 7주차 — **마일스톤 M1**
* **주간 목표**: OCR/VLM + **LangGraph 시뮬 루프** 통합.
* **배정 Task**: T-604 (B) | T-701 (A)
* **주말 체크포인트 (M1)**:
  * Q1. [하]/[중] 샘플 각 1건이 3회 이내 sim PASS로 수렴하는가?
  * Q2. `report.md`에 sim Vision 결과가 기록되는가?

#### 8주차
* **주간 목표**: 자가수정·리포트·컴파일 에러 파서·README 초안.
* **배정 Task**: T-702, T-703 (A) | T-503, T-904 (B)
* **주말 체크포인트**:
  * Q1. sim `self_correct` 5회 상한이 동작하는가?

#### 9주차 — **마일스톤 M2**
* **주간 목표**: **시뮬 E2E** + 평가지표(sim).
* **배정 Task**: T-901, T-902(sim) (A) | 버퍼 / Phase B 준비 (B)
* **주말 체크포인트 (M2)**:
  * Q1. `p10 run --mode sim` 전체가 완료되는가?
  * Q2. M2 통과 시에만 Phase B 또는 Phase HW 착수 결정이 문서화되었는가?

#### 10주차 — **Phase HW 착수**
* **주간 목표**: ESP-IDF + P4 BSP + PSRAM. (선택) Phase B.
* **배정 Task**: T-003, T-004, T-007 (B) | T-851, T-850(선택) (A/B)
* **주말 체크포인트**:
  * Q1. `idf.py flash` 1회 이상 성공하는가?
  * Q2. PSRAM 할당 로그가 evidence에 저장되었는가?

#### 11주차
* **주간 목표**: 카메라/HIL + 빌드/플래시 파이프라인 + (선택) 웹 대시보드.
* **배정 Task**: T-011, T-012(HW), T-013, T-501, T-502 (B) | T-852(선택) (A)
* **주말 체크포인트**:
  * Q1. HIL 포트 매핑·지그 사진이 evidence에 있는가?
  * Q2. Python에서 `idf.py build` 서브프로세스가 성공하는가?

#### 12주차 — **마일스톤 M3**
* **주간 목표**: 실기 카메라 HIL + 극한 테스트 + 시연 리허설.
* **배정 Task**: T-601, T-602 (B) | T-903, T-905 (A+B 페어/버퍼) | T-902(hw), `p10 run --mode hw` (A)
* **주말 체크포인트 (M3)**:
  * Q1. 실기 Vision HIL 1회 이상 PASS하는가?
  * Q2. 실기 기동률 70%+, Vision 일치율 75%+ (또는 비상 시뮬 시연 시나리오)?

### 4.2 마일스톤 및 품질 게이트 정의

* **마일스톤 1 (M1 - 7주차 종료): 시뮬레이션 자가수정 루프 수렴**
  * *품질 게이트*:
    1. `verify_simulation` 경로: SDL2 스크린샷 → T-603/604 PASS/FAIL.
    2. 난이도 [하]/[중] 샘플 각 1건, **3회 이내** sim PASS.
    3. `output/<run_id>/report.md` 생성.
    4. `self_correct` sim 라운드 **최대 5회** 안전 종료.
  * *미통과 시*: 8주차 전반 T-701~703 튜닝, Phase B 착수 연기.

* **마일스톤 2 (M2 - 9주차 종료): 소프트웨어 E2E 완성**
  * *품질 게이트*:
    1. `p10 run --mode sim` 샘플 1건 완료.
    2. `metrics_sim.json`에 sim 컴파일(시뮬 빌드) 성공률, Vision 일치율, 수렴 라운드 기록.
    3. T-901 통과.
  * *미통과 시*: Phase B(선택 확장) 즉시 컷, 10주차 전면 디버깅.
  * *통과 시*: Phase HW(10주차) 착수 + Phase B 선택 착수.

* **마일스톤 3 (M3 - 12주차 종료): 실기 HIL 및 시연**
  * *품질 게이트*:
    1. `p10 run --mode hw` 1건 이상 완료 (플래시+카메라+Vision).
    2. 컴파일 성공률 70%+, 실기 기동률 70%+, Vision 일치율 75%+.
    3. T-905 리허설 5회 또는 비상 시뮬 시연 스크립트 준비.
  * *미통과 시*: Phase B 폐기, 시뮬 E2E 시연으로 대체.

### 4.3 개발자 B 인력 재배치 (1~9주차, 실기 제외)

| 주차 | B 담당 Task | 내용 |
|---|---|---|
| 1 | T-801 | SDL2 시뮬 환경 스캐폴딩 |
| 2 | T-802, T-012(SW 지원) | sim_driver, 스크린샷 캡처 |
| 3 | T-303 지원 | LVGL C 파서 협업 |
| 4 | T-301 | 데이터시트 기반 보드 프로필 |
| 5 | (T-303 협업) | 파서·템플릿 연동 |
| 6 | T-402, T-603 | img conv + OpenCV sim Vision |
| 7 | T-604 | OCR/VLM sim 판정 |
| 8 | T-503, T-904 | 컴파일 에러 파서(모의 로그), README |
| 9 | Phase B 보조 / 버퍼 | M2 대비 |

---

## 제5장: Task 카드 전체

"""

# Task card patches: (task_id, replacements dict for key fields)
CARD_PATCHES = {
    "T-003": {
        "phase": "공통/인프라, **Phase HW**",
        "pre": "T-703",
        "purpose_add": " **Phase HW(10주차) 전용.** M2 시뮬 게이트 통과 후 ESP-IDF 툴체인을 구축한다.",
    },
    "T-012": {
        "phase": "스파이크, **Phase A(2주차 SW) / Phase HW(11주차 HW)**",
        "pre": "T-001",
        "purpose_replace": "입문자가 환경 차이로 막히지 않도록 개발·시연 기준 OS와 Docker 범위를 **2주차에(SW)** 확정하고, USB 플래시·카메라 접근은 **11주차(HW)**에 검증한다.",
        "impl_add": "\n  5. **2주차(SW)**: Python, Docker, 문서 빌드만 검증. **11주차(HW)**: 카메라·시리얼·플래시 검증을 `docs/verification/T-012_hw_matrix.md`에 추가 기록.",
        "test_sw": "  - **2주차 SW 테스트**: `python -c \"import cv2\"`, Docker 문서 빌드만 확인 (ESP-IDF·보드 불필요).\n  - **11주차 HW 테스트**: `idf.py --version`, `list_serial_ports`, 카메라 프레임 획득.",
    },
    "T-301": {
        "pre": "T-203",
        "purpose_add": " 데이터시트 기반 프로필만 사용하며 **T-007(PSRAM 실측) 선행을 요구하지 않는다.**",
    },
    "T-503": {
        "pre": "없음 (모의 GCC 로그 fixture 사용)",
        "purpose_add": " **Phase A(8주차)**에 모의 컴파일 로그로 파서를 완성하고, Phase HW에서 실제 `idf.py` 로그와 연동한다.",
    },
    "T-501": {
        "phase": "빌드/플래시, **Phase HW**",
        "pre": "T-301, T-402, T-703",
        "purpose_add": " **시뮬 E2E(M2) 완료 후** ESP32-P4 `idf.py build` 서브프로세스를 구현한다.",
    },
    "T-603": {
        "phase": "Vision 판정, **Phase A(시뮬) / Phase HW(캘리브레이션)**",
        "pre": "T-802, T-303",
        "purpose_replace": "T-802가 저장한 **시뮬레이터 스크린샷(1024×600 PNG)**과 T-303의 위젯 기대 좌표/텍스트 매니페스트를 대조해 PASS/FAIL한다. Phase HW(12주차)에서는 T-602 실기 보정 이미지에 동일 로직을 재적용한다.",
        "impl_add": "\n  4. `ImageSource` 추상화: `SimCaptureProvider`(T-802) / `CameraCaptureProvider`(T-602) 이중 입력.",
        "test_add": "\n  - **시뮬 모드**: T-802 `captured_sim.png` fixture로 pytest.\n  - **실기 모드**: 12주차 HIL 캡처 이미지로 재검증.",
    },
    "T-604": {
        "phase": "Vision 판정, **Phase A(시뮬)**",
        "pre": "T-603, T-009",
        "purpose_add": " 입력 이미지는 시뮬 스크린샷 우선. 원근 왜곡·반사 문제 없음.",
    },
    "T-602": {
        "phase": "실기 검증, **Phase HW**",
        "pre": "T-601",
        "purpose_add": " **Phase HW(12주차) 전용.** 시뮬 경로에서는 bypass.",
    },
    "T-701": {
        "phase": "오케스트레이션, **Phase A**",
        "pre": "T-304, T-802, T-603, T-604",
        "name": "LangGraph 2단계 상태머신 (Sim + HW) 그래프 구축",
        "purpose_replace": "시뮬레이션 루프와 실기 최종 검증 루프를 **단일 그래프 내 2단계**로 구현한다.",
        "impl_replace": """  1. `src/agent/orchestrator.py`에 `HMIAgentState` 및 `run_mode` (`sim` | `hw`) 필드를 정의한다.
  2. **1단계 (Phase A, 항상)**: `parse_datasheet` → `generate_code` → `verify_simulation` → `self_correct` (FAIL 시 `generate_code` 재순환, **최대 5회**).
  3. `verify_simulation` 구현: T-802 `capture_screenshot()` → T-603/604 판정. 게이트 조건: [하] 샘플 **3회 연속 PASS**, 위젯 오차 **±5%** 이내.
  4. **2단계 (Phase HW, `run_mode=hw` 및 sim_gate_passed=True)**: `build_and_flash` → `verify_physical` → `self_correct_hw` (**최대 2회**).
  5. `verify_physical`: T-601~602 실카메라 경로 + T-603/604 재사용.
  6. 조건부 엣지로 sim 단계만으로도 `END` 가능 (`--mode sim`).""",
    },
    "T-702": {
        "purpose_add": " **sim `self_correct` 최대 5회**, **`self_correct_hw` 최대 2회**를 분리 제어한다.",
    },
    "T-801": {
        "phase": "시뮬레이터, **Phase A (필수 코어)**",
        "pre": "T-001 (환경 스캐폴딩; T-303 완료 후 `ui_screens.c` 연동)",
        "purpose_replace": "생성된 LVGL C 코드를 PC SDL2(1024×600)에서 렌더링하여 **자가수정 루프의 1차 검증 엔진**으로 사용한다. 실기 플래시 **이전**에 시뮬 게이트를 통과해야 Phase HW로 진행한다.",
    },
    "T-802": {
        "phase": "시뮬레이터, **Phase A (필수 코어)**",
        "name": "PC 시뮬레이터 드라이버·스크린샷 캡처 및 자동 구동",
        "purpose_replace": "시뮬레이터 빌드·기동·종료와 **SDL 창 스크린샷 PNG 저장**(`captured_sim.png`)을 자동화하여 T-603/604 및 `verify_simulation` 노드의 입력을 제공한다.",
        "impl_add": "\n  4. `capture_screenshot(path: Path) -> Path` 메서드: 1024×600 PNG를 `output/<run_id>/assets/captured_sim.png`에 저장.",
    },
    "T-901": {
        "name": "Typer CLI 기반 시뮬 E2E 파이프라인 통합 테스트",
        "phase": "통합/시연, **Phase A (9주차)**",
        "purpose_replace": "`p10 run --mode sim`으로 문서 입력부터 시뮬 Vision 판정·자가수정·리포트까지 **장비 없이** E2E 검증한다.",
        "impl_replace": """  1. `tests/e2e/test_cli_pipeline_sim.py` 작성.
  2. ESP32 보드·웹캠 **불필요**. T-802 스크린샷 + T-603/604 실제 모듈 사용.
  3. (12주차) `tests/e2e/test_cli_pipeline_hw.py`는 Phase HW용 별도 스위트.""",
        "test_replace": "  - 실행: `python -m pytest tests/e2e/test_cli_pipeline_sim.py -v -s`\n  - 통과 기준: sim 모드 5회 이내 PASS, `report.md` 생성.",
    },
}


def extract_task_cards(content: str) -> dict:
    cards = {}
    pattern = re.compile(r"(### \[T-\d+\].*?)(?=\n---\n|\n## 제)", re.DOTALL)
    for m in pattern.finditer(content):
        block = m.group(1)
        tid = re.search(r"\[T-(\d+)\]", block).group(0).strip("[]")
        cards[tid] = block
    return cards


def _module_from_phase_line(card: str) -> str:
    m = re.search(r"\* \*\*3\. 모듈/Phase\*\*: (.+)", card)
    if not m:
        return "기타"
    raw = m.group(1).strip()
    if "," in raw:
        return raw.split(",", 1)[0].strip()
    for old in ("Phase A", "Phase B", "Phase HW", "Phase C", "Phase A/HW"):
        if raw.endswith(old):
            return raw[: -len(old)].strip().rstrip(",")
    return raw


def patch_card(tid: str, card: str) -> str:
    p = CARD_PATCHES.get(tid, {})
    meta = TASK_META.get(tid)
    if meta:
        phase, week, pre = meta
        if p.get("phase"):
            phase_line = f"* **3. 모듈/Phase**: {p['phase']}"
        else:
            module = _module_from_phase_line(card)
            phase_line = f"* **3. 모듈/Phase**: {module}, {phase}"
        card = re.sub(r"\* \*\*3\. 모듈/Phase\*\*:.*", phase_line, card, count=1)
        card = re.sub(
            r"\* \*\*6\. 선행 task\*\*:.*",
            f"* **6. 선행 task**: {p.get('pre', pre)}",
            card,
            count=1,
        )
    if p.get("name"):
        card = re.sub(
            r"\* \*\*2\. Task Name\*\*:.*",
            f"* **2. Task Name**: {p['name']}",
            card,
            count=1,
        )
    if p.get("purpose_replace"):
        card = re.sub(
            r"\* \*\*7\. 목적\*\*:.*",
            f"* **7. 목적**: {p['purpose_replace']}",
            card,
            count=1,
        )
    elif p.get("purpose_add"):
        card = re.sub(
            r"(\* \*\*7\. 목적\*\*:.*?)(\n\* \*\*8)",
            lambda m: m.group(1) + p["purpose_add"] + m.group(2),
            card,
            count=1,
            flags=re.DOTALL,
        )
    if p.get("impl_replace"):
        card = re.sub(
            r"\* \*\*8\. 구현 내용\*\*:.*?\n\* \*\*9\. 산출물\*\*:",
            f"* **8. 구현 내용**:\n{p['impl_replace']}\n* **9. 산출물**:",
            card,
            count=1,
            flags=re.DOTALL,
        )
    elif p.get("impl_add"):
        card = re.sub(
            r"(\* \*\*8\. 구현 내용\*\*:.*?)(\n\* \*\*9\. 산출물\*\*:)",
            lambda m: m.group(1) + p["impl_add"] + m.group(2),
            card,
            count=1,
            flags=re.DOTALL,
        )
    if p.get("test_replace"):
        card = re.sub(
            r"\* \*\*10\. 단위 테스트 절차\*\*:.*?\n\* \*\*11\. 완료 판정",
            f"* **10. 단위 테스트 절차**:\n{p['test_replace']}\n* **11. 완료 판정",
            card,
            count=1,
            flags=re.DOTALL,
        )
    elif p.get("test_add"):
        card = re.sub(
            r"(\* \*\*10\. 단위 테스트 절차\*\*:.*?)(\n\* \*\*11\. 완료 판정)",
            lambda m: m.group(1) + p["test_add"] + m.group(2),
            card,
            count=1,
            flags=re.DOTALL,
        )
    if p.get("test_sw"):
        card = re.sub(
            r"  - 준비: ESP32-P4 보드.*?\n  - 실행:",
            f"{p['test_sw']}\n  - 실행:",
            card,
            count=1,
            flags=re.DOTALL,
        )
    return card


def patch_generic_phase(card: str, tid: str) -> str:
    if tid in CARD_PATCHES:
        return card
    meta = TASK_META.get(tid)
    if not meta:
        return card
    phase, week, pre = meta
    module = _module_from_phase_line(card)
    if module.startswith("Phase "):
        module = "기타"
    card = re.sub(
        r"\* \*\*3\. 모듈/Phase\*\*:.*",
        f"* **3. 모듈/Phase**: {module}, {phase}",
        card,
        count=1,
    )
    card = re.sub(r"\* \*\*6\. 선행 task\*\*:.*", f"* **6. 선행 task**: {pre}", card, count=1)
    return card


CHAPTER6_9 = """## 제6장: 테스트 전략

### 6.1 테스트 피라미드 및 다이어그램
본 프로젝트는 **시뮬레이션 우선, 실기 최종 확인** 원칙에 따라 5단계 피라미드를 운용합니다.

```
       / \\
      / E2E \\  <-- [E2E-sim] 9주차: --mode sim  /  [E2E-hw] 12주차: --mode hw
     /-------\\
    /   HIL   \\  <-- [HIL] Phase HW 1회성 최종 검증 (10~12주차)
   /-----------\\
  /   System    \\  <-- [System] PC SDL2 시뮬 + 스크린샷 Vision (Nightly, 2주차~)
 /---------------\\
/  Integration    \\  <-- [Integration] KB → 코드 생성 스키마
/-------------------\\
|       Unit        |  <-- [Unit] Pytest 모듈 단위
+-------------------+
```

| 테스트 레벨 | 검증 기법 | 실행 주기 | 명령어 |
|---|---|---|---|
| **Unit** | Pytest | 커밋 시 | `pytest tests/unit/` |
| **Integration** | Pytest | Daily | `pytest tests/integration/` |
| **System** | SDL2 sim + T-603/604 | **Nightly (2주차~)** | `pytest tests/system/` |
| **HIL** | 실기 플래시+카메라 | **M3 / 12주차만** | `pytest tests/hil/` |
| **E2E-sim** | 전체 sim 파이프라인 | **M2 / 9주차** | `pytest tests/e2e/test_cli_pipeline_sim.py` |
| **E2E-hw** | 전체 hw 파이프라인 | **M3 / 12주차** | `pytest tests/e2e/test_cli_pipeline_hw.py` |

*기존 계획의 M1/M2가 HIL을 6~9주에 강제하던 구조를 폐기하고, HIL은 Phase HW 전용으로 재정의했습니다.*

{ch6_placeholder}

---

## 제7장: 운용·제품성 검증 계획

### 7.1 제품성 검증 기준 (갱신)
| 검증 항목 | Phase A (sim) | Phase HW |
|---|---|---|
| 첫 실행 | `p10 run --mode sim` 60분 내 | `p10 run --mode hw` (M3) |
| 산출물 | report.md + captured_sim.png | + captured_raw.png |
| 자가수정 상한 | 5 라운드 | 2 라운드(hw) |

### 7.2 ~ 7.4
(기존 운용 검증·장애 대응·run ID 체계 유지)

---

## 제8장: 진행 관리 규칙

### 8.1 일일 스탠드업 체크 (갱신)
* Phase A(1~9주): **시뮬 게이트 진척** 중심 보고.
* Phase HW(10~12주): **플래시/카메라 블로커** 중심 보고.

### 8.2 ~ 8.5
(기존 진행 관리 규칙 유지)

---

## 제9장: 가정 및 확인 task 매핑

| 가정 | 영향 | 검증 Task | **신규 기한** | Fallback |
|---|---|---|---|---|
| [가정 1] Solar Pro 3 비전 | VLM 보조 판정 | T-009 | **1주차** (fixture) | OpenCV+OCR 100% |
| [가정 2] VARCO Art API | 동적 에셋 | T-010 | **2주차** | Static Placeholder |
| [가정 3] MIPI-DSI BSP 호환 | 실기 기동률 0% | T-007 | **10주차** | BSP 다운그레이드 |
| [가정 4] 카메라 반사 제어 | Vision 오판 | T-011 | **11주차** | 15° 사선+암막 |
| [가정 5] 부트롬 DTR 복구 | 플래시 교착 | T-004 | **10주차** | 수동 Boot 모드 |
| [가정 6] langchain-upstage | API 호출 | T-002, T-008 | **1주차** | httpx REST |
| [가정 7] OS/USB/카메라 동시 안정 | 시연 불가 | T-012 | **SW 2주차 / HW 11주차** | 공식 OS 1개 고정 |
| [가정 8] WebAssembly 선택 확장 | 웹 UI | T-850~852 | **M2 통과 후** | CLI+sim 스크린샷 |

---

## 부록: 문서 품질 자체 점검표

| 점검 항목 | 결과 | 판정 |
|---|---|---|
| Task 총개수 | 45개 | 통과 |
| 공수 합계 | 55.5인일 | 96인일 이내 |
| 1단계 위반 10+3개 반영 | 재정렬_분석보고.md | 통과 |
| LangGraph 2단계 재설계 | T-701/702 | 통과 |
| 마일스톤 M1/M2/M3 재정의 | 제4.2장 | 통과 |
| 개발자 B 1~9주 재배치 | 제4.3장 | 통과 |
| 리스크 로그 | 제1.6장 | 통과 |
| 순환 의존 | Mermaid 검토 | 통과 |
| Phase HW 10~12주 완료 가능성 | 조건부(CoreS3 컷, A+B 페어, 버퍼 1일 사용) | 관리 필요 |

### 재정렬 품질 자체 점검표 (프롬프트 8항목)

| # | 점검 항목 | 결과 |
|---|---|---|
| 1 | 1단계 위반 지점 10+3개 전수 반영 | ✅ `재정렬_분석보고.md` |
| 2 | LangGraph 2단계 재설계 반영 | ✅ T-701 카드 |
| 3 | 마일스톤 재정의 | ✅ M1=7주, M2=9주, M3=12주 |
| 4 | 개발자 B 초반 인력 재배치 | ✅ 제4.3장 |
| 5 | 리스크 로그 갱신 | ✅ 제1.6장 |
| 6 | 순환 의존 없음 | ✅ T-801 선행을 T-001 스캐폴딩으로 완화 |
| 7 | 공수 합계 96인일 이내 | ✅ 55.5인일 |
| 8 | Phase HW 10~12주 완료 가능 | ⚠️ 조건부 (CoreS3 컷, sim 선행 검증, A+B 페어/버퍼 사용) |
"""

def build_document(orig: str) -> str:
    cards = extract_task_cards(orig)
    order = sorted(cards.keys(), key=lambda x: int(x.split("-")[1]))

    ch5_parts = []
    for tid in order:
        c = cards[tid]
        c = patch_card(tid, c)
        c = patch_generic_phase(c, tid)
        ch5_parts.append(c)
        ch5_parts.append("\n---\n\n")

    ch6_match = re.search(r"(### 6\.2 테스트 데이터.*?)## 제7장", orig, re.DOTALL)
    ch6_body = ch6_match.group(1) if ch6_match else ""
    ch6_final = CHAPTER6_9.replace(
        "{ch6_placeholder}",
        ch6_body.strip() if ch6_body else "(제6.2~6.4: `단위구현계획서_재정렬전.md` 참조)",
    )

    ch7_match = re.search(r"(## 제7장:.*?)## 제8장", orig, re.DOTALL)
    ch7_body = ch7_match.group(1) if ch7_match else ""
    ch6_final = ch6_final.replace(
        "### 7.2 ~ 7.4\n(기존 운용 검증·장애 대응·run ID 체계 유지)",
        ch7_body.split("### 7.1", 1)[-1] if "### 7.1" in ch7_body else ch7_body,
    )

    ch8_match = re.search(r"(## 제8장:.*?)## 제9장", orig, re.DOTALL)
    ch8_body = ch8_match.group(1) if ch8_match else ""
    ch6_final = ch6_final.replace(
        "### 8.2 ~ 8.5\n(기존 진행 관리 규칙 유지)",
        "\n".join(ch8_body.split("\n")[2:]) if ch8_body else "",
    )
    ch6_final = ch6_final.replace(
        "* [ ] Waveshare ESP32-P4 및 M5Stack CoreS3 2종 칩셋 아키텍처 환경 컴파일 분기 연동을 지원하는가?",
        "* [ ] Waveshare ESP32-P4 단일 주력 타깃의 실기 기동이 확인되었는가? (CoreS3는 T-006/T-504 컷 해제 시 별도 가산 항목)",
    )
    ch6_final = ch6_final.replace(
        "Phase C task와 보조 타깃 task",
        "Phase B 선택 확장 task와 보조 타깃 task",
    )
    ch6_final = ch6_final.replace(
        "Phase C 과업 폐기 절차",
        "Phase B 선택 확장 과업 폐기 절차",
    )

    return (
        CHAPTER1
        + BACKLOG_ROWS
        + MERMAID
        + CHAPTER4
        + "".join(ch5_parts)
        + ch6_final
    )


def main():
    import sys
    orig_path = BACKUP if BACKUP.exists() else ORIG
    orig = orig_path.read_text(encoding="utf-8")
    out = build_document(orig)
    if "--stdout" in sys.argv:
        sys.stdout.buffer.write(out.encode("utf-8"))
        return
    out_path = OUT
    for i, arg in enumerate(sys.argv):
        if arg == "--out" and i + 1 < len(sys.argv):
            out_path = Path(sys.argv[i + 1])
            break
    if not BACKUP.exists() and out_path == OUT:
        BACKUP.write_text(ORIG.read_text(encoding="utf-8"), encoding="utf-8")
    out_path.write_text(out, encoding="utf-8")
    print(f"Wrote {out_path} ({len(out.splitlines())} lines)")


if __name__ == "__main__":
    main()
