# Devices

- **Model** - device model from the ewelink cloud.
- **UIID** - [CoolKit UIID Protocol](https://github.com/CoolKit-Technologies/eWeLink-API/blob/main/en/UIIDProtocol.md). This is displayed as "Hardware firmware" on device page.
- **Tag** - Just a label, no specifications.
- **Local Type** - A text value indicates that the device supports the **local protocol**. If you see a dash there, the device does not support it and works **only via the cloud**. If you see a blank space, it simply means there is **no verified information** about the device.

| Model                         | UIID | Tag       | Firmware    | Local Type      | Comment                                       |
|-------------------------------|------|-----------|-------------|-----------------|-----------------------------------------------|
| BASICR2                       | 1    | 1ch       | 3.5.1       |                 |                                               |
| BASIC_R3                      | 1    | 1ch       | 3.6.0       |                 |                                               |
| Basic2                        | 1    | 1ch       | 3.8.2       | ???             |                                               |
| M601-1                        | 1    | 1ch       | 3.4.0       | plug            |                                               |
| MINI                          | 1    | 1ch       | 3.8.0       | plug            |                                               |
| RE5V1C                        | 1    | 1ch       | 3.5.1       | plug            |                                               |
| RFR2-8285                     | 1    | 1ch       | 3.8.2       | plug            |                                               |
| S26R1                         | 1    | 1ch       | 3.7.6       |                 |                                               |
| S26R2                         | 1    | 1ch       | 3.8.0       | plug            |                                               |
| SA-018                        | 1    | 1ch       | 3.8.1       | plug            |                                               |
| SANTTON_2                     | 1    | 1ch       | 3.5.1       | plug            |                                               |
| M602-1                        | 2    | 2ch       | 3.4.1       | strip           |                                               |
|                               | 3    | 3ch       |             |                 |                                               |
| 4CH Pro                       | 4    | 4ch       | 3.8.2       | strip           |                                               |
| Sonoff Pow                    | 5    | pow       | 2.6.1       | ---             | Sonoff POW (first)                            |
| Slampher_RF                   | 6    | 1ch       | 3.8.0       |                 |                                               |
| TX1C                          | 6    | 1ch       | 3.8.0       | plug            |                                               |
| TX2C                          | 7    | 2ch       | 3.8.0       | strip           |                                               |
| TX3C                          | 8    | 3ch       | 3.8.0       | strip           |                                               |
|                               | 9    | 4ch       |             |                 |                                               |
| BCM500DS-KZW                  | 11   | cover     | 3.4.3       | ---             |                                               |
| Basic                         | 14   | 1ch       | 3.5.0       | plug            |                                               |
| Sonoff                        | 14   | 1ch       | 3.8.1       | plug            |                                               |
| TH10R2                        | 15   | th        | 3.5.0       | ???             | Sonoff TH16                                   |
|                               | 18   | sensor    | 2.7.0       |                 |                                               |
|                               | 22   | light     |             | ---             | Sonoff B1                                     |
| YB-01                         | 25   | diffuser  | 3.4.0       |                 | Essential Oils Diffuser                       |
| RFBridge                      | 28   | bridge    | 3.5.0       |                 | Sonoff RF Brigde 433                          |
| RFBridge433                   | 28   | bridge    | 3.6.2       | rf              |                                               |
|                               | 29   | 2ch       |             |                 |                                               |
|                               | 30   | 3ch       |             |                 |                                               |
|                               | 31   | 4ch       |             |                 |                                               |
| POWR2                         | 32   | pow       | 3.7.0       | enhanced_plug   |                                               |
| POWR3                         | 32   | pow       | 1.2.1       | enhanced_plug   |                                               |
| PSF-X67                       | 32   | pow       | 3.6.4       | enhanced_plug   |                                               |
| ZJSB9-80 J                    | 32   | pow       | 3.6.4       | enhanced_plug   |                                               |
|                               | 33   | light     |             |                 | Sonoff L1                                     |
| iFan03                        | 34   | fan       | 3.6.0       | fan_light       |                                               |
| iFan04                        | 34   | fan       | 3.6.0       | fan_light       |                                               |
| KING-M4                       | 36   | dimmer    |             | ---             |                                               |
| D1R1                          | 44   | dimmer    | 3.5.0       | ???             | Sonoff D1                                     |
|                               | 57   | mosquito  |             |                 | Mosquito Killer Lamp                          |
| L1                            | 59   | light     | 3.4.3       | ---             | Sonoff L1                                     |
| ZBBridge                      | 66   | bridge    | 1.1.0       |                 | ZigBee Bridge                                 |
| KING-Q1                       | 67   | cover     | 3.4.3       | ---             | KingArt Garage Door Opener                    |
| Micro                         | 77   | usb       | 3.7.1       | switch_radar    | Sonoff Micro                                  |
| Micro-CFH                     | 77   | usb       | 3.6.0       | strip           |                                               |
| Single...                     | 78   | 1ch       |             |                 |                                               |
| GTWS78                        | 78   |           | 1.4.1       | strip           | AltoBeam GTWS78 #1160                         |
|                               | 81   | 1ch       |             |                 |                                               |
|                               | 82   | 2ch       |             |                 |                                               |
|                               | 83   | 3ch       |             |                 |                                               |
|                               | 84   | 4ch       |             |                 |                                               |
| GK-200MP2B                    | 87   | camera    | 41220220712 | ---             |                                               |
| ST-03                         | 91   | cover     | 3.4.3       | ---             |                                               |
|                               | 102  | sensor    |             |                 | Sonoff DW2 Door/Window sensor                 |
|                               | 103  | light     |             | ???             | Sonoff B02 CCT bulb                           |
| B05-B                         | 104  | light     | 1.3.2       | light           | Sonoff B05-B RGB+CCT color bulb               |
|                               | 107  | 1ch       |             |                 |                                               |
| DUALR3                        | 126  | pow       | 1.6.1       | multifun_switch | Sonoff DualR3                                 |
|                               | 127  | climate   |             |                 |                                               |
| SPM-Main                      | 128  | bridge    | 1.3.0       | meter           | SPM-Main                                      |
| GD32-SM4(130)                 | 130  | pow       | 1.3.0       | ---             | SPM-4Relay, can't safe get state via lan      |
|                               | 133  | panel     |             |                 | Sonoff NS Panel                               |
|                               | 135  | light     |             | ???             | Sonoff B02-BL                                 |
| B05-BL                        | 136  | light     | 1.7.0       | light           | Sonoff B05-BL                                 |
| L2                            | 137  | light     | 1000.2.1050 | ---             |                                               |
| BASICR4                       | 138  | 1ch       | 1.1.0       | plug            |                                               |
| CK-BL602-4SW-AY(138)          | 138  | 1ch       | 1.2.0       | ???             |                                               |
| CK-BL602-4SW-HS-03(138)-1     | 138  | 1ch       | 1.3.1       | plug            |                                               |
| CK-BL602-4SW-HS(138)          | 138  | 1ch       | 1.6.1       | plug            |                                               |
| CK-BL602-4SW-WH(138)          | 138  | 1ch       | 1.3.1       | plug            |                                               |
| MINI-D                        | 138  | 1ch       | 1.0.0       | plug            |                                               |
| MINIR4                        | 138  | 1ch       | 1.2.0       | plug            |                                               |
| MINIR4M                       | 138  | 1ch       | 1.2.0       | plug            |                                               |
| CK-BL602-4SW-HS(141)          | 141  | 4ch       | 1.6.1       | ---             |                                               |
| DW2-Wi-Fi-L                   | 154  | sensor    | 1000.2.1130 | ---             |                                               |
|                               | 160  | 1ch       |             |                 | Sonoff SwitchMan M5-1C                        |
|                               | 161  | 2ch       |             |                 | Sonoff SwitchMan M5-2C                        |
| M5-3C-120W                    | 162  | 3ch       | 1.2.0       | plug            | Sonoff SwitchMan M5-3C                        |
|                               | 165  | 2ch       |             | ???             | DualR3 Lite, without power consumption        |
| ZBBridge-P                    | 168  | bridge    | 3.0.0       | zigbee_gateway  |                                               |
|                               | 173  |           |             |                 | Sonoff L3-5M-P                                |
|                               | 174  | button    |             |                 | Sonoff R5 (6-key remote)                      |
|                               | 177  | button    |             |                 | Sonoff S-Mate                                 |
| THR316D                       | 181  | th        | 1.3.0       | th_plug         | Auto report every 5 sec                       |
| THR320D                       | 181  | th        | 1.3.0       | th_plug         | Auto report every 5 sec                       |
| CK-BL602-SWP1-01(182)         | 182  | pow       | 1.3.1       | ???             | Like S40, but without local protocol          |
| S40TPB                        | 182  | pow       | 1.4.1       | plug            | Sonoff S40                                    |
| POWCT                         | 190  | pow       | 1.3.1       | plug            | Support supply                                |
| POWR320D                      | 190  | pow       | 1.2.0       | plug            |                                               |
| S60TPF                        | 190  | pow       | 1.2.0       | plug            | Respond with current state to any lan request |
|                               | 195  | panel     |             |                 | NSPanel Pro                                   |
| T5-1C-86                      | 209  | 1ch       |             |                 | Sonoff TX ULTIMATE                            |
| T5-2C-86                      | 210  | 2ch       |             |                 | Sonoff TX ULTIMATE                            |
| T5-3C-86                      | 211  | 3ch       |             |                 | Sonoff TX ULTIMATE                            |
| T5-4C-86                      | 212  | 4ch       |             |                 | Sonoff TX ULTIMATE                            |
| CK-BL602-PCSW-01(225)         | 225  | 1ch       | 1.1.0       | plug            |                                               |
| CK-BL602-W102SW18-01(226)     | 226  | pow       | 1.2.1       | ---             |                                               |
| NSPanel120PB                  | 228  | panel     |             |                 | NSPanel Pro 120                               |
| CK-BK7238-W105SE10-01-HB(242) | 242  | sensor    | 1.0.0       |                 |                                               |
| ZbBridge-U                    | 243  | bridge    | 1.4.0       | zbbridgeu       |                                               |
| MINI-RBS                      | 258  | cover     | 1.0.2       | plug            |                                               |
| CK-BL602-SWP1-02(262)         | 262  | pow       | 1.0.0       | ???             |                                               |
| BASIC-1GS                     | 268  | 1ch       | 1.0.2       | plug            |                                               |
| MINI-2GS                      | 275  | 2ch       | 1.0.0       | plug            |                                               |
| S61STPF                       | 276  | pow       | 1.0.3       | ---             | Timeout on any local command!                 |
| MINI-DIM                      | 277  | light/pow | 1.1.2       | plug            |                                               |
| SNZB-03P                      | 7002 |           | 2.2.1       |                 |                                               |
| SNZB-04P                      | 7003 |           | 2.2.0       |                 |                                               |
| ZBMINIL2                      | 7004 |           | 1.0.14      |                 |                                               |
| ZBMicro                       | 7010 |           | 1.0.5       |                 |                                               |
| SNZB-02P                      | 7014 |           | 2.2.0       |                 |                                               |
| S60ZBTPF                      | 7032 | pow       | 2.0.2       | ---             |                                               |
| SNZB-02LD                     | 7033 |           | 1.1.0       |                 |                                               |
| SNZB-02DR2                    | 7038 |           | 1.0.2       |                 |                                               |
