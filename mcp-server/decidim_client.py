import httpx
import os
import time

DECIDIM_URL = os.getenv("DECIDIM_URL", "https://mgm.styxcore.dev")
API_KEY = os.getenv("DECIDIM_API_KEY")
API_SECRET = os.getenv("DECIDIM_API_SECRET")

_jwt_token = None
_jwt_expires = 0


async def _get_jwt() -> str | None:
    """Sign in with API credentials and return a Bearer JWT. Cached until expiry."""
    global _jwt_token, _jwt_expires
    if _jwt_token and time.time() < _jwt_expires - 60:
        return _jwt_token
    if not API_KEY or not API_SECRET:
        return None
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{DECIDIM_URL}/api/sign_in",
            headers={"Content-Type": "application/x-www-form-urlencoded", "Host": "mgm.styxcore.dev"},
            data={"api_user[key]": API_KEY, "api_user[secret]": API_SECRET},
            timeout=10,
        )
        data = r.json()
        _jwt_token = data.get("jwt_token")
        _jwt_expires = time.time() + 7200
        return _jwt_token


async def graphql(query: str, variables: dict = None, auth: bool = False) -> dict:
    """Execute a GraphQL query. Set auth=True for mutations."""
    headers = {"Content-Type": "application/json", "Host": "mgm.styxcore.dev"}
    if auth:
        token = await _get_jwt()
        if token:
            headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{DECIDIM_URL}/api",
            json={"query": query, "variables": variables or {}},
            headers=headers,
            timeout=30,
            follow_redirects=True,
        )
        return r.json()
