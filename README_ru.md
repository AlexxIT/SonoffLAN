# Sonoff

Компонент для работы с устройствами **eWeLink** по локальной сети. Устройства 
должны быть обновлены на прошивку 3й версии. В локальной сети должен 
поддерживаться **Multicast**.

Основные моменты компонента: 

- работает с оригинальной прошивкой Sonoff, нет необходимости перепрошивать 
  устройства
- работает по локальной сети, нет тормозов китайских серверов
- работает с устройствами без DIY-режима
- работает с устройствами в DIY-режиме
- можно получить список устройств с серверов eWeLink, либо настроить его 
  вручную (список сохраняется локально и может больше не запрашиваться)
- мгновенное получение нового состояния устройств по Multicast (привет 
  Yeelight)
- есть возможность менять тип устройства (например свет или вентилятор), для 
  удобной интеграции в голосовые ассистенты
- есть возможность объединить несколько каналов в один источник света и 
  управлять яркостью
  
## Протестированные устройства

- Sonoff Basic (самой первой версии)
- [Sonoff Mini](https://www.itead.cc/sonoff-mini.html) (режим DIY включать не нужно)
- [Sonoff TH](https://www.itead.cc/sonoff-th.html) (показывает температуру и влажность)
- [Sonoff 4CH Pro R2](https://www.itead.cc/sonoff-4ch-pro.html)
- [Sonoff Pow](https://www.itead.cc/sonoff-pow.html) (показывает энергопотребление)
- [Sonoff Micro](https://www.itead.cc/sonoff-micro-5v-usb-smart-adaptor.html)
- [Sonoff RF Bridge 433](https://www.itead.cc/sonoff-rf-bridge-433.html)
- Выключатели [MiniTiger](https://ru.aliexpress.com/item/33016227381.html)

## Примеры конфигов

Минимальный конфиг:

```yaml
sonoff:
  username: mymail@gmail.com
  password: mypassword
```

Расширенный конфиг:

```yaml
sonoff:
  username: mymail@gmail.com
  password: mypassword
  reload: always  # обновлять список устройств при каждом запуске HA
  devices:
    1000abcdefg:
      device_class: light
```

Устройства можно задать вручную, без подключения к китайским серверам. Но в 
этом случае нужно знать `devicekey` для каждого устройства.

```yaml
sonoff:
  devices:
    1000abcdefg:
      devicekey: f9765c85-463a-4623-9cbe-8d59266cb2e4
```

Примеры использования `device_class`:

```yaml
sonoff:
  username: mymail@gmail.com
  password: mypassword
  reload: once
  devices:
    1000abcde0: # коридор свет
      device_class: light
    1000abcde1: # детская свет (двойной выключатель, одна люстра)
      device_class:
      - device_class: light
        channels: [1, 2]
    1000abcde2: # туалет свет и вытяжка (двойной выключатель)
      device_class: [light, fan]
    1000abcde3: # спальня свет и подсветка (двойной выключатель)
      device_class: [light, light]
    1000abcde4: # зал три зоны света Sonoff 4CH
      device_class:
      - light # зона 1 (канал 1)
      - light # зона 2 (канал 2)
      - device_class: light # зона 3 (каналы 3 и 4)
        channels: [3, 4]
```

Для устройств в режиме DIY хватит:

```yaml
sonoff:
```

## Sonoff RF Bridge 433

Хоть компонент и поддерживает обучение - рекомендуется обучать кнопки через 
приложение eWeLink.

Компонент умеет как отправлять RF-сигналы, так и получать их, но только ранее обученные.

При получении команды создаётся событие `sonoff.remote` с порядковым номером 
кнопки и временем срабатывания (в UTC, присылает устройство).

`command` - порядковый номер изученной кнопки в приложении.


```yaml
automation:
- alias: Test RF
  trigger:
    platform: event
    event_type: sonoff.remote
    event_data:
      command: 0
  action:
    service: homeassistant.toggle
    entity_id: remote.sonoff_1000abcdefg

script:
  send_num1:
    sequence:
    - service: remote.send_command
      data:
        entity_id: remote.sonoff_1000abcdefg
        command: 1

  send_num111:
    sequence:
    - service: remote.send_command
      data:
        entity_id: remote.sonoff_1000abcdefg
        command: [1, 1, 1]
        delay_secs: 1
```

## Sonoff TH и Pow

Температура, влажность и остальные параметры устройств хранятся в их аттрибутах. Их можно вывести через [Template](https://www.home-assistant.io/integrations/template/)-сенсор.

```yaml
sensor:
- platform: template
  sensors:
    temperature_purifier:
      friendly_name: Температура
      device_class: temperature
      value_template: "{{ state_attr('switch.sonoff_1000abcdefg', 'temperature') }}"
    humidity_purifier:
      friendly_name: Влажность
      device_class: humidity
      value_template: "{{ state_attr('switch.sonoff_1000abcdefg', 'humidity') }}"
```

## Параметры:

- **reload** - *optional*  
  `always` - загружать список устройств при каждом старте HA  
  `once` - (по умолчанию) загрузить список устройств единожды
- **device_class** - *optional*, переопределяет тип устройства (по умолчанию 
  все устройства **sonoff** отображаются как `switch`). Может быть строкой 
  или массивом строк (для многоканальных выключателей). Поддерживает типы:
  `light`, `fan`, `switch`, `remote` (только для *Sonoff RF Bridge 433*).


## Работа с китайскими серверами

Если в настройках указать `username` и `password` (опционально) - при первом
запуске HA скачает список устройств **eWeLink** с китайских серверов и сохранит
в файле `/config/.sonoff.json` (скрытый файл).

Другие запросы к серверам компонент не делает.

Список загрузится только один раз. И при старте ХА список устройств будет 
загружаться из локального файла. В этом случае, когда у вас появятся новые 
устройства **eWeLink** - вручную удалите файл и перезагрузите ХА.

Если в настройках указать `reload: always` - при каждом старте HA этот файл 
будет обновляться.

Список устройств будет загружаться из локального файла даже если убрать 
`username` и `password` из настроек.

## Получение devicekey вручную

При желании ключ устройства можно получить таким способом.

1. Перевести устройство в режим настройки (*на выключателе это долгое 
удерживание одной из кнопок*)
2. Подключиться к Wi-Fi сети `ITEAD-10000`, пароль `12345678`
3. Открыть в браузере `http://10.10.7.1/device`
4. Скопировать полученные `deviceid` и `apikey` (это и есть `devicekey`)
5. Подключиться к своей Wi-Fi сети и настроить Sonoff через приложение eWeLink

## Демонстрация

**Sonoff 4CH Pro R2**, настроен как единый источник света с управлением яркостью

[![Control Sonoff Devices with eWeLink firmware over LAN from Home Assistant](https://img.youtube.com/vi/X7PcYfDy57A/0.jpg)](https://www.youtube.com/watch?v=X7PcYfDy57A)

## Поддержка HACS

![Support HACS](hacs.png)

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
комманды шифруются алгоритмом AES 128, где в качестве ключа используется 
`devicekey` 

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

## Отладка компонента

```yaml
logger:
  default: info
  logs:
    custom_components.sonoff: debug
```

## Полезные ссылки

- https://github.com/mattsaxon/sonoff-lan-mode-homeassistant
- https://blog.ipsumdomus.com/sonoff-switch-complete-hack-without-firmware-upgrade-1b2d6632c01
- https://github.com/itead/Sonoff_Devices_DIY_Tools/blob/master/SONOFF%20DIY%20MODE%20Protocol%20Doc%20v1.4.md
- https://github.com/peterbuga/HASS-sonoff-ewelink