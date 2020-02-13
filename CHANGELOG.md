# Changelog

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