"""FastAPI routes for the patient agent entrypoint."""

import json
from queue import Queue
from threading import Thread

from fastapi import Depends, Request
from fastapi.responses import StreamingResponse

from app.error_handling import raise_http_for_service_error

from .schemas import AgentInvokeRequest, AgentInvokeResponse
from .service import AgentExecutionError


def register_agent_routes(app):
    """Register agent routes on an existing FastAPI app."""

    def get_agent_service(request: Request):
        return request.app.state.agent_service

    def sse_event(event, data):
        return "event: {0}\ndata: {1}\n\n".format(event, json.dumps(data, ensure_ascii=False, default=str))

    @app.post(
        "/api/v1/agent/invoke",
        response_model=AgentInvokeResponse,
        tags=["Agent"],
        summary="Invoke the patient agent.",
    )
    def invoke_agent(payload: AgentInvokeRequest, agent_service=Depends(get_agent_service)):
        try:
            return agent_service.invoke(payload)
        except AgentExecutionError as exc:
            raise_http_for_service_error(exc)

    @app.post(
        "/api/v1/agent/stream",
        tags=["Agent"],
        summary="Stream patient agent execution events.",
    )
    def stream_agent(payload: AgentInvokeRequest, agent_service=Depends(get_agent_service)):
        def event_stream():
            queue = Queue()
            sentinel = object()

            def publish(event_name, data):
                queue.put(sse_event(event_name, data))

            def worker():
                try:
                    response = agent_service.invoke(payload, event_callback=publish)
                    final_answer = response.get("final_answer") or ""
                    chunk_size = 80
                    for offset in range(0, len(final_answer), chunk_size):
                        publish(
                            "answer.delta",
                            {
                                "run_id": response.get("run_id"),
                                "delta": final_answer[offset : offset + chunk_size],
                            },
                        )
                    publish("answer.done", response)
                    if response.get("audio"):
                        publish("audio.ready", response["audio"])
                except AgentExecutionError as exc:
                    publish(
                        "agent.error",
                        {
                            "code": exc.error_code,
                            "message": exc.detail,
                            "retryable": exc.status_code >= 500,
                            "verification_required": exc.error_code
                            in ("identity_verification_required", "identity_verification_failed"),
                        },
                    )
                except Exception:
                    publish(
                        "agent.error",
                        {
                            "code": "stream_execution_failed",
                            "message": "Agent stream execution failed.",
                            "retryable": True,
                            "verification_required": False,
                        },
                    )
                finally:
                    queue.put(sentinel)

            Thread(target=worker, daemon=True).start()

            while True:
                item = queue.get()
                if item is sentinel:
                    break
                yield item

        return StreamingResponse(event_stream(), media_type="text/event-stream")
