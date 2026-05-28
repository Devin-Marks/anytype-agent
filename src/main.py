"""FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager
from fastapi import APIRouter, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .api import StreamingHandler
from .schemas import AgentRequest, AgentResponse, StreamEventSchema, StreamResponse
from .safety import (
    get_sandbox_manager,
    SandboxState,
    get_health_checker,
    get_security_logger,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """"Application lifespan handler."""
    # Startup
    settings = get_settings()
    
    # Initialize sandbox manager
    sandbox_mgr = get_sandbox_manager()
    
    if not sandbox_mgr.is_available:
        logger.warning(
            "OpenShell not available. Running without sandbox isolation. "
            "This is suitable for local development only."
        )
    else:
        logger.info("Sandbox manager initialized with OpenShell isolation")
    
    yield
    
    # Shutdown
    await sandbox_mgr.stop_sandbox()


app = FastAPI(
    title="Anytype Agent",
    description="LangGraph agent for Anytype API interactions",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware if needed
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

streaming_router = APIRouter(prefix="/stream", tags=["streaming"])


@streaming_router.post("/invoke")
async def stream_invoke(request: AgentRequest, stream: bool = Query(True)):
    """Invoke the agent through streaming SSE or a JSON fallback."""
    from .graph.builder import get_graph

    graph = get_graph()
    handler = StreamingHandler(graph)

    initial_state = {
        "user_request": request.input,
        "space_id": request.space_id,
        "blocked": False,
    }

    config = {}
    if request.thread_id:
        config["configurable"] = {"thread_id": request.thread_id}

    if not stream:
        events = [event async for event in handler.stream_response(initial_state, config=config)]
        output = next(
            (
                event.data["output"]
                for event in reversed(events)
                if event.event_type.value == "output" and "output" in event.data
            ),
            None,
        )
        return StreamResponse(
            events=[
                StreamEventSchema(event=event.event_type.value, data=event.data)
                for event in events
            ],
            output=output,
        )

    return await handler.stream_to_sse(initial_state, config=config)


@streaming_router.get("/events")
async def stream_events(request: Request):
    """Stream agent events using query parameters for EventSource clients."""
    from .graph.builder import get_graph

    input_text = request.query_params.get("input", "")
    thread_id = request.query_params.get("thread_id")
    space_id = request.query_params.get("space_id")

    graph = get_graph()
    handler = StreamingHandler(graph)

    config = {"configurable": {"thread_id": thread_id}} if thread_id else None
    return await handler.stream_to_sse(
        {"user_request": input_text, "space_id": space_id, "blocked": False},
        config=config,
    )


app.include_router(streaming_router)


@app.get("/health")
async def health():
    """Liveness probe."""
    return {"ok": True}



@app.get("/health/sandbox")
async def sandbox_health():
    """Sandbox status endpoint.
    
    Returns the current sandbox state and availability.
    """
    sandbox_mgr = get_sandbox_manager()
    
    return {
        "ok": True,
        "openshell_available": sandbox_mgr.is_available,
        "sandbox_state": sandbox_mgr.state.value,
        "sandbox_name": sandbox_mgr.sandbox_name,
        "isolated": sandbox_mgr.is_available and sandbox_mgr.state == SandboxState.RUNNING,
    }


@app.get("/health/container")
async def container_health():
    """Check container security health.
    
    Runs all health checks to verify OpenShell sandbox security
    is active and functioning correctly.
    
    Returns:
        JSON with health status, message, and check details.
    """
    checker = get_health_checker()
    result = await checker.check()
    
    # Log the health check result
    logger_sec = get_security_logger()
    logger_sec.log_health_check(
        status=result.status.value,
        message=result.message,
        details=result.details,
    )
    
    return {
        "status": result.status.value,
        "message": result.message,
        "checks": result.details,
    }


@app.get("/ready")
async def readiness():
    """Readiness probe - check external dependencies."""
    # TODO: Implement dependency checks
    return {"ready": True}


@app.post("/invoke", response_model=AgentResponse)
async def invoke(request: AgentRequest):
    """Invoke the agent with user input."""
    from .graph.builder import get_graph

    graph = get_graph()

    initial_state = {
        "user_request": request.input,
        "space_id": request.space_id,
        "blocked": False,
    }

    config = {}
    if request.thread_id:
        config["configurable"] = {"thread_id": request.thread_id}

    result = await graph.ainvoke(initial_state, config=config)

    return AgentResponse(
        output=result.get("output"),
        blocked=result.get("blocked", False),
        block_reason=result.get("block_reason"),
        is_error=result.get("is_error", False),
        error_detail=result.get("error_detail"),
        intent=result.get("intent"),
        tool_name=result.get("tool_name"),
    )


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )