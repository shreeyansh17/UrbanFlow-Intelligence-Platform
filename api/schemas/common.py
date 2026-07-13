from typing import Any, Optional

from pydantic import BaseModel


class APIResponse(BaseModel):
    success: bool = True
    data: Optional[Any] = None
    message: str = "OK"
    timestamp: str = ""
