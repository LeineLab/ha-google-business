"""Sensor platform for Google Business Profile."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import GoogleBusinessCoordinator
from .const import DOMAIN

_STAR_RATING = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Google Business sensors from a config entry."""
    coordinator: GoogleBusinessCoordinator = entry.runtime_data
    async_add_entities([
        GoogleBusinessAverageRatingSensor(coordinator, entry),
        GoogleBusinessReviewCountSensor(coordinator, entry),
        GoogleBusinessLatestReviewSensor(coordinator, entry),
    ])


class _GoogleBusinessSensor(CoordinatorEntity, SensorEntity):
    """Base sensor for Google Business Profile."""

    def __init__(self, coordinator: GoogleBusinessCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Google",
            model="Business Profile",
        )


class GoogleBusinessAverageRatingSensor(_GoogleBusinessSensor):
    """Average star rating across all reviews."""

    _attr_icon = "mdi:star"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2
    _attr_native_unit_of_measurement = "stars"

    def __init__(self, coordinator: GoogleBusinessCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_name = f"{entry.title} Average Rating"
        self._attr_unique_id = f"{entry.entry_id}_average_rating"

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("averageRating")


class GoogleBusinessReviewCountSensor(_GoogleBusinessSensor):
    """Total number of reviews."""

    _attr_icon = "mdi:star-check"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _attr_native_unit_of_measurement = "reviews"

    def __init__(self, coordinator: GoogleBusinessCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_name = f"{entry.title} Review Count"
        self._attr_unique_id = f"{entry.entry_id}_review_count"

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("totalReviewCount")


class GoogleBusinessLatestReviewSensor(_GoogleBusinessSensor):
    """Star rating of the most recent review, with reviewer details as attributes."""

    _attr_icon = "mdi:account-star"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _attr_native_unit_of_measurement = "stars"

    def __init__(self, coordinator: GoogleBusinessCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_name = f"{entry.title} Latest Review"
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
