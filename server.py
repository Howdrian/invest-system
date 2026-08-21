# -*- coding: utf-8 -*-
"""
===================================
Daily Stock Analysis - FastAPI 后端服务入口
===================================

职责：
1. 提供 RESTful API 服务
2. 配置 CORS 跨域支持
3. 健康检查接口
4. 托管前端静态文件（生产模式）

启动方式：
    python server.py

    或使用 main.py:
    python main.py --serve-only      # 仅启动 API 服务
    python main.py --serve           # API 服务 + 执行分析
"""

import logging

from src.config import setup_env, get_config
from src.logging_config import setup_logging

# 初始化环境变量与日志
setup_env()

config = get_config()
level_name = (config.log_level or "INFO").upper()
level = getattr(logging, level_name, logging.INFO)

setup_logging(
    log_prefix="api_server",
    console_level=level,
    extra_quiet_loggers=['uvicorn', 'fastapi'],
)

# 从 api.app 导入应用实例
from api.app import app  # noqa: E402
from src.network_bind_security import (  # noqa: E402
    configure_app_bind_host,
    require_safe_network_bind,
)

# ``uvicorn server:app --host ...`` bypasses the direct-run guard. Record the
# configured intent so request middleware can still fail closed; the ASGI
# request scope supplies the actual local address when CLI ``--host`` differs.
configure_app_bind_host(app, config.webui_host or "127.0.0.1")

# 导出 app 供 uvicorn 使用
__all__ = ['app']


def _resolve_server_bind() -> tuple[str, int]:
    """Resolve the direct-run bind and refuse unsafe network exposure."""

    host = str(config.webui_host or "127.0.0.1").strip()
    port = int(config.webui_port)
    require_safe_network_bind(host)
    return host, port


if __name__ == "__main__":
    import uvicorn

    server_host, server_port = _resolve_server_bind()
    configure_app_bind_host(app, server_host)
    uvicorn.run(
        app,
        host=server_host,
        port=server_port,
        reload=False,
    )
