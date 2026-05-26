"""FastAPI application entry point."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .schemas import AgentRequest, AgentResponse, ErrorResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    settings = get_settings()
    yield
    # Shutdown


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


@app.get("/health")
async def health():
    """Liveness probe."""
    return {"ok": True}


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