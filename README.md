<div align="center">

# SonoffLANonly

### LAN-only Sonoff and eWeLink devices in Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-CUSTOM-FD7E14?style=for-the-badge&logo=home-assistant&logoColor=white&labelColor=555555)](https://github.com/hacs/integration)
[![Home Assistant 2023.2+](https://img.shields.io/badge/HOME%20ASSISTANT-2023.2%2B-41BDF5?style=for-the-badge&logo=home-assistant&logoColor=white&labelColor=555555)](https://www.home-assistant.io/)
[![Latest release](https://img.shields.io/github/v/release/Wheemer/SonoffLANonly?style=for-the-badge&logo=github&logoColor=white&label=RELEASE&labelColor=555555&color=22C55E)](https://github.com/Wheemer/SonoffLANonly/releases/latest)
[![License](https://img.shields.io/badge/LICENSE-MIT-64748B?style=for-the-badge&labelColor=555555)](LICENSE.md)

[Install](#install) | [Configure](#configure) | [Polling](#per-device-update-interval) | [Inching](#local-inching-controls) | [Diagnostics](#diagnostics) | [Devices](DEVICES.md)

</div>

SonoffLANonly is a Home Assistant custom integration for Sonoff and other eWeLink devices running their original firmware. It uses the local eWeLink protocol for device commands, state, availability, and realtime telemetry. There is no cloud command or state fallback.

This project is a LAN-only fork of [AlexxIT/SonoffLAN](https://github.com/AlexxIT/SonoffLAN). It keeps the broad device support from that project while adding stricter local operation, local telemetry recovery, and per-device callback watchdog intervals.

## What It Does

- Controls supported switches, lights, sensors, covers, fans, climate devices, RF bridges, cameras, and related entities over LAN.
- Treats local mDNS callbacks as the primary source of state and telemetry.
- Prompts supported power-monitoring devices for fresh local telemetry when callbacks become stale.
- Confirms ack-only stateful commands through a fresh local response.
- Exposes local, per-channel inching enable, duration, and action controls when a device reports `pulses` support.
- Retries unreachable devices and restores entity availability when a device returns.
- Supports a `1` to `300` second device-specific telemetry watchdog interval, with a `30` second default.
- Exposes an optional Connection binary sensor for actual LAN reachability.
- Refreshes the eWeLink device inventory and local encryption keys during integration setup without starting cloud control or cloud state updates.

## LAN-Only Boundary

All runtime device commands, entity state, telemetry, and availability are local. Unsupported cloud modes are rejected instead of silently falling back.

Entities whose implementation is known to require cloud commands are not exposed by this fork. Their locally reported measurements and relay controls remain available as separate entities where supported.

An eWeLink login is still required for normal encrypted devices because the integration needs account inventory, model metadata, and each device's local encryption key. The login is used for metadata retrieval; it is not a cloud control path. DIY devices can be configured without an eWeLink password when their metadata and key are supplied locally.

Home Assistant and the devices must share a network where mDNS and direct TCP traffic can reach the devices. VLANs require working multicast forwarding and routing between Home Assistant and the Sonoff devices.

## Install

[![Open your Home Assistant instance and add this repository to HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Wheemer&repository=SonoffLANonly&category=integration)

If the button does not work:

1. Open HACS.
2. Open the menu and choose **Custom repositories**.
3. Add `https://github.com/Wheemer/SonoffLANonly` as an **Integration** repository.
4. Install **SonoffLANonly**.
5. Restart Home Assistant so the new Python module is loaded.
6. Open **Settings > Devices & services > Add integration** and select **SonoffLANonly**.

For a manual install, copy `custom_components/sonoff` into the Home Assistant `/config/custom_components/` directory and restart Home Assistant.

After any integration update, restart Home Assistant. Reloading the config entry unloads and reloads the already-imported module but does not replace Python code held by the running Home Assistant process.

## Configure

Enter the eWeLink account email or phone number and password. The integration retrieves the device inventory, metadata, and local encryption keys, then operates the devices locally.

Use the integration options to select eWeLink homes or enable the debug page. New devices paired in the eWeLink app are reconciled into the local cache the next time the integration is set up or reloaded with working credentials.

### Per-Device Update Interval

Local callbacks remain authoritative. `update_interval` is the maximum age allowed for supported realtime telemetry before the integration prompts the device for a fresh local publication. It is not a blind poll when callbacks are already arriving.

The default is `30` seconds. Every top-level Sonoff device exposes one **Update interval** Number entity in the device page's **Configuration** section. It controls freshness for all entities belonging to that physical device. Set it from `1` through `300` seconds; the value is stored in the SonoffLANonly config entry and survives reloads, updates, and restarts.

You can also provide initial or fallback values in `configuration.yaml` by eWeLink device ID:

```yaml
sonoff:
  devices:
    1000123456:
      update_interval: 15
    1000654321:
      update_interval: 1
```

Allowed values are `1` through `300` seconds. Restart Home Assistant after changing YAML.

A value saved through the device's **Update interval** control overrides YAML for that device. This keeps existing YAML defaults intact while allowing normal adjustments from the Home Assistant UI.

LAN callbacks reset the device timer. The integration sends a direct local refresh only after the device has been silent for that device's configured interval, so normal callbacks remain authoritative instead of being duplicated by blind polling. Power-monitoring devices use their firmware-specific recovery path. S40 and compatible standalone power plugs are refreshed with `sledonline` while preserving the device's current LED setting. Devices that reject `getState` automatically use mDNS state polling instead. A shorter interval cannot make firmware generate new measurements more quickly than it permits; on devices that publish full telemetry in response, a one-second setting also receives that device's full local meter payload at that configured cadence.

Each device also provides a disabled-by-default diagnostic **Connection** binary sensor. It reports **Connected** only while the device has a usable LAN path and **Disconnected** after repeated direct connection failures. Its `host` attribute identifies the currently used local endpoint. The entity intentionally does not publish polling timestamps or retry counters, because those transient diagnostics do not represent a connection-state change.

### Local Inching Controls

Devices that report the channel-aware `pulses` configuration expose two controls per supported outlet in the device page's **Configuration** section. **Inching mode** offers **Disabled**, **Auto-off** (turn back off after the delay), and **Auto-on** (turn back on after the delay) in one dropdown. **Inching duration** uses 0.5-second increments from 0.5 seconds through one hour.

Each update sends the complete current `pulses` list through the local `/zeroconf/pulses` endpoint. Other outlets and unknown firmware fields are preserved. Home Assistant does not replace entity state from the HTTP acknowledgement alone; it waits for the resulting local state publication.

### Local Device Overrides

The existing SonoffLAN YAML device overrides remain available:

```yaml
sonoff:
  devices:
    1000123456:
      name: Workshop Plug
      device_class: outlet
      devicekey: 0123456789abcdef
      update_interval: 15
```

`devicekey` is sensitive. Do not include it in issues, logs, screenshots, or diagnostics shared publicly.

## Telemetry And Recovery

Supported power devices use local callbacks for power, current, voltage, and energy data. When telemetry becomes older than the configured interval, SonoffLANonly sends the appropriate LAN telemetry command and waits for the resulting local publication. Active reads use Home Assistant's shared Zeroconf instance and discard only the target service's cached record first, so only a fresh device reply advances telemetry freshness. Standalone S40/UIID 182 and UIID 32 devices use `sledonline`; local `uiActive` is not used because affected firmware rejects it. An HTTP acknowledgement alone is not treated as fresh sensor data.

Historical energy requests are also considered successful only after the requested energy payload arrives, either in the LAN response or through the subsequent local callback. An empty acknowledgement does not advance the entity's hourly history throttle.

For devices that return the proven `hundredDaysKwhData` format, SonoffLANonly imports the device's 100-day daily history into Home Assistant Recorder as an external statistic named `sonoff:<device_id>_energy_consumption`. The initial import backfills every available day; hourly updates refresh the latest 30 days so finalized or corrected device totals replace earlier values. Dates use Home Assistant's local timezone, and the importer runs even when the optional historical energy entity is disabled. Select the external statistic directly when configuring the Energy Dashboard.

Repeated connection failures mark a device unavailable. The integration continues local recovery attempts and clears the failure latch before notifying Home Assistant when the device answers again. This prevents a recovered switch from remaining unavailable because Home Assistant evaluated the old failure state during the recovery callback.

## Diagnostics

From **Settings > Devices & services > SonoffLANonly**, open the integration menu and download diagnostics. Connection diagnostic entities are disabled by default; enable one from the device entity list when troubleshooting.

The Connection entity has one stable attribute:

- `host`: the current local host and port used for the device.

Before opening an issue, confirm the device is reachable from the Home Assistant host and include the Home Assistant version, SonoffLANonly version, model, UIID, relevant logs, and sanitized diagnostics. Never publish account credentials or device keys.

## Device Support

See [DEVICES.md](DEVICES.md) for the inherited compatibility table. A verified **Local Type** indicates known local protocol support. Devices known to be cloud-only are intentionally unsupported by this fork. Blank local-support entries are unverified and may require testing.

## Updating From SonoffLAN

SonoffLANonly uses the same `sonoff` integration domain to preserve existing entities and automations. Do not install it alongside AlexxIT/SonoffLAN. Remove the old HACS repository, add this repository, install the fork, and restart Home Assistant once.

Back up Home Assistant before changing custom integration sources. Existing entity IDs should remain stable, but unsupported cloud-only devices will not be available.

## Development

Run the test suite from the repository root:

```bash
pytest -q
```

The GitHub workflow also runs HACS validation and Home Assistant hassfest checks.

## Credits

SonoffLANonly is derived from [AlexxIT/SonoffLAN](https://github.com/AlexxIT/SonoffLAN), including its protocol implementation, device definitions, and community contributions. Original local-protocol research credits remain with the upstream project and its contributors.

This repository preserves the upstream MIT license. See [LICENSE.md](LICENSE.md).
