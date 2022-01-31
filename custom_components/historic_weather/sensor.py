"""Historic weather sensor platform."""
from __future__ import annotations

import logging
import datetime

import ephem
from math import degrees

import json
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
    ATTR_RAIN,
    ATTR_SKY,
    ATTR_MOON,
    CONF_LOCATION,
    CONF_OFFSET_DAYS,
    CONF_OFFSET_HOURS,
    CONF_FILENAME
)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = datetime.timedelta(minutes=2)

SENSORS = {
    ATTR_TEMPERATURE:[SensorEntityDescription(
        key=ATTR_TEMPERATURE,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=TEMP_CELSIUS,
        name="Temperature"
    ),"mdi:thermometer"],
    ATTR_HUMIDITY:[SensorEntityDescription(
        key=ATTR_HUMIDITY,
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        name="Humidity",
    ),"mdi:water-percent"],
    ATTR_WINDSPEED:[SensorEntityDescription(
        key=ATTR_WINDSPEED,
        native_unit_of_measurement=SPEED_KILOMETERS_PER_HOUR,
        name="Windspeed",
    ),"mdi:windsock"],
    ATTR_PRESSURE:[SensorEntityDescription(
        key=ATTR_PRESSURE,
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=PRESSURE_MBAR,
        name="Air Pressure",
    ),"mdi:weather-cloudy"],
    ATTR_CONDITION:[SensorEntityDescription(
        key=ATTR_CONDITION,
        name="Condition",
    ),"mdi:weather-cloudy"],
    ATTR_RAIN:[SensorEntityDescription(
        key=ATTR_RAIN,
        name="Rain",
    ),"mdi:weather-pouring"],
    ATTR_SKY:[SensorEntityDescription(
        key=ATTR_SKY,
        name="Sky (cloudiness)",
    ),"mdi:weather-partly-cloudy"],
    ATTR_MOON:[SensorEntityDescription(
        key=ATTR_MOON,
        native_unit_of_measurement=PERCENTAGE,
        name="Moon illumination",
    ),"mdi:weather-night"],
}

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
    observer = ephem.Observer()
    observer.lat, observer.lon, observer.elevation = hass.config.latitude, hass.config.longitude, hass.config.elevation

    weather = HistoricWeatherParser(config[CONF_FILENAME], timezone, offset_days, config[CONF_OFFSET_HOURS], observer)
    entities = [HistoricWeatherSensor(weather, location, offset_days, sensor) for (sensor, _) in SENSORS.values()]
    async_add_entities(entities, update_before_add=True)

class HistoricWeatherParser():
    def __init__(self, filename, timezone, offset_days, offset_hours, observer):
        rawdata = open(filename, 'r').read()
        self._timezone = dt_util.get_time_zone(timezone)
        self._offset_days = offset_days
        self._offset_hours = offset_hours
        self._observer = observer

        now = dt_util.now()
        start_datetime = now - datetime.timedelta(days=offset_days)
        start_date_str = start_datetime.strftime("%Y-%m-%d")
        start_pos = rawdata.find(start_date_str) - 1
        rest_year_data = "{\n" + rawdata[start_pos:]

        self._structured_data = json.loads(rest_year_data)
        self._current_values = {}
        self._current_timestamp = None

    def parse_condition(self, values):
        condition = values.get(ATTR_CONDITION,"").lower()
        res = {}

        # from https://www.ecobee.com/home/developer/api/documentation/v1/objects/WeatherForecast.shtml
        # we're gonna interpret the numeric value as a correction factor for the daylight intensitiy,
        # the higher the value, the more it will be dimmed down

        # The order on the 2 DICTS is crucial - short substrings must matched last!
        SKY_DICT = {
            "mostly sunny": 3,
            "mostly clear": 4,
            "hazy sunshine": 5,
            "haze": 6,
            "passing clouds": 7,
            "more sun than clouds": 8,
            "scattered clouds": 9,
            "partly cloudy": 10,
            "a mixture of sun and clouds": 11,
            "high level clouds": 12,
            "more clouds than sun": 13,
            "partly sunny": 14,
            "broken clouds": 15,
            "mostly cloudy": 16,
            "cloudy": 17,
            "overcast": 18,
            "low clouds": 19,
            "light fog": 20,
            "dense fog": 22,
            "clear": 2,
            "sunny": 1,
            "fog": 21,
            "thunder": 30,
            "": 0
        }

        RAIN_DICT = {
            "drizzle": 1,
            "light rain": 2,
            "showers": 3,
            "heavy rain": 5,
            "rain.": 4,
            "": 0
        }

        for keyword, value in RAIN_DICT.items():
            if keyword in condition:
                res[ATTR_RAIN] = value
                break

        for keyword, value in SKY_DICT.items():
            if keyword in condition:
                res[ATTR_SKY] = value
                break

        return res

    def calc_moon(self, time):
        self._observer.date = time
        moon = ephem.Moon()
        moon.compute(self._observer)
        next_full = ephem.localtime(ephem.next_full_moon(time)).date()
        next_new = ephem.localtime(ephem.next_new_moon(time)).date()
        next_last_quarter = ephem.localtime(ephem.next_last_quarter_moon(time)).date()
        next_first_quarter = ephem.localtime(ephem.next_first_quarter_moon(time)).date()
        previous_full = ephem.localtime(ephem.previous_full_moon(time)).date()
        previous_new = ephem.localtime(ephem.previous_new_moon(time)).date()
        previous_last_quarter = ephem.localtime(ephem.previous_last_quarter_moon(time)).date()
        previous_first_quarter = ephem.localtime(ephem.previous_first_quarter_moon(time)).date()
        if time in (next_full, previous_full):
            icon = "mdi:moon-full"
        elif time in (next_new, previous_new):
            icon = "mdi:moon-new"
        elif time in (next_first_quarter, previous_first_quarter):
            icon = "mdi:moon-first-quarter"
        elif time in (next_last_quarter, previous_last_quarter):
            icon = "mdi:moon-last-quarter"
        elif previous_new < next_first_quarter < next_full < next_last_quarter < next_new:
            icon = "mdi:moon-waxing-crescent"
        elif previous_first_quarter < next_full < next_last_quarter < next_new < next_first_quarter:
            icon = "mdi:moon-waxing-gibbous"
        elif previous_full < next_last_quarter < next_new < next_first_quarter < next_full:
            icon = "mdi:moon-waning-gibbous"
        elif previous_last_quarter < next_new < next_first_quarter < next_full < next_last_quarter:
            icon = "mdi:moon-waning-crescent"
        SENSORS[ATTR_MOON][1] = icon
        moon_altitude = round(degrees(float(moon.alt)))
        return {ATTR_MOON: round(moon.phase) if moon_altitude > 0 else 0}

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
                for idx, key in enumerate([ATTR_TEMPERATURE, ATTR_HUMIDITY, ATTR_WINDSPEED, ATTR_PRESSURE, ATTR_CONDITION]):
                    new_values[key] = values[idx]
                new_values |= self.parse_condition(new_values)
                break

        self._current_timestamp = now
        new_values |= self.calc_moon(start_datetime)

        if new_values != self._current_values:
            _LOGGER.warning(f'on {start_datetime.strftime("%Y-%m-%d %H:%M")} {new_values}')
            self._current_values = new_values

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

    @property
    def rain(self) -> int:
        return self._current_values[ATTR_RAIN]

    @property
    def sky(self) -> int:
        return self._current_values[ATTR_SKY]

    @property
    def moon(self) -> int:
        return self._current_values[ATTR_MOON]


class HistoricWeatherSensor(SensorEntity):
    """Representation of a historic weather data sensor."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, weather, location, offset_days, entity_description):
        super().__init__()
        self._entity_description = entity_description
        self._weather = weather
        self._location = location
        self._offset_days = offset_days
        self._name = f"{entity_description.key} in {location}, {offset_days} days ago"
        self._available = True

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
        return SENSORS[self._entity_description.key][1]

    async def async_update(self):
        self._weather.update_current_value()
