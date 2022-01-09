DOMAIN = "historic_weather"
BASE_URL = "https://www.timeanddate.com/scripts/cityajax.php?mode=historic&json=1"

ATTR_TEMPERATURE = "temperature"
ATTR_HUMIDITY = "humidity"
ATTR_WINDSPEED = "windspeed"
ATTR_PRESSURE = "pressure"
ATTR_CONDITION = "condition"
ATTR_RAIN = "rain"
ATTR_SKY = "sky"
ATTR_MOON = "moon"

CONF_LOCATION = "location"
CONF_OFFSET_DAYS = "offset_days"
CONF_OFFSET_HOURS = "offset_hours"
CONF_FILENAME = "filename"

condition = "cloudy"
res = {}
RAIN_DICT = {"drizzle": 1, "light rain": 2, "showers": 3, "heavy rain": 5, "rain.": 4, "": 0}

for keyword, value in RAIN_DICT.items():
    if keyword in condition:
        res[ATTR_RAIN] = value
        break

print(res)

