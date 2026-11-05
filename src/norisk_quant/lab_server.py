"""Local, authenticated control surface for the unified research coordinator.

This module never reads arbitrary paths or starts market jobs by itself. The
coordinator validates submitted specifications and owns execution policy.
"""
from __future__ import annotations

import hmac
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
import threading
from urllib.parse import urlsplit

MAX_BODY_BYTES = 65_536
_JOB_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("Nonfinite JSON number")


class LabHTTPServer(ThreadingHTTPServer):
    """Threaded loopback server with one explicit worker tick at a time."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, coordinator, *, host="127.0.0.1", port=0, token=None):
        if host != "127.0.0.1":
            raise ValueError("Quantum Lab binds to IPv4 loopback only")
        if type(port) is not int or not 0 <= port <= 65535:
            raise ValueError("Invalid local port")
        if token is not None and (type(token) is not str or len(token) < 32):
            raise ValueError("Mutation token must contain at least 32 characters")
        self.coordinator = coordinator
        self.mutation_token = token or secrets.token_urlsafe(32)
        self.worker_lock = threading.Lock()
        super().__init__((host, port), LabRequestHandler)
        actual_port = self.server_address[1]
        self.allowed_hosts = {f"127.0.0.1:{actual_port}", f"localhost:{actual_port}"}
        self.allowed_origins = {f"http://{host}" for host in self.allowed_hosts}

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server_address[1]}"


class LabRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "NRFXLocalLab"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, format, *args):
        # No request targets, tokens, private paths or submitted data in logs.
        return

    def _headers(self, status, length, *, content_type="application/json; charset=utf-8", nonce=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        script_policy = f"'nonce-{nonce}'" if nonce else "'none'"
        self.send_header("Content-Security-Policy", "default-src 'none'; "
                         f"script-src {script_policy}; style-src 'unsafe-inline'; "
                         "connect-src 'self'; img-src 'self' data:; base-uri 'none'; "
                         "form-action 'none'; frame-ancestors 'none'")
        self.end_headers()

    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self._headers(status, len(body))
        self.wfile.write(body)

    def _error(self, status, code):
        self.close_connection = True
        self._json(status, {"error": code})

    def _valid_host(self):
        hosts = self.headers.get_all("Host", [])
        return len(hosts) == 1 and hosts[0].lower() in self.server.allowed_hosts

    def _authorized(self):
        if not self._valid_host():
            self._error(HTTPStatus.FORBIDDEN, "invalid_host")
            return False
        origins = self.headers.get_all("Origin", [])
        if len(origins) != 1 or origins[0] not in self.server.allowed_origins:
            self._error(HTTPStatus.FORBIDDEN, "invalid_origin")
            return False
        tokens = self.headers.get_all("X-Lab-Token", [])
        if len(tokens) != 1 or not hmac.compare_digest(tokens[0].encode("utf-8"), self.server.mutation_token.encode("utf-8")):
            self._error(HTTPStatus.FORBIDDEN, "invalid_token")
            return False
        return True

    def _path(self):
        parsed = urlsplit(self.path)
        # Absolute request URLs, queries and escapes are unnecessary here.
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or "%" in parsed.path:
            raise ValueError("Invalid route")
        return parsed.path

    def _body(self):
        if self.headers.get("Transfer-Encoding"):
            raise ValueError("Unsupported request encoding")
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1 or not lengths[0].isdigit():
            raise ValueError("A single content length is required")
        size = int(lengths[0])
        if size > MAX_BODY_BYTES:
            raise OverflowError("Request too large")
        if self.headers.get_content_type() != "application/json":
            raise TypeError("JSON required")
        body = self.rfile.read(size)
        if len(body) != size:
            raise ValueError("Incomplete request")
        value = json.loads(body.decode("utf-8"), object_pairs_hook=_unique_object,
                           parse_constant=_reject_constant)
        if type(value) is not dict:
            raise ValueError("JSON object required")
        return value

    def do_GET(self):
        if not self._valid_host():
            self._error(HTTPStatus.FORBIDDEN, "invalid_host")
            return
        try:
            path = self._path()
            if path == "/":
                nonce = secrets.token_urlsafe(24)
                boot = json.dumps({"token": self.server.mutation_token}, ensure_ascii=True).replace("<", "\\u003c")
                # Fixed package resource only; URL never selects a filesystem path.
                template = Path(__file__).with_name("lab_dashboard.html").read_text(encoding="utf-8")
                body = template.replace("__LAB_NONCE__", nonce).replace("__LAB_BOOT__", boot).encode("utf-8")
                self._headers(HTTPStatus.OK, len(body), content_type="text/html; charset=utf-8", nonce=nonce)
                self.wfile.write(body)
            elif path == "/api/status":
                self._json(HTTPStatus.OK, self.server.coordinator.status())
            elif path == "/api/jobs":
                self._json(HTTPStatus.OK, {"jobs": self.server.coordinator.list_jobs()})
            elif path.startswith("/api/jobs/") and _JOB_ID.fullmatch(path[10:]):
                result = self.server.coordinator.job(path[10:])
                if result is None:
                    self._error(HTTPStatus.NOT_FOUND, "job_not_found")
                else:
                    self._json(HTTPStatus.OK, result)
            else:
                self._error(HTTPStatus.NOT_FOUND, "route_not_found")
        except (ValueError, KeyError):
            self._error(HTTPStatus.BAD_REQUEST, "invalid_request")
        except Exception:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "local_service_error")

    def do_POST(self):
        if not self._authorized():
            return
        try:
            path = self._path()
            body = self._body()
            if path == "/api/jobs":
                self._json(HTTPStatus.CREATED, self.server.coordinator.submit(body))
            elif path == "/api/worker/tick":
                if body:
                    raise ValueError("Worker tick accepts no options")
                if not self.server.worker_lock.acquire(blocking=False):
                    self._error(HTTPStatus.CONFLICT, "worker_busy")
                    return
                try:
                    self._json(HTTPStatus.OK, self.server.coordinator.run_one())
                finally:
                    self.server.worker_lock.release()
            elif path.startswith("/api/jobs/") and path.endswith("/cancel"):
                job_id = path[10:-7]
                if body or not _JOB_ID.fullmatch(job_id):
                    raise ValueError("Invalid cancellation")
                result = self.server.coordinator.cancel(job_id)
                if result is None:
                    self._error(HTTPStatus.NOT_FOUND, "job_not_found")
                else:
                    self._json(HTTPStatus.OK, result)
            else:
                self._error(HTTPStatus.NOT_FOUND, "route_not_found")
        except OverflowError:
            self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request_too_large")
        except TypeError:
            self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "json_required")
        except (ValueError, KeyError, UnicodeError):
            self._error(HTTPStatus.BAD_REQUEST, "invalid_request")
        except Exception:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "local_service_error")


def create_server(coordinator, *, host="127.0.0.1", port=0, token=None):
    """Create without serving; caller owns serve_forever and server_close."""
    return LabHTTPServer(coordinator, host=host, port=port, token=token)
