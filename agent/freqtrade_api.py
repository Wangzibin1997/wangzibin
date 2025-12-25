import base64
import os
from dataclasses import dataclass

import httpx


@dataclass
class ApiAuth:
    base_url: str
    username: str
    password: str


def load_api_auth_from_config(config_path: str) -> ApiAuth:
    import json

    cfg = json.loads(open(config_path, encoding="utf-8").read())
    api = cfg.get("api_server") or {}
    host = api.get("listen_ip_address", "127.0.0.1")
    port = int(api.get("listen_port", 18080))
    username = api.get("username", "admin")
    password = api.get("password", "admin")
    return ApiAuth(base_url=f"http://{host}:{port}", username=username, password=password)


def _basic_auth_header(auth: ApiAuth) -> dict:
    token = base64.b64encode(f"{auth.username}:{auth.password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def get_json(auth: ApiAuth, path: str, params: dict | None = None) -> dict:
    url = auth.base_url.rstrip("/") + path
    with httpx.Client(timeout=10.0) as c:
        r = c.get(url, headers=_basic_auth_header(auth), params=params)
        r.raise_for_status()
        return r.json()


def post_json(auth: ApiAuth, path: str, body: dict | None = None) -> dict:
    url = auth.base_url.rstrip("/") + path
    with httpx.Client(timeout=10.0) as c:
        r = c.post(url, headers=_basic_auth_header(auth), json=body or {})
        r.raise_for_status()
        return r.json()
