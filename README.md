#  Enpal - Home Assistant integration (WiP)


<img src="images/logo.png" alt="enpal logo" width="512">

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/release/skipperro/enpal-homeassistant.svg)](https://GitHub.com/skipperro/enpal-homeassistant/releases/)
![](https://img.shields.io/badge/dynamic/json?color=41BDF5&logo=home-assistant&label=integration%20usage&suffix=%20installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.enpal.total)

## Disclaimer

This integration is created with acknowledgement and limited support from Enpal GmbH, but __it's not official software from Enpal__.<br>
It's a custom integration created entirely by me (Skipperro), and thus Enpal GmbH is not responsible for any damage/issues caused by this integration, nor it offers any end-user support for it.

It is still a work in progress and is not guaranteed to work 100% or even work at all.<br>

## Braking changes in 0.4.0 

> [!WARNING]  
> Version 0.4.0 of this integration is no longer using InfluxDB connection and doesn't require access token from Enpal.
> Instead it's based on pure HTML scraping of the Enpal web interface. 
> This means that the integration is now more reliable and doesn't require any special access to the Enpal system or periodic support tickets to get a new token.
> 
> The downside is, that it's no longer compatible with the previous versions of the integration, and you will need to remove the old integration and install the new one.

## How it works

During the setup you will need to provide IP of the Enpal Box for your installation. The device should be connected to your LAN/WiFi network, so you should be able to get the IP from your router or by scanning the network for devices with web interface.

![enpal web-interface](images/enpal-web-interface.png)

The integration will then scrape the data from the Enpal Box web interface ([IP]/deviceMessages) and provide it to Home Assistant as a set of sensors. Each row on the table will be represented as a sensor. 

Whenever possible, numerical values will be kept as numbers and the measurement units will also be passed to Home Assistant, so history graphs will be displayed correctly.
If conversion to number is not possible, the value will be passed as a string, for example for inverter serial number or operation modes.

![enpal measurements](images/enpal-measurements.png)

## Installation

1. Install this integration with HACS (adding repository required), or copy the contents of this
repository into the `custom_components/enpal` directory.
2. Restart Home Assistant.
3. Start the configuration flow:
   - [![Start Config Flow](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start?domain=enpal)
   - Or: Go to `Configuration` -> `Integrations` and click the `+ Add Integration`. Select `Enpal` from the list.
   - If the integration is not found try to refresh the HA page without using cache (Ctrl+F5).
4. Input the IP, Port and access token for access InfluxDB server of your Enpal solar installation.

![enpal config](images/enpal-config.png)
