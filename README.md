# SonoffLAN

Компонент для работы с устройствами eWeLink по локальной сети.

Тестировался на noname двухкнопочном выключателе. Прошивка выключателя 
обновлена до версии **3.3.0** через стандартное приложение eWeLink.

Для управления Sonoff устройством 3й версии пришивки без DIY режима, 
необходимо узнать его API-ключ:

1. Перевести устройство в режим настройки (*на выключателе это долгое 
удерживание одной из кнопок*)
2. Подключиться к Wi-Fi сети `ITEAD-10000`, пароль `12345678`
3. Открыть в браузере `http://10.10.7.1/device`
4. Скопировать полученные `deviceid` и `apikey`
5. Подключиться к своей Wi-Fi сети и настроить Sonoff через приложение eWeLink

## Home Assistant configuration.yaml

```yaml
sonoff:
  devices:
    1000abcdef:
      apikey: aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee
      channels: 2
```

`channels` - опциональный параметр для многоканальных устройств

## Описание протокола

- Для обнаружения устройств Sonoff используется **Zeroconf** 
(сервис `_ewelink._tcp.local.`)
- В сообщении **Zeroconf** устройство передаёт своё текущее состояние и 
настройки
- Изменение состояния устройства так же передаётся по **Zeroconf** 
(сервис `eWeLink_1000abcdef._ewelink._tcp.local.`)
- Устройство управляется через POST-запросы вида 
`http://{ip}:8081/zeroconf/{command}` с JSON в теле запроса
- В 3й версии прошивки при отключенном режиме DIY - сообщения и управляющие 
комманды шифруются алгоритмом AES 128, где в качестве ключа используется apikey 

**Пример:**

```
POST http://192.168.1.175:8081/zeroconf/switches
{
    "sequence": "1570626382", 
    "deviceid": "1000abcdef", 
    "selfApikey": "123", 
    "data": "MpiTz2jyRiIIaEB4z1nv/ZUaJuToGv8N5SY+G/5tDjQ3f+FGZ/2L0vajqzwbcjIS", 
    "encrypt": true, 
    "iv": "SI3QEXgpvuaHM3hL/1f3eg=="
}
```

В `data` закодирована комманда:

```json
{"switches": [{"outlet": 0, "switch": "on"}]}
```

## Полезные ссылки

- https://github.com/mattsaxon/sonoff-lan-mode-homeassistant
- https://blog.ipsumdomus.com/sonoff-switch-complete-hack-without-firmware-upgrade-1b2d6632c01