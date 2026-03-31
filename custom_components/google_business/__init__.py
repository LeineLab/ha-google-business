"""Google Business Profile integration."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.config_entry_oauth2_flow import (
    OAuth2Session,
    async_get_config_entry_implementation,
)

from .api import ACCOUNTS_URL, BUSINESS_INFO_BASE, GoogleBusinessAPI, GoogleBusinessError
from .const import (
    CONF_ENTRY_ID,
    CONF_LOCATION_NAME,
    CTA_TYPE_NONE,
    DOMAIN,
    POST_TYPE_EVENT,
    POST_TYPE_OFFER,
    SERVICE_CREATE_POST,
    SERVICE_DELETE_POST,
    SERVICE_UPDATE_POST,
    SERVICES_REGISTERED,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]
_RESOLVE_RETRY_INTERVAL = 3600  # seconds between Google API calls while waiting for quota approval

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


class GoogleBusinessReviewsCoordinator(DataUpdateCoordinator):
    """Polls the reviews endpoint once per hour."""

    def __init__(self, hass: HomeAssistant, api: GoogleBusinessAPI) -> None:
        super().__init__(hass, _LOGGER, name=f"{DOMAIN}_reviews", update_interval=timedelta(hours=1))
        self.api = api

    async def _async_update_data(self) -> dict:
        try:
            return await self.api.fetch_reviews(page_size=1)
        except GoogleBusinessError as err:
            raise UpdateFailed(str(err)) from err


class GoogleBusinessInfoCoordinator(DataUpdateCoordinator):
    """Polls business info (phone, address, website, status) every 12 hours."""

    def __init__(self, hass: HomeAssistant, api: GoogleBusinessAPI) -> None:
        super().__init__(hass, _LOGGER, name=f"{DOMAIN}_info", update_interval=timedelta(hours=12))
        self.api = api

    async def _async_update_data(self) -> dict:
        try:
            return await self.api.fetch_business_info()
        except GoogleBusinessError as err:
            raise UpdateFailed(str(err)) from err


@dataclass
class GoogleBusinessRuntimeData:
    """Runtime data stored on the config entry."""

    reviews: GoogleBusinessReviewsCoordinator
    info: GoogleBusinessInfoCoordinator


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Google Business Profile component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Google Business Profile from a config entry."""
    implementation = await async_get_config_entry_implementation(hass, entry)
    oauth_session = OAuth2Session(hass, entry, implementation)

    location_name = entry.data.get(CONF_LOCATION_NAME)
    if not location_name:
        location_name = await _resolve_location(hass, entry, oauth_session)
    api = GoogleBusinessAPI(oauth_session, location_name)
    reviews_coordinator = GoogleBusinessReviewsCoordinator(hass, api)
    info_coordinator = GoogleBusinessInfoCoordinator(hass, api)
    await reviews_coordinator.async_refresh()
    await info_coordinator.async_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = api
    entry.runtime_data = GoogleBusinessRuntimeData(reviews=reviews_coordinator, info=info_coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services once across all entries
    if not hass.data[DOMAIN].get(SERVICES_REGISTERED):
        _register_services(hass)
        hass.data[DOMAIN][SERVICES_REGISTERED] = True

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    hass.data[DOMAIN].pop(entry.entry_id, None)
    hass.data[DOMAIN].pop(f"_last_resolve_{entry.entry_id}", None)

    # Unregister services when no entries remain
    remaining = [
        k for k in hass.data[DOMAIN]
        if k not in (SERVICES_REGISTERED,)
    ]
    if not remaining:
        for service in (SERVICE_CREATE_POST, SERVICE_UPDATE_POST, SERVICE_DELETE_POST):
            hass.services.async_remove(DOMAIN, service)
        hass.data[DOMAIN].pop(SERVICES_REGISTERED, None)

    return True


async def _resolve_location(
    hass: HomeAssistant, entry: ConfigEntry, oauth_session: OAuth2Session
) -> str:
    """Fetch and persist the location name for a pending (quota=0) entry."""
    last_key = f"_last_resolve_{entry.entry_id}"
    last_attempt = hass.data[DOMAIN].get(last_key, 0)
    elapsed = time.monotonic() - last_attempt
    if elapsed < _RESOLVE_RETRY_INTERVAL:
        raise ConfigEntryNotReady(
            f"Waiting for API access approval (next check in "
            f"{int(_RESOLVE_RETRY_INTERVAL - elapsed) // 60} min)"
        )
    hass.data[DOMAIN][last_key] = time.monotonic()

    try:
        resp = await oauth_session.async_request("GET", ACCOUNTS_URL)
        if resp.status >= 400:
            text = await resp.text()
            raise ConfigEntryNotReady(f"Cannot fetch accounts ({resp.status}): {text}")
        data = await resp.json()
        accounts = data.get("accounts", [])
        if not accounts:
            raise ConfigEntryNotReady("No Google Business accounts found")

        locations: list[dict] = []
        for account in accounts:
            url = f"{BUSINESS_INFO_BASE}{account['name']}/locations"
            resp = await oauth_session.async_request(
                "GET", url, params={"readMask": "name,title"}
            )
            if resp.status >= 400:
                text = await resp.text()
                raise ConfigEntryNotReady(
                    f"Cannot fetch locations ({resp.status}): {text}"
                )
            loc_data = await resp.json()
            for loc in loc_data.get("locations", []):
                if loc.get("name", "").startswith("locations/"):
                    loc["name"] = f"{account['name']}/{loc['name']}"
                locations.append(loc)

    except ConfigEntryNotReady:
        raise
    except Exception as err:
        raise ConfigEntryNotReady(f"Error resolving location: {err}") from err

    if not locations:
        raise ConfigEntryNotReady("No Google Business locations found")

    if len(locations) > 1:
        _LOGGER.warning(
            "Multiple Google Business locations found; using '%s'. "
            "Re-add the integration to select a different location.",
            locations[0]["name"],
        )

    location = locations[0]
    location_name = location["name"]
    title = location.get("title", location_name)

    hass.config_entries.async_update_entry(
        entry,
        title=title,
        data={**entry.data, CONF_LOCATION_NAME: location_name},
    )
    return location_name


def _get_api(hass: HomeAssistant, config_entry_id: str | None) -> GoogleBusinessAPI:
    """Return the API instance for the given config entry, or the single entry."""
    entries = {
        entry_id: api
        for entry_id, api in hass.data.get(DOMAIN, {}).items()
        if entry_id != SERVICES_REGISTERED
    }

    if config_entry_id:
        if config_entry_id not in entries:
            raise ServiceValidationError(
                f"Config entry '{config_entry_id}' not found for {DOMAIN}."
            )
        return entries[config_entry_id]

    if len(entries) == 1:
        return next(iter(entries.values()))

    raise ServiceValidationError(
        f"Multiple {DOMAIN} entries configured. Specify 'config_entry_id'."
    )


def _register_services(hass: HomeAssistant) -> None:
    """Register the google_business services."""

    async def handle_create_post(call: ServiceCall) -> ServiceResponse:
        api = _get_api(hass, call.data.get(CONF_ENTRY_ID))
        post_data = _build_post_body(call.data)
        try:
            post = await api.create_post(post_data)
        except GoogleBusinessError as err:
            raise ServiceValidationError(str(err)) from err
        return {"post_name": post["name"]}

    async def handle_update_post(call: ServiceCall) -> None:
        api = _get_api(hass, call.data.get(CONF_ENTRY_ID))
        post_name = call.data["post_name"]
        post_data, update_mask = _build_update_body(call.data)
        if not update_mask:
            raise ServiceValidationError("No fields to update were provided.")
        try:
            await api.update_post(post_name, post_data, update_mask)
        except GoogleBusinessError as err:
            raise ServiceValidationError(str(err)) from err

    async def handle_delete_post(call: ServiceCall) -> None:
        api = _get_api(hass, call.data.get(CONF_ENTRY_ID))
        post_name = call.data["post_name"]
        try:
            await api.delete_post(post_name)
        except GoogleBusinessError as err:
            raise ServiceValidationError(str(err)) from err

    hass.services.async_register(
        DOMAIN,
        SERVICE_CREATE_POST,
        handle_create_post,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(DOMAIN, SERVICE_UPDATE_POST, handle_update_post)
    hass.services.async_register(DOMAIN, SERVICE_DELETE_POST, handle_delete_post)


def _build_post_body(data: dict) -> dict:
    """Build a Google Business localPost body from service call data."""
    post_type = data["post_type"].upper()
    body: dict[str, Any] = {
        "topicType": post_type,
        "languageCode": data.get("language_code", "en"),
        "summary": data["summary"],
    }

    cta_type = data.get("call_to_action_type")
    if cta_type and cta_type != CTA_TYPE_NONE:
        cta: dict[str, Any] = {"actionType": cta_type.upper()}
        if url := data.get("call_to_action_url"):
            cta["url"] = url
        body["callToAction"] = cta

    if data.get("post_type") in (POST_TYPE_EVENT, "event"):
        event: dict[str, Any] = {}
        if title := data.get("event_title"):
            event["title"] = title
        start = data.get("event_start")
        end = data.get("event_end")
        if start or end:
            schedule: dict[str, Any] = {}
            if start:
                schedule["startDateTime"] = _datetime_to_api(start)
            if end:
                schedule["endDateTime"] = _datetime_to_api(end)
            event["schedule"] = schedule
        if event:
            body["event"] = event

    if data.get("post_type") == POST_TYPE_OFFER:
        offer: dict[str, Any] = {}
        if code := data.get("coupon_code"):
            offer["couponCode"] = code
        if url := data.get("redeem_online_url"):
            offer["redeemOnlineUrl"] = url
        if terms := data.get("terms_conditions"):
            offer["termsConditions"] = terms
        if offer:
            body["offer"] = offer

    return body


def _build_update_body(data: dict) -> tuple[dict, str]:
    """Build PATCH body and updateMask from service call data."""
    body: dict[str, Any] = {}
    mask_fields: list[str] = []

    if summary := data.get("summary"):
        body["summary"] = summary
        mask_fields.append("summary")

    if lang := data.get("language_code"):
        body["languageCode"] = lang
        mask_fields.append("languageCode")

    cta_type = data.get("call_to_action_type")
    cta_url = data.get("call_to_action_url")
    if cta_type is not None:
        if cta_type == CTA_TYPE_NONE:
            body["callToAction"] = None
        else:
            cta: dict[str, Any] = {"actionType": cta_type.upper()}
            if cta_url:
                cta["url"] = cta_url
            body["callToAction"] = cta
        mask_fields.append("callToAction")

    # Event fields
    event_parts: dict[str, Any] = {}
    if title := data.get("event_title"):
        event_parts["title"] = title
        mask_fields.append("event.title")
    start = data.get("event_start")
    end = data.get("event_end")
    if start or end:
        schedule: dict[str, Any] = {}
        if start:
            schedule["startDateTime"] = _datetime_to_api(start)
        if end:
            schedule["endDateTime"] = _datetime_to_api(end)
        event_parts["schedule"] = schedule
        mask_fields.append("event.schedule")
    if event_parts:
        body["event"] = event_parts

    # Offer fields
    offer_parts: dict[str, Any] = {}
    if code := data.get("coupon_code"):
        offer_parts["couponCode"] = code
        mask_fields.append("offer.couponCode")
    if url := data.get("redeem_online_url"):
        offer_parts["redeemOnlineUrl"] = url
        mask_fields.append("offer.redeemOnlineUrl")
    if terms := data.get("terms_conditions"):
        offer_parts["termsConditions"] = terms
        mask_fields.append("offer.termsConditions")
    if offer_parts:
        body["offer"] = offer_parts

    return body, ",".join(mask_fields)


def _datetime_to_api(dt: Any) -> dict | str:
    """Convert a datetime object to Google API DateTime dict."""
    from datetime import datetime
    if isinstance(dt, datetime):
        return {
            "year": dt.year,
            "month": dt.month,
            "day": dt.day,
            "hours": dt.hour,
            "minutes": dt.minute,
        }
    # Already a string → pass through as-is (best-effort)
    return str(dt)
