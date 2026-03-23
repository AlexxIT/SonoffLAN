# Control Sonoff Devices from Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/hacs/integration)

Home Assistant custom component for control [Sonoff](https://www.itead.cc/) devices with [eWeLink](https://www.ewelink.cc/en/) (original) firmware over LAN and/or Cloud.

> [!CAUTION]
> Starting in 2026 - power, current, and voltage sensors will no longer be updated via the cloud connection. These updates placed a heavy load on the eWeLink cloud. As a result, they were blocked by the cloud.

<details>
<summary><b>Table of Contents</b></summary>

- [Installation](#installation)
- [Configuration](#configuration)
- [Posting new issues](#posting-new-issues)
- [Configuration UI](#configuration-ui)
  * [Mode](#mode)
  * [Debug page](#debug-page)
  * [Homes](#homes)
- [Configuration YAML](#configuration-yaml)
  * [Custom device_class](#custom-device-class)
  * [Custom devices](#custom-devices)
  * [Custom sensors](#custom-sensors)
  * [Force update](#force-update)
  * [Preventing DB size growth](#preventing-db-size-growth)
- [Sonoff Pow](#sonoff-pow)
- [Sonoff TH](#sonoff-th)
- [Sonoff RF Bridge 433](#sonoff-rf-bridge-433)
- [Sonoff GK-200MP2-B Camera](#sonoff-gk-200mp2-b-camera)
- [Common problems in only LAN mode](#common-problems-in-only-lan-mode)
- [Raw commands](#raw-commands)
- [Getting devicekey manually](#getting-devicekey-manually)
- [Useful Links](#useful-links)

</details>

A list of known devices can be found here - [DEVICES](DEVICES.md).

**Features**

- support new [eWeLink API](https://coolkit-technologies.github.io/eWeLink-API/#/en/PlatformOverview)
- support [multiple eWeLink accounts](#configuration) and [homes](#homes)
- can manage **both local and cloud control at the same time**!

**Pros**

- work with original eWeLink / Sonoff firmware, no need to flash devices
- work over Local Network and/or Cloud Server
- work with devices without DIY-mode
- work with devices in DIY-mode
- support single and multi-channel devices
- support TH and Pow device sensors
- support Sonoff [RF Bridge 433](#sonoff-rf-bridge-433) for receive and send commands
- instant device state update with local Multicast or cloud Websocket connection
- load devices list from eWeLink Servers (with names and encryption keys) and save it locally
- (optional) change [device type](#custom-device_class) from `switch` to `light`

**Component review from DrZzs**

[![Sonoffs can work with Home Assistant without changing the Firmware!](https://img.youtube.com/vi/DsTqOlrQQ1k/mqdefault.jpg)](https://www.youtube.com/watch?v=DsTqOlrQQ1k)

Thanks to [@beveradb](https://github.com/beveradb/sonoff-lan-mode-homeassistant) and [@mattsaxon](https://github.com/mattsaxon/sonoff-lan-mode-homeassistant) for researching the local Sonoff protocol.
Thanks to [@michthom](https://github.com/michthom) and [@EpicLPer](https://github.com/EpicLPer) for researching the local Sonoff Camera protocol.

## Installation

[![](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=AlexxIT&repository=SonoffLAN&category=Integration)

Via [HACS](https://hacs.xyz/) or manually copy `sonoff` folder from [latest release](https://github.com/AlexxIT/SonoffLAN/releases/latest) to `custom_components` folder in your config folder.

## Configuration

[![](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=sonoff)

Add integration via Home Assistant UI. You can setup multiple integrations with different ewelink accounts.

## Posting new issues

Before posting new issue:

1. Check the number of online devices on the [System Health page](https://my.home-assistant.io/redirect/system_health)
2. Check warning and errors on the [Logs page](https://my.home-assistant.io/redirect/logs/)
3. Check **debug logs** on the [Debug page](#debug-page) (must be enabled in integration options)
4. Check **open and closed** [issues](https://github.com/AlexxIT/SonoffLAN/issues?q=is%3Aissue)
5. Share integration [diagnostics](https://www.home-assistant.io/integrations/diagnostics/):
   - All devices: Settings > [Integrations](https://my.home-assistant.io/redirect/integrations/) > **Sonoff** > 3 dots > Download diagnostics
   - One device: Settings > [Devices](https://my.home-assistant.io/redirect/devices/) > Device > Download diagnostics

## Configuration UI

Settings > [Integrations](https://my.home-assistant.io/redirect/integrations/) > **Sonoff** > Configure (gear)

### Mode

In `auto` mode component using both local and cloud connections to your devcies. If device could be reached via LAN - the local connection will be used. Otherwise the cloud connection will be used.

`local` mode or `cloud` mode will use only this type of connection.

Sometimes it can be difficult to get a local connection to work. You need a local network with working Multicast (mDNS/[zeroconf](https://www.home-assistant.io/integrations/zeroconf/)) traffic between the Hass and your devices. Read about [common problems](#common-problems-in-only-lan-mode).

Each time the integration starts, a list of user devices is loaded from cloud and saved locally (`/config/.storage/sonoff/`).

`auto` mode and `local` mode can work without Internet connection. If the integration fails to connect to the cloud - the component will use the previously saved list of devices and continue to work only in `local` mode. `auto` mode will continue trying to connect to the cloud.

`local` mode can't work without ewelink credentials because it needs devices encryption keys.

Devices in DIY mode can be used without ewelink credentials because their protocol unencrypted.

It is **highly recommended** that you use `mode: auto` and do not use `mode: local` or DIY mode. Because the local protocol is not always stable and you will get a bad experience. Devices may sometimes disappear from the network or fail to respond to local requests. Also some POW and TH devices cannot update their sensors without a cloud connection.

### Debug page

Enable debug page in integration configuration (gear) via UI. Reload integrations page. Open: Integraion > Menu (top right dots) > Known issues.

Debug page shows only integration logs and removes some private data. You can filter log and enable auto refresh (in seconds).

```
http://192.168.1.123:8123/api/sonoff/c8503fee-88fb-4a18-84d9-abb782bf0aa7?q=1000xxxxxx&r=2
```

### Homes

By default component loads cloud devices **only for current active Home** in ewelink application. If there is only one Home in the account, it shouldn't be a problem. Otherwise you can select one or multiple Homes to load devices from.

## Configuration YAML

These settings are made via [YAML](https://www.home-assistant.io/docs/configuration/).

**Important**. DeviceID is always 10 symbols string from entity_id or eWeLink app.

### Custom device_class

You can convert all switches into light by default:

```yaml
sonoff:
  default_class: light  # (optional), default switch
```

You can convert specific switches into `light`, `fan` or `binary_sensor`:

```yaml
sonoff:
  devices:
    1000xxxxxx:
      device_class: light
      name: Sonoff Basic
    1000yyyyyy:
      device_class: fan
      name: Sonoff Mini
```

You can convert multi-channel devices (e.g. Sonoff T1 2C):

```yaml
sonoff:
  devices:
    1000xxxxxx:
      device_class: [light, fan]
      name: Sonoff T1 2C
    1000yyyyyy:
      device_class: [switch, light]
      name: MiniTiger 2CH
```

You can convert multi-channel device (e.g. Sonoff T1 3C) into single light with brightness control:

```yaml
sonoff:
  devices:
    1000xxxxxx:
      device_class:
        - light: [1, 2, 3]
      name: Sonoff T1 3C
```

You can control multiple light zones with single multi-channel device (e.g. Sonoff 4CH):

```yaml
sonoff:
  devices:
    1000xxxxxx:
      device_class:
        - switch: 1  # entity 1 (channel 1)
        - light: [2, 3]  # entity 2 (channels 2 and 3)
        - fan: 4  # entity 3 (channel 4)
      name: Sonoff 4CH
```

You can change `device_class` for [Binary Sensor](https://www.home-assistant.io/integrations/binary_sensor/):

```yaml
sonoff:
  devices:
    1000xxxxxx:
      device_class: window
```

You can change `device_class` for [Cover](https://www.home-assistant.io/integrations/cover/):

```yaml
sonoff:
  devices:
    1000xxxxxx:
      device_class: shutter
```

You can set the `uiid` when running in DIY mode to enable the device features. More info [here](https://github.com/AlexxIT/SonoffLAN/blob/master/custom_components/sonoff/core/devices.py).

```yaml
sonoff:
  devices:
    1000xxxxxx:
      extra: { uiid: 136 }  # Sonoff B05-BL
```

### Custom devices

```yaml
sonoff:
  devices:
    1000xxxxxx:
      name: Device name from YAML  # optional rewrite device name
      host: 192.168.1.123  # optional force device IP-address
      devicekey: xxx  # optional encription key (downloaded automatically from the cloud)
```

### Custom sensors

If you want some additional device attributes as sensors:

```yaml
sonoff:
  sensors: [staMac, bssid, host]
```

### Force update

You can request actual device state and all its sensors manually at any time using `homeassistant.update_entity` service. Use it with any device entity except sensors. Use it with only one entity from each device.

As example, you can create an automation for forced temperature updates for Sonoff TH:

```yaml
trigger:
  - platform: time_pattern
    minutes: '3'
action:
  - service: homeassistant.update_entity
    target:
      entity_id: switch.sonoff_1000xxxxxx
```

### Preventing DB size growth

Pow devices may send a lot of data every second. You can reduce the amount of processed data.

For multi-channel devices use `power_1`, `current_2`, etc.

```yaml
sonoff:
  devices:
    1000xxxxxx:
      reporting:
        power: [30, 3600, 1]  # min seconds, max seconds, min delta value
        current: [5, 3600, 0.1]
        voltage: [60, 3600, 5]
```

- if new value came before `min seconds` - it will be "delayed"
- if new value came between `min` and `max seconds`
  - if delta lower than `delta value` - it will be "delayed"
  - otherwise - it will be used
- if new value came after `max seconds` - it will be used
- any used value will erase "delayed" value
- new "delayed" value will overwrite old one
- "delayed" value will be checked for the above conditions every 30 seconds

## Sonoff Pow

> [!IMPORTANT]
> Read the warning at the beginning of the readme file.

Check which devices support the local protocol here - [DEVICES](DEVICES.md). Depending on your environment settings, the local protocol may not work. Every device has a connection sensor (disabled by default). You can check which protocol your specific device is using with this sensor.

Support `power`, `current` and `voltage` sensors via **local** connection.

The **S60TPF** device automatically sends power data to the cloud whenever the day energy sensor reading increases by 1W. Therefore, even with a cloud connection, the data will update very slowly, depending on consumption. I don't know if other device models do the same.

Supports two types of `energy`, depending on the device model:

- Regular sensor - updated in real time via a **local** connection (if device supports it)
  - Sensor name: `energy_day`, `energy_week`, `energy_month`, `energy_year`
  - UIID (HW version): 190, 226, 276, 7032
- Historical data - updated once an hour via a **cloud** connection
  - Sensor name: `energy`, `energy_1`, `energy_2`...
  - UIID (HW version): 5, 32, 126, 130, 182, 190

By default, historical `energy` data loads from cloud every hour. You can change interval via YAML and add history data to sensor attributes (max size - 30 days, disable - 0). For multi-channel devices use `energy_1`, `energy_2`.

```yaml
sonoff:
  devices:
    1000xxxxxx:
      reporting:
        energy: [3600, 10]  # update interval (seconds), history size (days)

template:
  - sensor:
      - name: "10 days consumpion"
        unit_of_measurement: "kWh"
        state: "{{ (state_attr('sensor.sonoff_1000xxxxxx_energy', 'history') or [])|sum }}"
```

You can also setup a [integration sensor](https://www.home-assistant.io/integrations/integration/#energy), that will collect energy data locally by Hass:

```yaml
sensor:
  - platform: integration
    source: sensor.sonoff_1000xxxxxx_power
    name: energy_spent
    unit_prefix: k
    round: 2
```

## Sonoff TH

> [!IMPORTANT]
> For the THR316D/THR320D models, temperature and humidity sensor updates only work when connected locally. It's the same issue as with power devices - the message at the beginning of the readme file.

Support optional [Climate](https://www.home-assistant.io/integrations/climate/) entity that controls Thermostat. You can control low and high temperature values and hvac modes:

- **heat** - lower temp enable switch, higher temp disable switch
- **cool** - lower temp disable switch, higher temp enable switch
- **dry** - change control by **humidity** with previous low/high switch settings

In `dry` mode, the Thermostat controls and displays Humidity. But the units are displayed as temperature (Hass limitation).

Thermostat can be controlled only with **Cloud** connection. Main switch and TH sensors support LAN and Cloud connections.

## Sonoff RF Bridge 433

RF Bridge support learning up to 64 signals (16 x 4 buttons).

**Video HOWTO from @KPeyanski**

[![Automatic Calls and Messages from Home Assistant, Sonoff RF Bridge and Smoke Detectors](https://img.youtube.com/vi/QD1K7s01cak/mqdefault.jpg)](https://www.youtube.com/watch?v=QD1K7s01cak?t=284)

**Important**. Integration v3 supports automatic creation of sensors for RF Bridge. All **buttons** will be created as [Button entity](https://www.home-assistant.io/integrations/button/). All **alarms** will be created as [Binary sensor](https://www.home-assistant.io/integrations/binary_sensor/).

Both button and binary sensor has `last_triggered` attribute with the time of the last signal received. You can use it in automations.

Binary sensor will stay in `on` state during **120 seconds** by default. Each new signal will reset the timer. Binary sensor support restore state between Hass restarts.

If you has door sensor with two states (for open and for closed state) like [this one](https://www.banggood.com/10Pcs-GS-WDS07-Wireless-Door-Magnetic-Strip-433MHz-for-Security-Alarm-Home-System-p-1597356.html?cur_warehouse=CN), you can config `payload_off` as in the example below. Also disable the timeout if you do not need it in this case (with `timeout: 0` option).

You can use any `device_class` that is supported in [Binary Sensor](https://www.home-assistant.io/integrations/binary_sensor/). With `device_class: button` you can convert sensor to button.

**PIR Sensor**

```yaml
sonoff:
  rfbridge:
    PIR Sensor 1:  # button/alarm name in eWeLink application
      device_class: motion
      timeout: 60  # optional (default 120), timeout in seconds for auto turn off
```

**Single State Sensor**

```yaml
sonoff:
  rfbridge:
    Door Sensor 1:  # button/alarm name in eWeLink application
      name: Door Sensor  # optional, you can change sensor name
      device_class: door  # e.g. door, window
      timeout: 5
```

**Dual State Sensor**

```yaml
sonoff:
  rfbridge:
    Sensor1:  # button/alarm name in eWeLink application (open signal)
      name: Window Sensor  # optional, you can change sensor name
      device_class: window  # e.g. door, window
      timeout: 0  # disable auto close timeout
      payload_off: Sensor2  # button/alarm name in eWeLink application (close signal)
```

You can read more about using this bridge in [wiki](https://github.com/AlexxIT/SonoffLAN/wiki/RF-Bridge).

## Common problems in only LAN mode

`auto` mode and `cloud` mode users don't have these problems.

**Devices are not displayed**

- not all devices supports local protocol
- two routers
- **docker** with port forwarding
  - you must use: [--network host](https://docs.docker.com/network/network-tutorial-host/)
  - hassio users are okay
- **virtual machine** with port forwarding
  - you must use bridge virtual network mode (not NAT mode)
- Oracle VM VirtualBox
- linux firewall
- linux network driver
- incorrect network interface selected in Configuration > [Settings](https://my.home-assistant.io/redirect/general/) > Global > Network

The devices publish their data through [Multicast DNS](https://en.wikipedia.org/wiki/Multicast_DNS) (mDNS/[zeroconf](https://www.home-assistant.io/integrations/zeroconf/)), read [more](http://developers.sonoff.tech/sonoff-diy-mode-api-protocol.html#Device-mDNS-Service-Info-Publish-Process).

**Devices unavailable after reboot**

All devices **unavailable** after each Home Assistant restart. Devices are automatically detected in the local network after each restart. Sometimes devices appear quickly. Sometimes after a few minutes. If this does not happen, there are some problems with the multicast / router.

## Raw commands

The component adds the service `sonoff.send_command` to send low-level commands.

Example service params to single switch:

```yaml
device: 1000xxxxxx
switch: 'on'
```

Example service params to multi-channel switch:

```yaml
device: 1000xxxxxx
switches: [{outlet: 0, switch: 'off'}]
```

Example service params to dimmer:

```yaml
device: 1000123456
command: dimmable
switch: 'on'
brightness: 50
mode: 0
```

## Getting devicekey manually

*The average user does not need to get the device key manually. The component does everything automatically, using the ewelink account.*

1. Put the device in setup mode
2. Connect to the Wi-Fi network `ITEAD-10000`, password` 12345678`
3. Open in browser `http://10.10.7.1/device`
4. Copy `deviceid` and `apikey` (this is `devicekey`)
5. Connect to your Wi-Fi network and setup Sonoff via the eWeLink app

## Useful Links

- https://github.com/peterbuga/HASS-sonoff-ewelink
- https://github.com/beveradb/sonoff-lan-mode-homeassistant
- https://github.com/mattsaxon/sonoff-lan-mode-homeassistant
- https://github.com/EpicLPer/Sonoff_GK-200MP2-B_Dump
- https://github.com/bwp91/homebridge-ewelink
- https://blog.ipsumdomus.com/sonoff-switch-complete-hack-without-firmware-upgrade-1b2d6632c01
- https://github.com/itead/Sonoff_Devices_DIY_Tools
- [SONOFF DIY MODE API PROTOCOL](http://developers.sonoff.tech/sonoff-diy-mode-api-protocol.html)
- [No Tasmota And EWeLink Cloud To Control The SONOFF Device? YES!](https://sonoff.tech/product-tutorials/diy-mode-to-control-the-sonoff-device)
