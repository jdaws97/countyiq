"""Provider-neutral account session contract; credentials remain server/edge managed."""

import os
from fastapi import APIRouter, Request, Response
from api.lib.auth import (
    auth_configuration,
    require_identity,
    require_workspace_write,
    login_url,
    optional_identity,
    logout_url,
)
from api.lib.accounts import lookup_account, provision_account
from api.lib.database import get_cursor

router = APIRouter()


def session_payload(identity, account):
    return {
        "authenticated": True,
        "configured": True,
        "user": {
            "id": str(account["user_id"]) if account else None,
            "email": identity.email,
        },
        "workspace_id": str(account["workspace_id"])
        if account and account["workspace_id"]
        else None,
        "sync_enabled": os.environ.get("COUNTYIQ_WATCH_SYNC_ENABLED", "").lower()
        in {"1", "true", "yes", "on"},
        "login_url": login_url(),
        "logout_url": logout_url(),
    }


@router.get("")
def session(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    if auth_configuration() is None:
        return {"authenticated": False, "configured": False, "login_url": login_url()}
    identity = optional_identity(request)
    if identity is None:
        return {"authenticated": False, "configured": True, "login_url": login_url()}
    with get_cursor() as cur:
        return session_payload(identity, lookup_account(cur, identity))


@router.post("")
def initialize(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    identity = require_identity(request)
    require_workspace_write(request)
    with get_cursor(write=True) as cur:
        return session_payload(identity, provision_account(cur, identity))
