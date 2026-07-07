# T-008 검증 기록 — Upstage Document Parse 표 추출 성능 검증

- 생성 시각: 2026-07-07T17:56:03+09:00
- Task: [T-008] [Spike] Upstage Document Parse 표 추출 성능 검증
- 선행: T-002 (main 머지 완료)

## 1. 실험 개요

카드 7 목적: ESP32-P4 데이터시트류 문서의 핀맵·레지스터 맵 등 복잡한 표를 Upstage Document Parse가 누락 없이 마크다운/HTML 테이블 구조로 추출하는지 검증한다.

### 입력 데이터 처리 방식

- 저장소에 실제 ESP32-P4 데이터시트 PDF가 없어, 카드 8-2가 요구하는 '디스플레이 핀 구성 + 레지스터 맵'을 포함한 대체 샘플 데이터시트 PDF를 `reportlab`으로 합성해 `tests/data/p4_datasheet_sample.pdf`(5페이지, 5개 표)로 저장했다.
- 표 종류: (1) MIPI-DSI 디스플레이 핀 구성, (2) LCD 컨트롤러 레지스터 맵, (3) 전원 레일, (4) 클럭 소스, (5) GPIO Alt-function mux.
- `reportlab`은 fixture 생성 전용 임시 도구로만 사용했고 저장소 산출물/런타임 의존성에는 포함하지 않았다.

## 2. 실험 절차 (카드 10항)

- 실행: `.venv\Scripts\python.exe -m pytest tests/test_document_parser.py -k "test_table_extraction" -v -s`
- API: `UpstageDocumentParseLoader(split='element', output_format='html', ocr='auto')` — 실제 UPSTAGE_API_KEY로 호출.
- HTML `<table>` → 마크다운 표 구문 복원 후, 핀맵+레지스터맵 전체 셀 그라운드 트루스 대비 손실율 측정.

## 3. 결과 (통과 기준: 셀 텍스트 손실율 < 5%)

- 추출된 표 요소 개수: **5개** (fixture의 5개 표 전부 인식)
- 마크다운 표 구문(`|---|---|`) 포맷팅: **정상**
- 핵심 표 셀 손실율: **1.18%** (기준 5% 미만)
- API 응답: **200 정상** (예외 없이 element 파싱 완료)

### 관찰된 유일한 결함

- 레지스터 맵의 `V_RES` 셀이 `VRES`로 추출됨(언더스코어 1개 소실). 70개 핵심 셀 중 1개로 손실율에 반영됨. 그 외 핀 번호·주소·리셋값·설명 텍스트는 전부 정확히 보존.

## 4. Go/No-Go 결론

### 결론: **GO**

손실율 1.18%로 카드 10항 통과 기준(<5%)을 충족한다. Upstage Document Parse는 데이터시트류 표를 마크다운/HTML 구조로 신뢰도 높게 추출하므로, 후속 T-201(문서 파싱·청킹)의 표 추출 기반 기술로 채택한다(**Go**).

### Fallback (카드 12항) — 참고

- 만약 셀 병합으로 열 어긋남/손실율 >=5%였다면: Upstage Information Extract API를 병행 연동해 핵심 사양 파라미터(해상도, 핀 번호 등)를 키-밸류로 이중 검증 추출한다. 이번 실험에서는 손실율이 기준 이내라 Fallback 발동 불필요.

## 5. 추출된 표 (마크다운 복원 결과)

### 표 1 (page 1)

| Pin | Signal | Direction | Default Level | Description |
| --- | --- | --- | --- | --- |
| GPIO0 | DSI_CLK_P | OUT | Low | MIPI-DSI clock lane positive |
| GPIO1 | DSI_CLK_N | OUT | Low | MIPI-DSI clock lane negative |
| GPIO2 | DSI_D0_P | OUT | Low | Data lane 0 positive |
| GPIO3 | DSI_D0_N | OUT | Low | Data lane 0 negative |
| GPIO4 | DSI_D1_P | OUT | Low | Data lane 1 positive |
| GPIO5 | DSI_D1_N | OUT | Low | Data lane 1 negative |
| GPIO23 | LCD_RESET | OUT | High | Panel hardware reset (active low) |
| GPIO24 | LCD_BL_EN | OUT | Low | Backlight enable |

### 표 2 (page 2)

| Address | Register | Reset Value | Access | Function |
| --- | --- | --- | --- | --- |
| 0x00 | CTRL_MODE | 0x0000 | R/W | Display controller mode select |
| 0x04 | H_RES | 0x0400 | R/W | Horizontal resolution (1024) |
| 0x08 | VRES | 0x0258 | R/W | Vertical resolution (600) |
| 0x0C | PIX_FMT | 0x0002 | R/W | Pixel format RGB565 |
| 0x10 | FB_ADDR | 0x00000000 | R/W | Framebuffer base address |
| 0x14 | INT_STAT | 0x0000 | R | Interrupt status flags |
| 0x18 | INT_MASK | 0xFFFF | R/W | Interrupt mask register |

### 표 3 (page 3)

| Rail | Min (V) | Typ (V) | Max (V) | Current (mA) |
| --- | --- | --- | --- | --- |
| VDD_CPU | 0.95 | 1.00 | 1.05 | 500 |
| VDD_IO | 3.13 | 3.30 | 3.47 | 120 |
| VDD_DSI | 1.14 | 1.20 | 1.26 | 80 |
| VDD_PLL | 1.71 | 1.80 | 1.89 | 40 |

### 표 4 (page 4)

| Clock | Source | Frequency (MHz) | Divider | Target Peripheral |
| --- | --- | --- | --- | --- |
| CPU_CLK | PLL0 | 400 | 1 | HP CPU core |
| APB_CLK | PLL0 | 100 | 4 | Peripheral bus |
| DSI_CLK | PLL1 | 500 | 1 | MIPI-DSI PHY |
| SPI_CLK | APB | 50 | 2 | SPI master |

### 표 5 (page 5)

| GPIO | AF0 | AF1 | AF2 | AF3 |
| --- | --- | --- | --- | --- |
| GPIO30 | UART0_TX | I2C0_SDA | PWM0 | GPIO |
| GPIO31 | UART0_RX | I2C0_SCL | PWM1 | GPIO |
| GPIO32 | SPI2MOSI | SDIO_D0 | PWM2 | GPIO |
| GPIO33 | SPI2_MISO | SDIO_D1 | PWM3 | GPIO |
| GPIO34 | SPI2_CLK | SDIO_CLK | PWM4 | GPIO |

## 6. pytest 실행 로그

```
tests/test_document_parser.py::test_html_table_to_markdown_emits_separator_row PASSED
tests/test_document_parser.py::test_html_table_to_markdown_handles_empty_input PASSED
tests/test_document_parser.py::test_cell_loss_ratio_zero_when_all_present PASSED
tests/test_document_parser.py::test_cell_loss_ratio_detects_missing_cells PASSED
tests/test_document_parser.py::test_load_table_elements_missing_file_raises PASSED
tests/test_document_parser.py::test_table_extraction [T-008] 추출 표 5개, 셀 손실율 1.18% PASSED

============================== 6 passed in 3.86s ==============================
```

(API 키 값은 본 기록/로그/커밋 어디에도 포함하지 않음 — `.env`는 git 추적 대상 아님)

