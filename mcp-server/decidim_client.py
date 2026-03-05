import httpx
import os

DECIDIM_URL = os.getenv("DECIDIM_URL", "http://localhost:3000")
_token = None


async def _get_token() -> str:
    global _token
    if _token:
        return _token
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{DECIDIM_URL}/api", json={"query": """
            mutation {
              login(input: {
                email: "%s"
                password: "%s"
              }) {
                token
              }
            }
        """ % (os.getenv("DECIDIM_EMAIL"), os.getenv("DECIDIM_PASSWORD"))})
        _token = r.json()["data"]["login"]["token"]
    return _token


async def graphql(query: str, variables: dict = None) -> dict:
    token = await _get_token()
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{DECIDIM_URL}/api",
            json={"query": query, "variables": variables or {}},
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        return r.json()
