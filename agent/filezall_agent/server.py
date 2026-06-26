from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import parse

from filezall_agent.config import AgentConfig
from filezall_agent.files import AgentFileService
from filezall_agent.resources import AgentResourceService
from filezall_agent import __version__


def create_server(
    config: AgentConfig,
    resource_service: AgentResourceService | None = None,
) -> ThreadingHTTPServer:
    file_service = AgentFileService(config)
    resource_service = resource_service or AgentResourceService()

    class AgentHandler(BaseHTTPRequestHandler):
        server_version = "FileZallAgent/0.1"

        def do_GET(self) -> None:
            if not _authorized(self, config.token):
                _write_json(self, {"error": "unauthorized"}, status=401)
                return
            route = _route(self.path)
            try:
                _handle_get(self, route, file_service, resource_service)
            except Exception as exc:
                _write_json(self, {"error": str(exc)}, status=400)

        def do_POST(self) -> None:
            if not _authorized(self, config.token):
                _write_json(self, {"error": "unauthorized"}, status=401)
                return
            route = _route(self.path)
            try:
                _handle_post(self, route, file_service)
            except Exception as exc:
                _write_json(self, {"error": str(exc)}, status=400)

        def log_message(self, format: str, *args) -> None:
            return

    return ThreadingHTTPServer((config.host, config.port), AgentHandler)


def main() -> int:
    token = os.environ["FILEZALL_AGENT_TOKEN"]
    host = os.environ.get("FILEZALL_AGENT_HOST", "127.0.0.1")
    port = int(os.environ.get("FILEZALL_AGENT_PORT", "8765"))
    root_value = os.environ.get("FILEZALL_AGENT_ROOT")
    root = Path(root_value) if root_value else None
    server = create_server(AgentConfig(token=token, host=host, port=port, root=root))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    return 0


def _handle_get(
    handler: BaseHTTPRequestHandler,
    route: tuple[str, dict[str, list[str]]],
    file_service: AgentFileService,
    resource_service: AgentResourceService,
) -> None:
    path, query = route
    if path == "/health":
        _write_json(handler, {"ok": True, "version": __version__, "api_version": 1})
    elif path == "/resources":
        _write_json(handler, resource_service.resources())
    elif path == "/processes":
        _write_json(handler, resource_service.processes())
    elif path.startswith("/processes/"):
        _write_json(handler, resource_service.process_detail(int(path.rsplit("/", 1)[1])))
    elif path == "/files/list":
        _write_json(handler, {"entries": file_service.list_directory(_query_one(query, "path"))})
    elif path == "/files/size":
        _write_json(handler, file_service.file_size(_query_one(query, "path")))
    elif path == "/download-chunk":
        data = file_service.download_chunk(
            _query_one(query, "path"),
            offset=int(_query_one(query, "offset")),
            size=int(_query_one(query, "size")),
        )
        _write_bytes(handler, data)
    elif path.startswith("/transfers/") and path.endswith("/chunks"):
        transfer_id = path.split("/")[2]
        _write_json(handler, file_service.chunk_status(transfer_id))
    else:
        _write_json(handler, {"error": "not found"}, status=404)


def _handle_post(
    handler: BaseHTTPRequestHandler,
    route: tuple[str, dict[str, list[str]]],
    file_service: AgentFileService,
) -> None:
    path, query = route
    if path == "/files/rename":
        payload = _read_json(handler)
        _write_json(handler, file_service.rename(payload["source"], payload["destination"]))
    elif path == "/files/verify":
        payload = _read_json(handler)
        _write_json(handler, file_service.verify(payload["path"], payload["checksum"]))
    elif path.startswith("/transfers/") and path.endswith("/merge"):
        transfer_id = path.split("/")[2]
        payload = _read_json(handler)
        _write_json(handler, file_service.merge(transfer_id, payload["path"], int(payload["total_size"])))
    elif path.startswith("/transfers/") and "/chunks/" in path:
        parts = path.split("/")
        transfer_id = parts[2]
        index = int(parts[4])
        data = _read_body(handler)
        _write_json(handler, file_service.write_chunk(_query_one(query, "path"), transfer_id, index, data))
    else:
        _write_json(handler, {"error": "not found"}, status=404)


def _authorized(handler: BaseHTTPRequestHandler, token: str) -> bool:
    return handler.headers.get("Authorization") == f"Bearer {token}"


def _route(path: str) -> tuple[str, dict[str, list[str]]]:
    parsed = parse.urlparse(path)
    return parsed.path, parse.parse_qs(parsed.query)


def _query_one(query: dict[str, list[str]], key: str) -> str:
    return query[key][0]


def _read_body(handler: BaseHTTPRequestHandler) -> bytes:
    length = int(handler.headers.get("Content-Length", "0"))
    return handler.rfile.read(length)


def _read_json(handler: BaseHTTPRequestHandler) -> dict:
    return json.loads(_read_body(handler).decode("utf-8"))


def _write_json(handler: BaseHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    data = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _write_bytes(handler: BaseHTTPRequestHandler, data: bytes, status: int = 200) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", "application/octet-stream")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


if __name__ == "__main__":
    raise SystemExit(main())
