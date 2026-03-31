"""OAuth2 config flow for Google Business Profile."""
from __future__ import annotations

import json
import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.config_entry_oauth2_flow import AbstractOAuth2FlowHandler

from .api import GoogleBusinessAPI, GoogleBusinessError
from .const import CONF_LOCATION_NAME, DOMAIN, OAUTH_SCOPE

_LOGGER = logging.getLogger(__name__)


class OAuth2FlowHandler(AbstractOAuth2FlowHandler, domain=DOMAIN):
    """Handle the Google Business Profile OAuth2 config flow."""

    VERSION = 1
    DOMAIN = DOMAIN

    def __init__(self) -> None:
        """Initialize flow."""
        super().__init__()
        self._locations: list[dict] = []
        self._oauth_data: dict = {}

    @property
    def logger(self) -> logging.Logger:
        """Return logger."""
        return _LOGGER

    @property
    def extra_authorize_data(self) -> dict:
        """Extra parameters to include in the authorization request."""
        return {
            "scope": OAUTH_SCOPE,
            "access_type": "offline",
            "prompt": "consent",
        }

    async def async_oauth_create_entry(self, data: dict) -> Any:
        """Handle completion of the OAuth flow — fetch locations."""
        token = data["token"]["access_token"]

        try:
            async with aiohttp.ClientSession() as session:
                accounts = await GoogleBusinessAPI.fetch_accounts(session, token)
                if not accounts:
                    return self.async_abort(reason="no_locations")

                locations: list[dict] = []
                for account in accounts:
                    account_name = account["name"]
                    locs = await GoogleBusinessAPI.fetch_locations(
                        session, token, account_name
                    )
                    locations.extend(locs)

        except GoogleBusinessError as err:
            _LOGGER.error(
                "Failed to fetch locations (HTTP %s): %s",
                err.status,
                err.message,
            )
            if err.status == 429 and _is_quota_zero(err.message):
                self._oauth_data = data
                return await self.async_step_api_access_pending()
            if err.status == 403 and (
                activation_url := _get_service_disabled_url(err.message)
            ):
                return self.async_abort(
                    reason="api_not_enabled",
                    description_placeholders={"activation_url": activation_url},
                )
            return self.async_abort(reason="cannot_fetch_locations")

        if not locations:
            return self.async_abort(reason="no_locations")

        if len(locations) == 1:
            location = locations[0]
            return self._create_entry(data, location["name"], location.get("title", location["name"]))

        # Multiple locations → let user pick
        self._locations = locations
        self._oauth_data = data
        return await self.async_step_select_location()

    async def async_step_api_access_pending(
        self, user_input: dict | None = None
    ) -> Any:
        """Show info about pending API access and let user add the entry anyway."""
        if user_input is None:
            return self.async_show_form(
                step_id="api_access_pending",
                description_placeholders={
                    "api_access_url": "https://support.google.com/business/contact/api_default"
                },
            )
        return self.async_create_entry(
            title="Google Business Profile (pending)",
            data=self._oauth_data,
        )

    async def async_step_select_location(
        self, user_input: dict | None = None
    ) -> Any:
        """Step to select a location when multiple are available."""
        if user_input is not None:
            location_name = user_input[CONF_LOCATION_NAME]
            # Find the display title
            title = next(
                (loc.get("title", location_name) for loc in self._locations if loc["name"] == location_name),
                location_name,
            )
            return self._create_entry(self._oauth_data, location_name, title)

        location_options = {
            loc["name"]: loc.get("title", loc["name"]) for loc in self._locations
        }

        return self.async_show_form(
            step_id="select_location",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_LOCATION_NAME): vol.In(location_options),
                }
            ),
        )

    def _create_entry(self, oauth_data: dict, location_name: str, title: str) -> Any:
        """Create the config entry with location information."""
        # Check for existing entry with same location
        existing_entries = self._async_current_entries()
        for entry in existing_entries:
            if entry.data.get(CONF_LOCATION_NAME) == location_name:
                return self.async_abort(reason="already_configured")

        return self.async_create_entry(
            title=title,
            data={**oauth_data, CONF_LOCATION_NAME: location_name},
        )

    async def async_step_reauth(self, entry_data: dict) -> Any:
        """Handle re-authentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict | None = None
    ) -> Any:
        """Confirm re-authentication."""
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")
        return await self.async_step_user()

    async def async_oauth_create_entry_reauth(
        self, data: dict, existing_entry: ConfigEntry
    ) -> Any:
        """Handle re-auth completion — update existing entry."""
        self.hass.config_entries.async_update_entry(
            existing_entry,
            data={**existing_entry.data, **data},
        )
        await self.hass.config_entries.async_reload(existing_entry.entry_id)
        return self.async_abort(reason="reauth_successful")


def _get_service_disabled_url(message: str) -> str | None:
    """Return the activation URL if the error indicates a disabled API service."""
    try:
        data = json.loads(message)
        for detail in data.get("error", {}).get("details", []):
            if (
                detail.get("@type") == "type.googleapis.com/google.rpc.ErrorInfo"
                and detail.get("reason") == "SERVICE_DISABLED"
            ):
                return detail.get("metadata", {}).get("activationUrl") or (
                    "https://console.cloud.google.com/apis/library/mybusiness.googleapis.com"
                )
    except (json.JSONDecodeError, AttributeError):
        pass
    return None


def _is_quota_zero(message: str) -> bool:
    """Return True when the 429 error indicates quota_limit_value=0 (API access not yet approved)."""
    try:
        data = json.loads(message)
        for detail in data.get("error", {}).get("details", []):
            if (
                detail.get("@type") == "type.googleapis.com/google.rpc.ErrorInfo"
                and detail.get("metadata", {}).get("quota_limit_value") == "0"
            ):
                return True
    except (json.JSONDecodeError, AttributeError):
        pass
    return False
