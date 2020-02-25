# Changelog

## 0.2.16 - 2020-02-25

### Added

- `default_class` config option 

## 0.2.15 - 2020-02-24

### Changed

- The component is completely rewritten to asynchronous work.

## 0.2.14 - 2020-02-22

### Added

- Support Sonoff iFan02 and iFan03 (light and fan with speed control)

## 0.2.13 - 2020-02-21

### Added

- Load friendly names for **RF Bridge** buttons from cloud servers
- **RF Bridge** displays last pressed button in attributes
- Send **RF Bridge** command by button name
- Load friendly names for multi-channel switch child buttons from cloud servers

You must manually delete the `.sonoff.json` file to update names.

## 0.2.12 - 2020-02-20

### Added

- Service `sonoff.send_command` to send low-level commands.

### Changed

- Unknown devices will be added as binary_sensor. For debugging purposes

## 0.2.11 - 2020-02-14

### Added

- Support login with phone number

## 0.2.10 - 2020-02-13

### Fixed

- Some users devices send updates several times
- Some users had update errors at startup

## 0.2.9 - 2020-02-12

### Added

- Support Sonoff D1 (dimmer)
- Automatic detection `device_class` for popular devices

## 0.2.8 - 2020-01-25

### Changed

- Add config check (fix only numbers in password or deviceid)

## 0.2.7 - 2020-01-25

### Fixed

- Support non Euro eWeLink server
- Fix readme about `reload: always` default value

## 0.2.6 - 2020-01-22

### Added

- rssi device attribute

## 0.2.5 - 2020-01-21

### Added

- Support Sonoff Pow

## 0.2.4 - 2020-01-18

### Added

- Support Sonoff in DIY mode

## 0.2.3 - 2020-01-18

### Added

- Support Sonoff RF Bridge 433

## 0.2.2 - 2020-01-18

### Fixed

- Support Apple HomeKit

## 0.2.1 - 2020-01-15

### Added

- Support [HACS](https://hacs.xyz/) as Custom Repo

## 0.2.0 - 2020-01-12

### Added

- Support download devices list from [eWeLink](https://www.ewelink.cc/en/) servers
- Support control `device_class` (`switch`, `light`, `fan`)
- Support multichannel devices as single `light` with brightness controll

# Changed

- `apikey` renamed to `devicekey`

## 0.1.1 - 2019-11-20

### Added

- Support **Sonoff TH** (temperature and humidity)

## 0.1.0 - 2019-11-16

### Added

- Support control **Sonoff** (eWeLink) devices over LAN