"""领域异常与 HTTP 映射。"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


class DomainError(Exception):
    """业务失败：带稳定代码与可读说明。"""

    def __init__(self, code: str, detail: str = "", status: int = 400):
        super().__init__(detail or code)
        self.code = code
        self.detail = detail or code
        self.status = status


async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status,
        content={"ok": False, "code": exc.code, "detail": exc.detail},
    )


def register(app) -> None:
    app.add_exception_handler(DomainError, domain_error_handler)
