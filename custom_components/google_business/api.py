"""Async Google Business Profile API wrapper."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
from homeassistant.helpers.config_entry_oauth2_flow import OAuth2Session

_LOGGER = logging.getLogger(__name__)

API_BASE = "https://mybusiness.googleapis.com/v4/"
ACCOUNTS_URL = "https://mybusinessaccountmanagement.googleapis.com/v1/accounts"
BUSINESS_INFO_BASE = "https://mybusinessbusinessinformation.googleapis.com/v1/"


class GoogleBusinessError(Exception):
    """Exception for Google Business API errors."""

    def __init__(self, status: int, message: str) -> None:
        """Initialize error."""
        super().__init__(f"Google Business API error {status}: {message}")
        self.status = status
        self.message = message


class GoogleBusinessAPI:
    """Async wrapper for the Google Business Profile API.

    After setup, uses OAuth2Session for automatic token refresh.
    """

    def __init__(self, oauth_session: OAuth2Session, location_name: str) -> None:
        """Initialize with an OAuth2Session and location resource name."""
        self._session = oauth_session
        self.location_name = location_name

    async def _request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> Any:
        """Make an authenticated request via the OAuth2Session."""
        resp = await self._session.async_request(method, url, **kwargs)
        if resp.status >= 400:
            text = await resp.text()
            raise GoogleBusinessError(resp.status, text)
        if resp.status == 204:
            return None
        return await resp.json()

    # ------------------------------------------------------------------
    # Setup-time helpers (called from config_flow with raw aiohttp session)
    # ------------------------------------------------------------------

    @staticmethod
    async def fetch_accounts(
        http_session: aiohttp.ClientSession, token: str
    ) -> list[dict]:
        """Fetch all accounts for the authenticated user."""
        headers = {"Authorization": f"Bearer {token}"}
        async with http_session.get(ACCOUNTS_URL, headers=headers) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise GoogleBusinessError(resp.status, text)
            data = await resp.json()
        return data.get("accounts", [])

    @staticmethod
    async def fetch_locations(
        http_session: aiohttp.ClientSession, token: str, account_name: str
    ) -> list[dict]:
        """Fetch all locations for a given account."""
        url = f"{BUSINESS_INFO_BASE}{account_name}/locations"
        headers = {"Authorization": f"Bearer {token}"}
        params = {"readMask": "name,title"}
        async with http_session.get(url, headers=headers, params=params) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise GoogleBusinessError(resp.status, text)
            data = await resp.json()
        locations = data.get("locations", [])
        # Business Information API v1 returns short names ("locations/{id}").
        # Reconstruct the full resource path needed by the v4 posts API.
        for loc in locations:
            if loc.get("name", "").startswith("locations/"):
                loc["name"] = f"{account_name}/{loc['name']}"
        return locations

    # ------------------------------------------------------------------
    # Post CRUD operations
    # ------------------------------------------------------------------

    async def list_posts(self) -> list[dict]:
        """List all local posts for the configured location."""
        url = f"{API_BASE}{self.location_name}/localPosts"
        data = await self._request("GET", url)
        return (data or {}).get("localPosts", [])

    async def create_post(self, post_data: dict) -> dict:
        """Create a local post. Returns the created post resource."""
        url = f"{API_BASE}{self.location_name}/localPosts"
        return await self._request("POST", url, json=post_data)

    async def update_post(self, post_name: str, post_data: dict, update_mask: str) -> dict:
        """Update an existing post using PATCH with updateMask."""
        url = f"{API_BASE}{post_name}"
        params = {"updateMask": update_mask}
        return await self._request("PATCH", url, json=post_data, params=params)

    async def delete_post(self, post_name: str) -> None:
        """Delete a local post by its resource name."""
        url = f"{API_BASE}{post_name}"
        await self._request("DELETE", url)
