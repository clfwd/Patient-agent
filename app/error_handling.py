"""Shared error helpers for Agent and MCP entrypoints."""

from fastapi import HTTPException


ERROR_STATUS_CODES = {
    "bad_request": 400,
    "invalid_tool_arguments": 400,
    "identity_verification_required": 403,
    "identity_verification_failed": 403,
    "patient_context_mismatch": 403,
    "patient_not_found": 404,
    "session_not_found": 404,
    "tool_not_found": 404,
    "image_not_found": 404,
    "tool_execution_failed": 502,
}


def status_code_for_error(error_code, default=400):
    return ERROR_STATUS_CODES.get(error_code, default)


def build_api_error(detail, error_code="bad_request", retryable=False, verification_required=False, extra=None):
    return {
        "code": error_code or "bad_request",
        "message": detail,
        "retryable": bool(retryable),
        "verification_required": bool(verification_required),
        "extra": extra or {},
    }


class ServiceError(Exception):
    """Structured application error with a stable internal error code."""

    def __init__(self, detail, error_code="bad_request", status_code=None):
        super(ServiceError, self).__init__(detail)
        self.detail = detail
        self.error_code = error_code or "bad_request"
        self.status_code = status_code or status_code_for_error(self.error_code)

    def __str__(self):
        return self.detail


def raise_http_for_service_error(exc):
    raise HTTPException(
        status_code=exc.status_code,
        detail=exc.detail,
        headers={
            "X-Error-Code": exc.error_code,
            "X-Retryable": "true" if exc.status_code >= 500 else "false",
            "X-Verification-Required": "true"
            if exc.error_code in ("identity_verification_required", "identity_verification_failed")
            else "false",
        },
    )


def raise_http_for_mcp_result(result):
    error_code = result.get("error") or "bad_request"
    verification = result.get("verification") or {}
    detail = result.get("detail") or verification.get("message") or error_code
    raise HTTPException(
        status_code=status_code_for_error(error_code),
        detail=detail,
        headers={
            "X-Error-Code": error_code,
            "X-Retryable": "true" if status_code_for_error(error_code) >= 500 else "false",
            "X-Verification-Required": "true"
            if error_code in ("identity_verification_required", "identity_verification_failed")
            else "false",
        },
    )
