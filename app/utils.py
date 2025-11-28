from __future__ import annotations

from fastapi import HTTPException, status

from app.schemas import ErrorBody, ErrorResponse


def error_response(
    code: str,
    message: str,
    http_status: int = status.HTTP_400_BAD_REQUEST,
    retryable: bool | None = None,
):
    body = ErrorResponse(
        error=ErrorBody(code=code, message=message, retryable=retryable)
    )
    raise HTTPException(status_code=http_status, detail=body.model_dump())
