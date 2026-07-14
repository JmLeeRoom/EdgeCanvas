"""T-851: FastAPI 백엔드 — 에이전트 통합 제어 REST API.

POST /api/run, GET /api/status/{run_id}, GET /api/report/{run_id} 및
BackgroundTasks + 세마포어 순차 큐로 LangGraph 오케스트레이터를 비동기 기동한다.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.agent.orchestrator import build_orchestrator_graph, initial_state
from src.common.run_manager import create_run_dirs, generate_run_id

RunStatus = Literal["queued", "running", "completed", "failed"]
RunMode = Literal["sim", "hw"]

DEFAULT_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8501",
    "http://127.0.0.1:8501",
]


class RunRequest(BaseModel):
    pdf_path: str = Field(..., description="데이터시트 PDF 절대/상대 경로")
    spec_path: str = Field(..., description="UI 요구사항 텍스트 파일 경로")
    target: str = Field("esp32-p4", description="타깃 보드명")
    mode: RunMode = Field("sim", description="sim 또는 hw")


class ErrorBody(BaseModel):
    code: str
    message: str


class RunStartResponse(BaseModel):
    ok: bool
    run_id: str
    status: RunStatus
    error: ErrorBody | None = None


class HealthResponse(BaseModel):
    status: str = "healthy"


class StatusResponse(BaseModel):
    run_id: str
    status: RunStatus
    current_node: str | None = None
    verdict: str | None = None
    error: ErrorBody | None = None


class ReportResponse(BaseModel):
    run_id: str
    report_markdown: str
    found: bool


PipelineRunner = Callable[[RunRequest, str, Path], dict[str, Any]]


@dataclass
class RunRecord:
    run_id: str
    status: RunStatus
    mode: RunMode
    current_node: str | None = None
    verdict: str | None = None
    error: ErrorBody | None = None
    report_path: str | None = None


class RunRegistry:
    """In-memory run 상태 저장소 + 단일 실행 세마포어(보드 플래시 임계 구역)."""

    def __init__(self) -> None:
        self._records: dict[str, RunRecord] = {}
        self._lock = threading.Lock()
        self._semaphore = threading.Semaphore(1)

    def create(self, run_id: str, mode: RunMode) -> RunRecord:
        record = RunRecord(run_id=run_id, status="queued", mode=mode)
        with self._lock:
            self._records[run_id] = record
        return record

    def get(self, run_id: str) -> RunRecord | None:
        with self._lock:
            return self._records.get(run_id)

    def update(self, run_id: str, **fields: Any) -> None:
        with self._lock:
            record = self._records.get(run_id)
            if record is None:
                return
            for key, value in fields.items():
                setattr(record, key, value)

    def execute_guarded(
        self,
        run_id: str,
        request: RunRequest,
        output_dir: Path,
        runner: PipelineRunner,
    ) -> None:
        """세마포어로 한 번에 하나의 파이프라인만 실행한다 (카드 12)."""
        self._semaphore.acquire()
        try:
            self.update(run_id, status="running", current_node="parse_datasheet")
            result = runner(request, run_id, output_dir)
            current_node = "end_pass" if result.get("verdict") == "PASS" else "end_fail"
            history = result.get("history") or []
            if history:
                last = history[-1]
                if isinstance(last, dict):
                    current_node = str(last.get("node", current_node))
            self.update(
                run_id,
                status="completed",
                current_node=current_node,
                verdict=result.get("verdict"),
                report_path=result.get("report_path"),
                error=None,
            )
        except Exception as exc:  # noqa: BLE001 — API 계약상 구조화된 실패로 정규화
            self.update(
                run_id,
                status="failed",
                current_node="pipeline_error",
                error=ErrorBody(code="pipeline_error", message=str(exc)),
            )
        finally:
            self._semaphore.release()


def _resolve_output_dir(output_dir: Path | None) -> Path:
    if output_dir is not None:
        return Path(output_dir)
    return Path(os.environ.get("P10_OUTPUT_DIR", "output"))


def default_pipeline_runner(
    request: RunRequest, run_id: str, output_dir: Path
) -> dict[str, Any]:
    """LangGraph 오케스트레이터 sim E2E (T-901 fake adapter 재사용)."""
    from src.agent.report_generator import write_report
    from src.cli.main import build_sim_e2e_mocks

    pdf = Path(request.pdf_path)
    spec = Path(request.spec_path)
    if not pdf.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf}")
    if not spec.is_file():
        raise FileNotFoundError(f"Spec not found: {spec}")

    create_run_dirs(run_id, output_dir)
    mocks = build_sim_e2e_mocks(
        output_dir=output_dir,
        pdf_path=pdf,
        spec_path=spec,
    )
    graph = build_orchestrator_graph(mocks)
    final = graph.invoke(
        initial_state(run_mode=request.mode, run_id=run_id)  # type: ignore[arg-type]
    )

    code = final.get("generated_code") or ""
    if code:
        (output_dir / run_id / "generated_ui_screens.c").write_text(code, encoding="utf-8")

    if not final.get("report_path"):
        report_path = write_report(
            final,
            output_dir=output_dir,
            vision_image_path=final.get("screenshot_path"),
            also_checkpoint=True,
        )
        final["report_path"] = str(report_path)

    return dict(final)


def _record_to_start_response(record: RunRecord) -> RunStartResponse:
    ok = record.status not in ("failed",)
    return RunStartResponse(
        ok=ok,
        run_id=record.run_id,
        status=record.status,
        error=record.error,
    )


def _record_to_status(record: RunRecord) -> StatusResponse:
    return StatusResponse(
        run_id=record.run_id,
        status=record.status,
        current_node=record.current_node,
        verdict=record.verdict,
        error=record.error,
    )


def create_app(
    *,
    output_dir: Path | None = None,
    pipeline_runner: PipelineRunner | None = None,
    run_sync: bool = False,
    cors_origins: list[str] | None = None,
    registry: RunRegistry | None = None,
) -> FastAPI:
    """FastAPI 앱 팩토리. 테스트에서 runner·동기 실행·출력 경로를 주입한다."""
    resolved_output = _resolve_output_dir(output_dir)
    runner = pipeline_runner or default_pipeline_runner
    run_registry = registry or RunRegistry()

    application = FastAPI(
        title="P10 Manufacturing Agent API",
        description="에이전트 파이프라인 원격 제어 및 상태 모니터링 REST API (T-851)",
        version="0.1.0",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or DEFAULT_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    def _schedule_run(
        background: BackgroundTasks,
        run_id: str,
        request: RunRequest,
    ) -> RunStartResponse:
        run_registry.create(run_id, request.mode)

        def task() -> None:
            run_registry.execute_guarded(run_id, request, resolved_output, runner)

        if run_sync:
            task()
        else:
            background.add_task(task)

        record = run_registry.get(run_id)
        assert record is not None
        return _record_to_start_response(record)

    @application.get("/api/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse()

    @application.post("/api/run", response_model=RunStartResponse, tags=["pipeline"])
    def start_run(
        request: RunRequest,
        background_tasks: BackgroundTasks,
    ) -> RunStartResponse:
        run_id = generate_run_id()
        create_run_dirs(run_id, resolved_output)
        return _schedule_run(background_tasks, run_id, request)

    @application.get(
        "/api/status/{run_id}",
        response_model=StatusResponse,
        tags=["pipeline"],
    )
    def get_status(run_id: str) -> StatusResponse:
        record = run_registry.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"run_id not found: {run_id}")
        return _record_to_status(record)

    @application.get(
        "/api/report/{run_id}",
        response_model=ReportResponse,
        tags=["pipeline"],
    )
    def get_report(run_id: str) -> ReportResponse:
        report_path = resolved_output / run_id / "report.md"
        if not report_path.is_file():
            return ReportResponse(run_id=run_id, report_markdown="", found=False)
        return ReportResponse(
            run_id=run_id,
            report_markdown=report_path.read_text(encoding="utf-8"),
            found=True,
        )

    application.state.run_registry = run_registry
    application.state.output_dir = resolved_output
    return application


app = create_app()
