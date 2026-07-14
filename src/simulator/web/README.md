# T-850 — Emscripten (emsdk) 설치 및 WASM 웹 시뮬

Phase B 선택 확장: LVGL UI를 브라우저 Canvas에서 무설치로 돌려 본다.
emsdk가 없으면 **WASM 빌드는 자동 스킵**되고 PC SDL2 시뮬(T-801/T-802)로 대체한다
(`src/simulator/wasm_build.py`).

## emsdk 설치 (요약)

1. 클론 및 활성화 (Linux / macOS / Git Bash):

```bash
git clone https://github.com/emscripten-core/emsdk.git
cd emsdk
./emsdk install latest
./emsdk activate latest
source ./emsdk_env.sh   # PATH 에 emcc 추가
emcc -v
```

2. Windows (PowerShell):

```powershell
git clone https://github.com/emscripten-core/emsdk.git
cd emsdk
.\emsdk install latest
.\emsdk activate latest
.\emsdk_env.ps1
emcc -v
```

상세: https://emscripten.org/docs/getting_started/downloads.html

## 빌드

```bash
# emsdk 환경 로드 후
emmake make -C src/simulator/web
# 산출물: src/simulator/web/build_web/lvgl_sim.js , lvgl_sim.wasm
```

Python에서:

```python
from src.simulator.wasm_build import build_wasm, WasmBuildOutcome
result = build_wasm()
# result.outcome in {SUCCESS, SKIPPED, FAILED}
```

## 브라우저에서 열기

1. `lvgl_sim.js` / `lvgl_sim.wasm` 을 `index.html` 과 같은 디렉터리로 복사(또는 `build_web`에서 정적 서빙).
2. 로컬 서버로 제공 (file:// 에서는 WASM MIME/`fetch` 제한이 있을 수 있음):

```bash
python -m http.server 8080 --directory src/simulator/web
# http://localhost:8080/index.html
```

정적 서버는 `.wasm` 에 `Content-Type: application/wasm` 을 주어야 한다.

## SDL2 데스크탑 폴백

`emcc`가 PATH에 없으면 `build_wasm()` 은 `SKIPPED` + `fallback="sdl2_desktop"` 을 반환한다.
데스크탑 경로는 `src/simulator/README.md` (CMake + SDL2) 및 `SimDriver`(T-802)를 사용한다.
