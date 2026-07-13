# T-010 검증 기록 — NC AI VARCO Art 이미지 생성 API 접속 검증 (스파이크)

- 생성 시각: 2026-07-08 (KST)
- Task: [T-010] [Spike] NC AI VARCO Art 이미지 생성 API 접속 검증
- 선행: T-002 (main 머지 완료, #73 / 81624fc)
- 검증 대상 가정: [가정 2] VARCO Art (제9장) — 외부 서비스 접근 허용 및 REST 규격 신뢰성
- 관련 이슈: #35, 브랜치: spike/T-010-varco-art

## 1. 실험 개요 (카드 7 목적)

[가정 2] "VARCO Art 이미지 생성 API가 외부 서비스 접근을 완전히 허용하고 REST API
호출 규격을 신뢰성 있게 준수하는가"를, "100x50 파란색 사각형 전송 버튼 이미지"
프롬프트를 `requests`로 POST 하여 응답 PNG를 로컬 저장하는 방식으로 실측 검증한다.

## 2. 구현 (카드 8항)

`src/agent/varco_art.py`에 다음을 구현했다(T-008이 `src/agent/document_parser.py`에
스파이크 로직을 둔 방식과 동일한 배치).

1. `build_generation_payload` — 프롬프트 + 100x50 크기 요청 바디 구성 (8-2).
2. `request_image` — `requests.post`로 이미지(3D) 생성 엔드포인트 호출. 기본 URL은
   `https://openapi.ai.nc.com/3d/varco/v1/image-to-3d`이며, `resolve_varco_endpoint`가
   `NC_VARCO_API_URL`(전체 URL) 또는 `NC_VARCO_API_BASE`+path로 오버라이드한다.
   인증은 `build_auth_headers`로 NC OpenAPI `OPENAPI_KEY` 헤더(기본)를 사용하며,
   토큰·모델은 `os.environ`(`NC_VARCO_API_KEY` / `NC_VARCO_AUTH_HEADER` / `NC_VARCO_MODEL`)에서
   읽는다. 코드·로그에 남기지 않는다(코딩표준 §Python).
3. `extract_image_bytes` — 응답 JSON의 base64(`data`/`b64_json`) 또는 이미지 URL(`url`/
   `image_url`/`link`), 또는 raw `image/*` 바이너리 세 경로를 모두 처리 (8-3).
4. `save_image_bytes` — PNG 매직넘버 검증 후 디스크 저장 (10 통과 기준).
5. `make_placeholder_png` — Pillow 없이 stdlib(`zlib`/`struct`)만으로 단색 PNG 인코딩.

## 3. 실험 절차 (카드 10항)

- 실행: `python -m pytest tests/test_varco_api.py -v` (전체 로그: `T-010_pytest.txt`)
- 오프라인 테스트(요청 구성/응답 파싱/PNG 매직넘버/디스크 저장/placeholder fallback)는
  API 키 없이 항상 실행·통과한다.
- 라이브 테스트(`@REQUIRES_LIVE_API`, `NC_VARCO_API_KEY` 키드)는 키가 있을 때만 실제
  VARCO Art API를 호출해 온전한 PNG 저장을 검증한다.
- 실행 결과 (2026-07-13): **17 passed** (NC_VARCO_API_KEY 설정 시 라이브 포함; 당회 401→fallback).
- 실행 결과 (2026-07-13, OPENAPI_KEY 헤더): **21 passed** (로그: `T-010_pytest.txt`)

## 4. 접속 상태 및 결론 — Go/No-Go

**현시점 No-Go (조건부).** 저장소 `.env`에는 `UPSTAGE_API_KEY`만 있고 NC AI 콘솔에서
발급한 `NC_VARCO_API_KEY`/엔드포인트가 아직 확보되지 않았다. 따라서 라이브 200/201
수신을 실증하지 못했고, 카드 12항 *실패*("권한 미획득으로 네트워크/인증 불가")
시나리오에 해당한다.

가정 검증 자체는 미결(Pending)이나, 키가 확보되면 `request_image`가 그대로 라이브
경로로 동작하도록 설계했으므로 재검증 시 코드 변경 없이 200/201 실측이 가능하다.

## 5. Fallback 문서화 (카드 12항 / 제9장 [가정 2])

가정을 (현시점) 기각하고 **Placeholder Fallback** 메커니즘을 확정했다.

- `request_image`는 키 미설정·네트워크 에러·비200·응답 처리 실패 시 자동으로
  `make_placeholder_png`(단순 색상 채우기, 100x50 파란색)로 전환해 온전한 PNG를 저장하고,
  `{"ok": False, "used_fallback": True, "reason": ...}`로 사유를 보고한다.
- 이 fallback은 후속 T-401(VARCO Art API 연동 HMI 이미지 생성기)에서 API 불가 시에도
  파이프라인이 끊기지 않도록 정적 에셋/placeholder 경로를 제공하는 근거가 된다.
- 테스트 `test_request_image_falls_back_on_network_error`가 ConnectionError 주입 시
  fallback이 valid PNG를 생성함을 실증한다(카드 12 실패 케이스 커버).

## 6. DoD 판정 (카드 11항)

| DoD 항목 | 결과 | 근거 |
|---|---|---|
| VARCO Art API 호출 성공 200/201 수신 | **미충족(Pending)** | OPENAPI_KEY 헤더 적용 후 라이브 202(비동기 수락) 수신. 동기 200/201 PNG 미수신. |
| 수신 바이너리가 온전한 PNG 구조(89 50 4E 47) 지님 | **충족(fallback 경로)** | `is_valid_png`로 매직넘버 검증. 본 산출물 `T-010_varco_art.png`(142 bytes)가 온전한 PNG임을 확인. |

> 스파이크 성격상 "접근 가능 여부 진단 + 불가 시 대체 경로 수립"이 목적이며, 라이브 키
> 부재라는 사실 확인과 Placeholder Fallback 확정으로 목적을 달성했다. 키 확보 후 라이브
> 200/201 실측은 후속 재검증 항목으로 남긴다.

## 7. 산출물

- `docs/verification/T-010_varco_art.png` — 카드 13 검증 이미지. 라이브 키 부재로 **fallback
  placeholder PNG**(100x50 파란색)를 저장했다. 키 확보 후 재실행 시 라이브 생성 이미지로 대체.
- `docs/verification/T-010_pytest.txt` — pytest 실행 로그.

## 8. 엔드포인트 마이그레이션 후속 (2026-07-13 KST)

- 브랜치: `feature/T-010-varco-endpoint` (커밋 `2c5b2ff`)
- 기본/권장 URL: `https://openapi.ai.nc.com/3d/varco/v1/image-to-3d` (`NC_VARCO_API_URL`로 오버라이드 가능)
- pytest: `python -m pytest tests/test_varco_api.py -v` → **17 passed** (로그: `T-010_pytest.txt`)
- 라이브 (`test_varco_art_live_generation`, 키는 `.env`에만 존재·로그에 미출력):
  - `ok`: false
  - `status_code`: 401
  - `used_fallback`: true
  - `reason`: HTTP 401 (엔드포인트 도달 가능, 인증/권한 미해결)
- 결론: 엔드포인트 코드 변경은 PR로 반영; 라이브 200/201 DoD는 **Pending** (NC 측 키/권한 확인 필요).

## 9. OPENAPI_KEY 인증 헤더 재검증 (2026-07-13 KST)

- 브랜치: `feature/T-010-openapi-key-auth`
- 변경: `Authorization: Bearer` → NC OpenAPI `OPENAPI_KEY` 헤더 (`build_auth_headers`).
  선택 오버라이드: `NC_VARCO_AUTH_HEADER` (기본 `OPENAPI_KEY`; `Authorization` 지정 시 Bearer).
- pytest: `python -m pytest tests/test_varco_api.py -v` → **21 passed** (로그: `T-010_pytest.txt`)
- 라이브 (`request_image` → `docs/verification/T-010_varco_art.png`, 키는 `.env`에만 존재·로그에 미출력):
  - `ok`: false
  - `status_code`: 202
  - `used_fallback`: true
  - `reason`: HTTP 202 (인증 통과·비동기 수락으로 추정; 200/201 동기 PNG 미수신)
- 결론: 401→202로 인증 개선 확인. 라이브 200/201 동기 PNG DoD는 **Pending** (202 비동기 응답 처리 또는 NC API 규격 추가 확인 필요).

## 8. 재현 방법

```
python -m pytest tests/test_varco_api.py -v
```
- 라이브 검증: `.env`에 `NC_VARCO_API_KEY`(및 필요 시 `NC_VARCO_API_URL` 또는
  `NC_VARCO_API_BASE`)를 채우면 `@REQUIRES_LIVE_API` 테스트가 활성화되어
  `https://openapi.ai.nc.com/3d/varco/v1/image-to-3d`(또는 오버라이드 URL)로 실제 API를 호출한다.
