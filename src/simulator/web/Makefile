# =============================================================================
# T-850 — Emscripten WebAssembly browser pipeline
#
# Builds lvgl_sim.js + lvgl_sim.wasm for the HTML5 Canvas shell (index.html).
# Requires emsdk (emcc on PATH). Without emsdk, use Python guard in
# src/simulator/wasm_build.py which skips WASM and falls back to SDL2 desktop.
#
# Usage:
#   emmake make -C src/simulator/web
#   # or:
#   make -C src/simulator/web EMCC=emcc
#
# Output: build_web/lvgl_sim.js , build_web/lvgl_sim.wasm
# Serve index.html from this directory (or copy JS/WASM next to it).
# =============================================================================

EMCC      ?= emcc
OUT_DIR   ?= build_web
JS_OUT    := $(OUT_DIR)/lvgl_sim.js
WASM_OUT  := $(OUT_DIR)/lvgl_sim.wasm

SIM_ROOT  := ..
SOURCES   ?= $(SIM_ROOT)/main.c

# Emscripten SDL2 port — matches desktop 1024x600 target conceptually.
# Full LVGL link needs LVGL sources/includes on the include path (see README).
EMFLAGS = \
	-O2 \
	-sUSE_SDL=2 \
	-sALLOW_MEMORY_GROWTH=1 \
	-sEXPORTED_RUNTIME_METHODS=ccall,cwrap \
	-sFORCE_FILESYSTEM=0

.PHONY: all clean help

all: $(JS_OUT)

$(JS_OUT): $(SOURCES)
	@mkdir -p $(OUT_DIR)
	$(EMCC) $(SOURCES) $(EMFLAGS) -o $(JS_OUT)
	@echo "Built $(JS_OUT) (+ $(WASM_OUT) when emitted by emcc)"

clean:
	rm -rf $(OUT_DIR)

help:
	@echo "T-850 WASM targets:"
	@echo "  make / make all  -> $(JS_OUT)"
	@echo "  make clean       -> remove $(OUT_DIR)"
	@echo "Requires: emsdk activated (emcc on PATH). See README.md"
