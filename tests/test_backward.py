from homeassistant.components.button import ButtonEntity
from homeassistant.components.climate.const import ClimateEntityFeature, HVACMode
from homeassistant.components.fan import FanEntityFeature, FanEntity
from homeassistant.components.light import ColorMode, LightEntityFeature
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.helpers.entity import Entity

from . import init


def test_2021_9_0():
    sensor = SensorEntity()
    assert sensor.native_value is None
    assert sensor.native_unit_of_measurement is None


def test_2021_12_0():
    assert ButtonEntity
    assert EntityCategory
    assert FanEntity().percentage is 0
    assert SensorDeviceClass
    assert SensorStateClass


def test_2022_5_0():
    assert ClimateEntityFeature
    assert HVACMode
    assert FanEntityFeature
    assert ColorMode
    assert LightEntityFeature


def test_2022_11_0():
    assert UnitOfEnergy
    assert UnitOfPower
    assert UnitOfTemperature


def test_2023_1_0():
    assert UnitOfElectricCurrent
    assert UnitOfElectricPotential


def test_2024_1_cached_properties():
    _, entities = init({"extra": {"uiid": 5}})
    sensor: SensorEntity = next(e for e in entities if e.uid == "energy")
    assert sensor.device_class == SensorDeviceClass.ENERGY

    _, entities = init({"extra": {"uiid": 1256}})
    sensor: Entity = next(e for e in entities)
    assert sensor.should_poll is False
