# Running the regression tests

Run these commands in a separate development environment, not inside a running
Home Assistant installation. The gate candidate was tested with Python 3.14.7
and Home Assistant 2026.9.2:

```sh
python -m pip install homeassistant==2026.9.2 pytest==9.1.1
python -m pytest tests -q -p no:cacheprovider
```

To run only the opt-in UIID 216 gate scenarios:

```sh
python -m pytest tests/test_gate.py -q -p no:cacheprovider
```

The tests replay synthetic commands and notifications through SonoffLAN's existing
WebSocket processing and registry. All command transports are mocked: they do not
connect to an eWeLink account or operate a gate. Hardware qualification must still
confirm the two-report behaviour for the target controller and firmware.
