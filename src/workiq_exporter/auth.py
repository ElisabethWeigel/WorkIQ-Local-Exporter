from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import msal


WORK_IQ_SCOPE = "api://workiq.svc.cloud.microsoft/WorkIQAgent.Ask"


class AuthenticationError(RuntimeError):
    pass


@dataclass(frozen=True)
class AuthSession:
    access_token: str
    tenant_id: str
    user_oid: str


def authenticate(tenant_id: str, client_id: str) -> AuthSession:
    application = msal.PublicClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
    )
    result: dict[str, Any] | None = None
    accounts = application.get_accounts()
    if accounts:
        result = application.acquire_token_silent([WORK_IQ_SCOPE], account=accounts[0])
    if not result:
        result = application.acquire_token_interactive(scopes=[WORK_IQ_SCOPE])
    access_token = result.get("access_token")
    claims = result.get("id_token_claims") or {}
    resolved_tenant_id = claims.get("tid")
    user_oid = claims.get("oid")
    if not access_token or not resolved_tenant_id or not user_oid:
        detail = result.get("error_description") or result.get("error") or "unknown error"
        raise AuthenticationError(f"Microsoft sign-in failed: {detail}")
    if resolved_tenant_id.lower() != tenant_id.lower():
        raise AuthenticationError("signed-in user belongs to an unexpected tenant")
    return AuthSession(access_token, resolved_tenant_id, user_oid)
