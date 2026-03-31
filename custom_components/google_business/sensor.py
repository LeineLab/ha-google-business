"""Sensor platform for Google Business Profile."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import GoogleBusinessInfoCoordinator, GoogleBusinessReviewsCoordinator, GoogleBusinessRuntimeData
from .const import DOMAIN

_STAR_RATING = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Google Business sensors from a config entry."""
    data: GoogleBusinessRuntimeData = entry.runtime_data
    async_add_entities([
        GoogleBusinessAverageRatingSensor(data.reviews, entry),
        GoogleBusinessReviewCountSensor(data.reviews, entry),
        GoogleBusinessLatestReviewSensor(data.reviews, entry),
        GoogleBusinessInfoSensor(data.info, entry),
    ])


class _GoogleBusinessSensor(CoordinatorEntity, SensorEntity):
    """Base sensor for Google Business Profile."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Google",
            model="Business Profile",
        )


class GoogleBusinessAverageRatingSensor(_GoogleBusinessSensor):
    """Average star rating across all reviews."""

    _attr_translation_key = "average_rating"
    _attr_icon = "mdi:star"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2
    _attr_native_unit_of_measurement = "stars"

    def __init__(self, coordinator: GoogleBusinessReviewsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_average_rating"

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("averageRating")


class GoogleBusinessReviewCountSensor(_GoogleBusinessSensor):
    """Total number of reviews."""

    _attr_translation_key = "review_count"
    _attr_icon = "mdi:star-check"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _attr_native_unit_of_measurement = "reviews"

    def __init__(self, coordinator: GoogleBusinessReviewsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_review_count"

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("totalReviewCount")


class GoogleBusinessLatestReviewSensor(_GoogleBusinessSensor):
    """Star rating of the most recent review, with reviewer details as attributes."""

    _attr_translation_key = "latest_review"
    _attr_icon = "mdi:account-star"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _attr_native_unit_of_measurement = "stars"

    def __init__(self, coordinator: GoogleBusinessReviewsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_latest_review"

    @property
    def native_value(self) -> int | None:
        reviews = (self.coordinator.data or {}).get("reviews", [])
        if not reviews:
            return None
        return _STAR_RATING.get(reviews[0].get("starRating"))

    @property
    def extra_state_attributes(self) -> dict:
        reviews = (self.coordinator.data or {}).get("reviews", [])
        if not reviews:
            return {}
        review = reviews[0]
        return {
            "reviewer": review.get("reviewer", {}).get("displayName"),
            "comment": review.get("comment"),
            "created": review.get("createTime"),
        }


class GoogleBusinessInfoSensor(_GoogleBusinessSensor):
    """Business status with contact details and address as attributes."""

    _attr_translation_key = "status"
    _attr_icon = "mdi:storefront"

    def __init__(self, coordinator: GoogleBusinessInfoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_status"

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data is None:
            return None
        status = self.coordinator.data.get("openInfo", {}).get("status")
        return status.lower() if status else None

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data or {}
        attrs: dict = {}

        if phone := data.get("phoneNumbers", {}).get("primaryPhone"):
            attrs["phone"] = phone

        if website := data.get("websiteUri"):
            attrs["website"] = website

        if addr := data.get("storefrontAddress"):
            attrs["address"] = _format_address(addr)

        if description := data.get("profile", {}).get("description"):
            attrs["description"] = description

        return attrs


def _format_address(addr: dict) -> str:
    """Format a PostalAddress dict into a readable string."""
    parts = list(addr.get("addressLines", []))
    postal = addr.get("postalCode", "")
    city = addr.get("locality", "")
    if postal or city:
        parts.append(f"{postal} {city}".strip())
    if country := addr.get("regionCode"):
        parts.append(country)
    return ", ".join(p for p in parts if p)
