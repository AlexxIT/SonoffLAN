# Control Sonoff Devices from Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/custom-components/hacs)
[![Donate](https://img.shields.io/badge/donate-Coffee-yellow.svg)](https://www.buymeacoffee.com/AlexxIT)
[![Donate](https://img.shields.io/badge/donate-Yandex-red.svg)](https://money.yandex.ru/to/41001428278477)

Home Assistant custom component for control [Sonoff](https://www.itead.cc/) devices with [eWeLink](https://www.ewelink.cc/en/) (original) firmware over LAN and/or Cloud.

**New features in version 3.0**

- support Integration UI, Devices and Zones
- support new [eWeLink API](https://coolkit-technologies.github.io/eWeLink-API/#/en/PlatformOverview)
- support [multiple eWeLink accounts](#configuration) and [homes](#homes)
- support many sensors for each device (include [RFBridge](#sonoff-rf-bridge-433))
- support thermostats for [Sonoff TH](#sonoff-th) ans NS Panel
- support [preventing DB size growth](#preventing-db-size-growth)
- support many new Hass features

**Features from previous versions**

- can manage **both local and cloud control at the same time**!
- support old devices wih 2.7 firmware (only cloud connection)
- support new device types: color lights, sensors, covers
- support [eWeLink cameras](#sonoff-gk-200mp2-b-camera) with PTZ
- support unavailable device state for both local and cloud connection
- support sensors for Sonoff [RF Bridge 433](#sonoff-rf-bridge-433)
- support ZigBee Bridge and Devices
- added new [debug mode](#debug-page) for troubleshooting

**Pros**

- work with original eWeLink / Sonoff firmware, no need to flash devices
- work over Local Network and/or Cloud Server
- work with devices without DIY-mode
- work with devices in DIY-mode
- support single and multi-channel devices
- support TH and Pow device sensors
- support Sonoff [RF Bridge 433](#sonoff-rf-bridge-433) for receive and send commands
- support Sonoff [GK-200MP2-B Camera](#sonoff-gk-200mp2-b-camera)
- instant device state update with local Multicast or cloud Websocket connection
- load devices list from eWeLink Servers (with names and encryption keys) and save it locally
- (optional) change [device type](#custom-device_class) from `switch` to `light`

**Component review from DrZzs**

[![Sonoffs can work with Home Assistant without changing the Firmware!](https://img.youtube.com/vi/DsTqOlrQQ1k/mqdefault.jpg)](https://www.youtube.com/watch?v=DsTqOlrQQ1k)

There is another great component by [@peterbuga](https://github.com/peterbuga/HASS-sonoff-ewelink), that works with cloud servers.

Thanks to [@beveradb](https://github.com/beveradb/sonoff-lan-mode-homeassistant) and [@mattsaxon](https://github.com/mattsaxon/sonoff-lan-mode-homeassistant) for researching the local Sonoff protocol.  
Thanks to [@michthom](https://github.com/michthom) and [@EpicLPer](https://github.com/EpicLPer) for researching the local Sonoff Camera protocol.

## Tested Devices

Almost any single or multi-channel Switch working in the eWeLink application will work with this Integration even if it is not on the list.

**Tested (LAN and Cloud)**

These devices work both on a local network and through the cloud.

- Sonoff Basic, [BASICR2](https://itead.cc/product/sonoff-basicr2/), [BASICR3](https://itead.cc/product/sonoff-basicr3-wifi-diy-smart-switch/), [RFR2](https://itead.cc/product/sonoff-rf/), [RFR3](https://itead.cc/product/sonoff-rfr3/)
- [Sonoff Mini](https://itead.cc/product/sonoff-mini/), [MINI R3](https://itead.cc/product/sonoff-minir3-smart-switch/) (no need use DIY-mode)
- [Sonoff Micro](https://itead.cc/product/sonoff-micro-5v-usb-smart-adaptor/)
- [Sonoff TH10/TH16](https://itead.cc/product/sonoff-th/) (support Thermostat)
- Sonoff 4CH, 4CHR2, [4CHR3 & 4CHPROR3](https://itead.cc/product/sonoff-4ch-r3-pro-r3/)
- Sonoff POW, [POWR2](https://itead.cc/product/sonoff-pow-r2/) (show power consumption)
- [Sonoff DUALR3/DUALR3 Lite](https://itead.cc/product/sonoff-dualr3/)
- [Sonoff RF Bridge 433](https://www.itead.cc/sonoff-rf-bridge-433.html) (receive and send commands) fw 3.5.0
- [Sonoff D1](https://www.itead.cc/sonoff-d1-smart-dimmer-switch.html) (dimmer with brightness control) fw 3.4.0, 3.5.0
- [Sonoff G1](https://www.itead.cc/sonoff-g1.html) fw 3.5.0
- [Sonoff Dual](https://www.itead.cc/sonoff-dual.html)
- Sonoff iFan02, iFan03, [iFan04](https://www.itead.cc/sonoff-ifan03-wifi-ceiling-fan-light-controller.html) (light and fan with speed control) fw 3.4.0
- Sonoff S20, [S26](https://itead.cc/product/sonoff-s26-wifi-smart-plug/), [S31](https://itead.cc/product/sonoff-s31/), [S55](https://itead.cc/product/sonoff-s55/)
- [Sonoff SV](https://www.itead.cc/sonoff-sv.html) fw 3.0.1
- Sonoff T1, [TX Series](https://itead.cc/product/sonoff-tx-series-wifi-smart-wall-switches/)
- [Sonoff T4EU1C](https://www.itead.cc/sonoff-t4eu1c-wi-fi-smart-single-wire-wall-switch.html)
- [Sonoff IW100/IW101](https://www.itead.cc/sonoff-iw100-iw101.html)
- [Sonoff Slampher R2](https://www.itead.cc/sonoff-slampher-r2.html)
- [Sonoff 5V DIY](https://www.aliexpress.com/item/32818293817.html)
- [Sonoff RE5V1C](https://www.itead.cc/sonoff-re5v1c.html)
- [Sonoff NSPanel](https://itead.cc/product/sonoff-nspanel-smart-scene-wall-switch/)
- [MiniTiger Wall Switch](https://www.aliexpress.com/item/33016227381.html) (I have 8 without zero-line) fw 3.3.0
- [Smart Circuit Breaker](https://www.aliexpress.com/item/4000454408211.html), [link](https://www.aliexpress.com/item/4000351300288.html), [link](https://www.aliexpress.com/item/4000077475264.html)
- [Smart Timer Switch](https://www.aliexpress.com/item/4000189016383.html)
- [Eachen WiFi Smart Touch](https://ewelink.eachen.cc/product/eachen-single-live-wall-switch-us-ac-l123ewelink-app/) fw 3.3.0

**Tested (only Cloud)**

These devices only work through the cloud!

- [Sonoff L1](https://www.itead.cc/sonoff-l1-smart-led-light-strip.html) (color, brightness, effects) fw 2.7.0
- [Sonoff B1](https://www.itead.cc/sonoff-b1.html) (color, brightness, color temp) fw 2.6.0
- Sonoff B02, B05-B, B05-BL
- [Sonoff SC](https://www.itead.cc/sonoff-sc.html) (five sensors) fw 2.7.0
- [Sonoff DW2](https://www.itead.cc/sonoff-dw2.html)
- [Sonoff SwitchMan R5](https://itead.cc/product/sonoff-switchman-scene-controller-r5/)
- [Sonoff S-MATE](https://sonoff.tech/product/diy-smart-switch/s-mate/)
- [Sonoff S40](https://itead.cc/product/sonoff-iplug-series-wi-fi-smart-plug-s40-s40-lite/)
- [King Art - King Q4 Cover](https://www.aliexpress.com/item/32956776611.html) (pause, position) fw 2.7.0
- [KING-M4](https://www.aliexpress.com/item/33013358523.html) (brightness) fw 2.7.0
- [Eachen WiFi Door/Window Sensor](https://ewelink.eachen.cc/product/eachen-wifi-smart-door-window-sensor-wdw-ewelink/)
- [Essential Oils Diffuser](https://www.amazon.co.uk/dp/B07WF7MQ17) (fan and color light) fw 2.9.0
- [Smart USB Mosquito Killer](https://www.aliexpress.com/item/33037963105.html)
- [Smart Bulb RGB+CCT](https://www.aliexpress.com/item/4000764330397.html)

**Tested ZigBee (only Cloud)**

- [Sonoff ZigBee Bridge](https://www.itead.cc/sonoff-zbbridge.html) - turn on for pairing mode
- SONOFF SNZB-01 - Zigbee Wireless Switch
- SONOFF SNZB-02 - ZigBee Temperature and Humidity Sensor
- SONOFF SNZB-03 - ZigBee Motion Sensor
- SONOFF SNZB-04 - ZigBee Wireless door/window sensor

**Tested Cameras (only LAN)**

Maybe other eWeLink cameras also work, I don’t know.

- [Camera GK-100CD10B](https://www.gearbest.com/smart-home-controls/pp_009678072743.html) (camera with PTZ)
- [Sonoff GK-200MP2-B](https://www.itead.cc/sonoff-gk-200mp2-b-wi-fi-wireless-ip-security-camera.html) (camera with PTZ)

## Installation

[HACS](https://hacs.xyz/) > Integrations > Plus > **SonoffLAN**

Or manually copy `sonoff` folder from [latest release](https://github.com/AlexxIT/SonoffLAN/releases/latest) to `custom_components` folder in your config folder.

## Configuration

Configuration > [Integrations](https://my.home-assistant.io/redirect/integrations/) > Add Integration > [Sonoff](https://my.home-assistant.io/redirect/config_flow_start/?domain=sonoff)

You can setup multiple integrations with different ewelink accounts.

## Issues

Before posting new issue:

1. Check the number of online devices on the [System Health page](https://my.home-assistant.io/redirect/info/)
2. Check warning and errors on the [Logs page](https://my.home-assistant.io/redirect/logs/)
3. Check **debug logs** on the [Debug page](#debug-page) (must be enabled in integration options)
4. Check **open and closed** [issues](https://github.com/AlexxIT/SonoffLAN/issues?q=is%3Aissue)
5. Share integration [diagnostics](https://www.home-assistant.io/integrations/diagnostics/):

- All devices: Configuration > [Integrations](https://my.home-assistant.io/redirect/integrations/) > **Sonoff** > 3 dots > Download diagnostics
- One device: Configuration > [Devices](https://my.home-assistant.io/redirect/devices/) > Device > Download diagnostics

*There is no private data, but you can delete anything you think is private.*

## Configuration UI

Configuration > [Integrations](https://my.home-assistant.io/redirect/integrations/) > **Sonoff** > Configure

### Mode

In `auto` mode component using both local and cloud connections to your devcies. If device could be reached via LAN - the local connection will be used. Otherwise the cloud connection will be used. This mode is recommended for most general user.

`local` mode or `cloud` mode will use only this type of connection.

Sometimes it can be difficult to get a local connection to work. You need a local network with working Multicast (mDNS/[zeroconf](https://www.home-assistant.io/integrations/zeroconf/)) traffic between the Hass and your devices. Read about [common problems](#common-problems-in-only-lan-mode).

Each time the integration starts, a list of user devices is loaded from cloud and saved locally (`/config/.storage/sonoff/`).

`auto` mode and `local` mode can work without Internet connection. If the integration fails to connect to the cloud - the component will use the previously saved list of devices and continue to work only in `local` mode. `auto` mode will continue trying to connect to the cloud.

`local` mode can't work without ewelink credentials because it needs devices encryption keys.

Devices in DIY mode can be used without ewelink credentials because their protocol unencrypted. But the average user does not need to use devices in this mode.

### Debug page

A link to the debug page can be found on the [System Health page](https://my.home-assistant.io/redirect/info/). Debug page shows only Integration logs and removes all private data. You can filter log and enable auto refresh (in seconds).

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

You can control multiple light zones with single multi-channel device (e.g. Sonoff 4CH Pow):

```yaml
sonoff:
  devices:
    1000xxxxxx:
      device_class:
        - switch: 1  # entity 1 (channel 1)
        - light: [2, 3]  # entity 2 (channels 2 and 3)
        - fan: 4  # entity 3 (channel 4)
      name: Sonoff 4CH Pow
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

### Preventing DB size growth

Pow devices may send a lot of data every second. You can reduce the amount of processed data.

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

## Sonoff TH

Support optional [Climate](https://www.home-assistant.io/integrations/climate/) entity that controls Thermostat. You can control low and high temperature values and hvac modes:

- **heat** - lower temp enable switch, higher temp disable switch
- **cool** - lower temp disable switch, higher temp enable switch
- **dry** - change control by **humidity** with previous low/high switch settings

In `dry` mode, the Thermostat controls and displays Humidity. But the units are displayed as temperature (Hass limitation).

Thermostat can be controlled only with **Cloud** connection. Main switch and TH sensors support LAN and Cloud connections.

## Sonoff Pow

Support power, current and voltage sensors via LAN and Cloud connections. Also support energy (consumption) sensor only with **Cloud** connection. Energy data loads from cloud every hour.

You can also setup a sensor, that will collect energy data locally by Hass:

```yaml
sensor:
  - platform: integration
    source: sensor.sonoff_1000xxxxxx_power
    name: Dishwasher
    unit_prefix: k
    unit: kWh
    round: 2
```

## Sonoff RF Bridge 433

**Video HOWTO from @KPeyanski**

[![Automatic Calls and Messages from Home Assistant, Sonoff RF Bridge and Smoke Detectors](https://img.youtube.com/vi/QD1K7s01cak/mqdefault.jpg)](https://www.youtube.com/watch?v=QD1K7s01cak?t=284)

**Important**. Integration v3 supports automatic creation of sensors for RF Bridge. All buttons will be created as [Button entity](https://www.home-assistant.io/integrations/button/). All sensors will be created as [Binary entity](https://www.home-assistant.io/integrations/binary_sensor/).

Both button and binary sensor has `last_triggered` attribute with the time of the last signal received. You can use it in automations.

Binary sensor will stay in `on` state during **120 seconds** by default. Each new signal will reset the timer.

You can read more about configuring and using this bridge in [wiki](https://github.com/AlexxIT/SonoffLAN/wiki/RF-Bridge).

## Sonoff GK-200MP2-B Camera

Currently only PTZ commands are supported. Camera entity is not created now.

You can send `left`, `right`, `up`, `down` commands with `sonoff.send_command` service:

```yaml
script:
  left:
    sequence:
      - service: sonoff.send_command
        data:
          device: '012345'  # use quotes, this is important
          cmd: left
```

`device` - this is the number from the camera ID `EWLK-012345-XXXXX`, exactly 6 digits (leading zeros - it is important).

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
cmd: dimmable
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
