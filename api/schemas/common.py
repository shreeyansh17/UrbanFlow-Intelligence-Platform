from pydantic import BaseModel
from typing import Any, Optional

class APIResponse(BaseModel):
    success: bool = True
    data: Optional[Any] = None
    message: str = "OK"
    timestamp: str = ""
