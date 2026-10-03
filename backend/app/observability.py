"""轻量就绪检查与不包含请求敏感数据的访问日志。"""
import logging
import re
from time import perf_counter
from uuid import uuid4

from sqlalchemy import text
from starlette.responses import JSONResponse

from app.migrate import HEAD

# 继承 Uvicorn 的日志配置，确保容器默认输出访问记录。
logger = logging.getLogger('uvicorn.error.requests')
_REQUEST_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', re.ASCII)
_METHOD = re.compile(r'[A-Z]{1,16}', re.ASCII)


class SafeServerLogFilter(logging.Filter):
    """Uvicorn 的 WebSocket 握手日志不受 --no-access-log 控制。"""

    def filter(self, record):
        if not record.name.startswith('uvicorn.error') or record.name == logger.name:
            return True
        if getattr(record, '_safe_server_log', False):
            return True
        # 协议 DEBUG/TRACE 会输出请求头、URL 和帧内容，不能安全逐字段清洗。
        if record.levelno < logging.INFO:
            return False
        message = record.getMessage()
        if 'WebSocket' in message:
            record.msg = ('WebSocket handshake accepted' if '[accepted]' in message
                          else 'WebSocket handshake rejected')
            record.args = ()
        elif record.exc_info or '?' in message:
            record.msg = 'Server request failed; details redacted'
            record.args = ()
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        record._safe_server_log = True
        return True


def install_safe_server_logging():
    """在应用导入时安装，早于握手解析及中间件的第一次调用。"""
    server_logger = logging.getLogger('uvicorn.error')
    if not any(isinstance(item, SafeServerLogFilter) for item in server_logger.filters):
        server_logger.addFilter(SafeServerLogFilter())
    # Logger 过滤器不处理子 logger 的传播记录，输出 handler 也必须过滤。
    current = server_logger
    while current is not None:
        for handler in current.handlers:
            if not any(isinstance(item, SafeServerLogFilter) for item in handler.filters):
                handler.addFilter(SafeServerLogFilter())
        if not current.propagate:
            break
        current = current.parent


def database_ready(engine):
    """仅检查连接及迁移版本；完整结构校验仍在启动时执行。"""
    try:
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
            versions = connection.execute(
                text('SELECT version_num FROM alembic_version')).scalars().fetchmany(2)
            return versions == [HEAD]
    except Exception:  # noqa: BLE001 - readiness must not expose connection details
        # 连接异常可能包含数据库用户名、密码或内部地址。
        return False


class RequestLoggingMiddleware:
    """仅记录受限 ID 和路由模板，禁止 query、请求体与异常详情。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        supplied = [value.decode('latin-1') for key, value in scope['headers']
                    if key.lower() == b'x-request-id']
        request_id = (supplied[0] if len(supplied) == 1 and _REQUEST_ID.fullmatch(supplied[0])
                      else str(uuid4()))
        scope.setdefault('state', {})['request_id'] = request_id
        started = perf_counter()
        status = 500
        response_started = False

        async def send_with_id(message):
            nonlocal status, response_started
            if message['type'] == 'http.response.start':
                status = message['status']
                response_started = True
                headers = [(key, value) for key, value in message.get('headers', [])
                           if key.lower() != b'x-request-id']
                headers.append((b'x-request-id', request_id.encode('ascii')))
                message = {**message, 'headers': headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception:  # noqa: BLE001 - sanitize the HTTP boundary before server logging
            status = 500
            if response_started:
                # 已开始的响应不可重写；让服务器终止流，但不泄漏原始异常。
                raise RuntimeError('Request failed after response started') from None
            await JSONResponse({'detail': 'Internal server error'}, status_code=500)(
                scope, receive, send_with_id)
        finally:
            route = scope.get('route')
            path = getattr(route, 'path', '<unmatched>')
            method = scope.get('method', '')
            method = method if _METHOD.fullmatch(method) else 'OTHER'
            duration_ms = round((perf_counter() - started) * 1000, 3)
            logger.info('request_id=%s method=%s path=%s status=%s duration_ms=%.3f',
                        request_id, method, path, status, duration_ms,
                        extra={'request_id': request_id, 'method': method, 'path': path,
                               'status': status, 'duration_ms': duration_ms})
