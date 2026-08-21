# -*- coding: utf-8 -*-
"""
===================================
WebUI 启动脚本
===================================

用于启动 Web 服务界面。
直接运行 `python webui.py` 将启动 Web 后端服务。

等效命令：
    python main.py --webui-only

Usage:
  python webui.py
  WEBUI_HOST=0.0.0.0 WEBUI_PORT=8000 python webui.py
"""

from __future__ import annotations

import os
import logging

logger = logging.getLogger(__name__)


def _resolve_webui_bind() -> tuple[str, int]:
    """Resolve the legacy WebUI entrypoint bind and apply the shared guard."""
    from src.network_bind_security import require_safe_network_bind

    host = os.getenv("WEBUI_HOST", os.getenv("API_HOST", "127.0.0.1"))
    port = int(os.getenv("WEBUI_PORT", os.getenv("API_PORT", "8000")))
    require_safe_network_bind(host)
    return host, port


def main() -> int:
    """
    启动 Web 服务
    """
    try:
        import uvicorn
        from src.config import setup_env
        from src.logging_config import setup_logging
        from src.network_bind_security import configure_app_bind_host

        setup_env()
        setup_logging(log_prefix="web_server")
        host, port = _resolve_webui_bind()

        from api.app import app as fastapi_app

        configure_app_bind_host(fastapi_app, host)
        print(f"正在启动 Web 服务: http://{host}:{port}")
        print(f"API 文档: http://{host}:{port}/docs")
        print()

        uvicorn.run(
            fastapi_app,
            host=host,
            port=port,
            log_level="info",
        )
    except KeyboardInterrupt:
        pass
    except RuntimeError as exc:
        logger.error("拒绝启动 Web 服务: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
