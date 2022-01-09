"""Historic weather sensor platform."""
from __future__ import annotations

import logging
import re
import datetime
import pytz

from typing import Any, Callable, Dict, Optional
from urllib import parse

import json
# import re
import voluptuous as vol

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    TEMP_CELSIUS,
    PERCENTAGE,
    PRESSURE_MBAR,
    SPEED_KILOMETERS_PER_HOUR
)
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import (
    ConfigType,
    DiscoveryInfoType,
)
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_TEMPERATURE,
    ATTR_HUMIDITY,
    ATTR_WINDSPEED,
    ATTR_PRESSURE,
    ATTR_CONDITION,
    BASE_URL,
    DOMAIN,
    CONF_LOCATION,
    CONF_OFFSET_DAYS,
    CONF_OFFSET_HOURS,
    CONF_FILENAME
)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = datetime.timedelta(minutes=2)

SENSORS = [
    (SensorEntityDescription(
        key=ATTR_TEMPERATURE,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=TEMP_CELSIUS,
        name="Temperature"
    ),"mdi:thermometer"),
    (SensorEntityDescription(
        key=ATTR_HUMIDITY,
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        name="Humidity",
    ),"mdi:water-percent"),
    (SensorEntityDescription(
        key=ATTR_WINDSPEED,
        native_unit_of_measurement=SPEED_KILOMETERS_PER_HOUR,
        name="Windspeed",
    ),"mdi:windsock"),
    (SensorEntityDescription(
        key=ATTR_PRESSURE,
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=PRESSURE_MBAR,
        name="Air Pressure",
    ),"mdi:weather-cloudy"),
    (SensorEntityDescription(
        key=ATTR_CONDITION,
        name="Condition",
    ),"mdi:weather-cloudy"),
]

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_LOCATION): cv.string,
        vol.Required(CONF_FILENAME): cv.string,
        vol.Required(CONF_OFFSET_DAYS): cv.positive_int,
        vol.Optional(CONF_OFFSET_HOURS): cv.positive_int,
    }
)

async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the sensor platform."""

    # coordinator: DataUpdateCoordinator = hass.data[DOMAIN][config.entry_id]
    location = config[CONF_LOCATION]
    offset_days = config[CONF_OFFSET_DAYS]
    timezone = hass.config.time_zone


    weather = HistoricWeatherParser(config[CONF_FILENAME], timezone, offset_days, config[CONF_OFFSET_HOURS])

    entities = [HistoricWeatherSensor(weather, location, offset_days, sensor, icon) for (sensor, icon) in SENSORS]
    async_add_entities(entities, update_before_add=True)

class HistoricWeatherParser():
    def __init__(self, filename, timezone, offset_days, offset_hours):
        rawdata = open(filename, 'r').read()
        self._timezone = dt_util.get_time_zone(timezone)
        _LOGGER.warning(f'timezone {self._timezone}')
        self._offset_days = offset_days
        self._offset_hours = offset_hours

        now = dt_util.now()
        start_datetime = now - datetime.timedelta(days=offset_days)
        start_date_str = start_datetime.strftime("%Y-%m-%d")
        start_pos = rawdata.find(start_date_str) - 1
        rest_year_data = "{\n" + rawdata[start_pos:]

        self._structured_data = json.loads(rest_year_data)
        self._current_values = {}
        self._current_timestamp = None

    def update_current_value(self):
        new_values = {}
        now = dt_util.now()
        now = datetime.datetime.replace(now, second=0, microsecond=0)
        if self._current_timestamp == now:
            return

        start_datetime = now - datetime.timedelta(days=self._offset_days, hours=self._offset_hours)

        for timestamp, values in self._structured_data.items():
            date_time_obj = datetime.datetime.replace((datetime.datetime.strptime(timestamp, "%Y-%m-%d %H:%M")),tzinfo=self._timezone)
            if date_time_obj > start_datetime:
                new_values = {
                    ATTR_TEMPERATURE: values[0],
                    ATTR_HUMIDITY: values[1],
                    ATTR_WINDSPEED: values[2],
                    ATTR_PRESSURE: values[3],
                    ATTR_CONDITION: values[4],
                }
                break

        self._current_timestamp = now
        if new_values != self._current_values:
            self._current_values = new_values
            _LOGGER.warning(f'on {start_datetime.strftime("%Y-%m-%d %H:%M")} {self._current_values}')

    @property
    def temperature(self) -> int:
        return self._current_values[ATTR_TEMPERATURE]

    @property
    def humidity(self) -> int:
        return self._current_values[ATTR_HUMIDITY]

    @property
    def windspeed(self) -> int:
        return self._current_values[ATTR_WINDSPEED]

    @property
    def pressure(self) -> int:
        return self._current_values[ATTR_PRESSURE]

    @property
    def condition(self) -> int:
        return self._current_values[ATTR_CONDITION]

class HistoricWeatherSensor(SensorEntity):
    """Representation of a historic weather data sensor."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, weather, location, offset_days, entity_description, icon):
        super().__init__()
        self._entity_description = entity_description
        self._weather = weather
        self._location = location
        self._offset_days = offset_days
        self._name = f"{entity_description.key} in {location}, {offset_days} days ago"
        self._available = True
        self._icon = icon

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._name

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available

    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return f"historic_{self._entity_description.key}_{self._location}-{self._offset_days}"

    @property
    def native_unit_of_measurement(self):
        return self._entity_description.native_unit_of_measurement

    @property
    def native_value(self):
        """Return the value reported by the sensor."""
        return getattr(self._weather, self._entity_description.key)

    @property
    def icon(self):
        return self._icon

    async def async_update(self):
        self._weather.update_current_value()
