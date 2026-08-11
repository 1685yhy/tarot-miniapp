"""星友圈（SDD P2 · T8-1）的请求/响应模型。

响应合规：零 UGC、零敏感字段——只暴露系统生成的脱敏星名与聚合展示位，
不暴露 openid/nickname/avatar 等真实身份字段。
"""

from pydantic import BaseModel


class AliasResponse(BaseModel):
    """脱敏星名（首次生成落库，此后恒定）。"""

    alias: str
