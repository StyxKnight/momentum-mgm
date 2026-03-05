import httpx
import os

# Decidim 0.31 GraphQL is public read-only.
# No auth needed for proposal queries — all civic data is public.
# Mutations are not exposed. Writes go through Rails runner (seeder).
DECIDIM_URL = os.getenv("DECIDIM_URL", "https://mgm.styxcore.dev")


async def graphql(query: str, variables: dict = None) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{DECIDIM_URL}/api",
            json={"query": query, "variables": variables or {}},
            timeout=30,
            follow_redirects=True,
        )
        return r.json()
