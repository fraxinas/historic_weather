# Historic Weather for Home Assistant

(CC) 2022 by Andreas Frisch <github@fraxinas.dev>

## OwO what's this?
**`historic_weather` is a custom component for Home Assistant which provides historic weather readings**

## Usage
* save a historic weather table file using https://github.com/fraxinas/historic_weather_getter
* place the historic weather table file in the config directory (same as your `configuration.yaml`)
* add a definition to your Home Assistant's `configuration.yaml` under `sensor:` following this prototype:
```
  - platform: historic_weather
    location: country/city
    filename: historic_weather_2021.json
    offset_days: 182
    offset_hours: 0
```
* the historic weather data is assumed to have local timezone timestamps of the remote location
* the values `temperature`, `humidity`, `pressure`, `windspeed` and `condition` are then provided as sensors with the IDs in the form of `sensor.value_in_country_city_182_days_ago`
