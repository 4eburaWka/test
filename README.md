# PM970 BLE sender

Python-утилита для устройств **pm970** по аналогии с `com.bupin.data.CardSdkAgent` и `cn.manytag.tablecard.manager.selfDeveloped.BleManager.connectBle2()`.

## Что реализовано

| Модуль | Аналог в Android |
|--------|------------------|
| `packet_utils.py` | `a.a`, `a.b` — разбиение на пакеты по 242 байта |
| `card_sdk_agent.py` | `CardSdkAgent.getRefreshData()`, `refreshCallback()` |
| `image_utils.py` | загрузка Bitmap → ARGB pixels |
| `native_bridge.py` | `JniUtils.CreateImage`, `BleCallBack`, `ScanCallBack` |
| `ble_client.py` | `BaseTxManager` + Nordic UART UUID |
| `pm970_send.py` | CLI: файл → пакеты → BLE |

## Установка

```bash
cd scripts/pm970
pip install -r requirements.txt
```

## 1. Сборка Java-моста к native-библиотеке

Кодирование изображения выполняется в `libbluetoothhelper.so` (JNI). Сборка **не распаковывает classes.dex** — компилируются только JNI-заглушки `JniUtils` и `EncodeBridge.java`:

```bash
cd scripts/pm970/java
# Windows (cmd/PowerShell):
build.bat D:\path\to\TableCard.apk
# Linux/macOS:
./build.sh /path/to/tablecard.apk
```

Будет создан:
- `pm970-encoder.jar`
- `native/libbluetoothhelper.so` (извлекается из APK)

Требуется только **JDK** (`javac`, `jar`). Android SDK / d8 **не нужны**.

> **Важно:** `libbluetoothhelper.so` — ARM-библиотека Android. На Windows x64 `CreateImage` через Java не запустится; используйте Raspberry Pi / Termux или режим `--packets-file`.

## 2. Кодирование без отправки

```bash
python -m pm970.pm970_send \
  --apk D:/apk/tablecard.apk \
  --image-a D:/images/front.png \
  --width 800 --height 480 \
  --screen-code 1 \
  --dump-packets packets.hex
```

## 3. Отправка по Bluetooth

```bash
python -m pm970.pm970_send \
  --apk D:/apk/tablecard.apk \
  --address AA:BB:CC:DD:EE:FF \
  --image-a D:/images/front.png \
  --image-b D:/images/back.png \
  --screen-code 1
```

Или отправка заранее подготовленных пакетов:

```bash
python -m pm970.pm970_send \
  --apk D:/apk/tablecard.apk \
  --address AA:BB:CC:DD:EE:FF \
  --packets-file packets.hex
```

## Параметры экрана

- По умолчанию: **800×480** (`Constants.editWidth/editHight`)
- `--screen-code` — из scan data устройства (`CardDeviceInfo.screenCode`), обычно получают при первом сканировании в приложении

## BLE UUID (Nordic UART)

- Service: `6e400001-b5a3-f393-e0a9-e50e24dcca9e`
- Write:   `6e400002-b5a3-f393-e0a9-e50e24dcca9e`
- Notify:  `6e400003-b5a3-f393-e0a9-e50e24dcca9e`

## Переменные окружения

- `TABLECARD_APK` — путь к APK, если не указан `--apk`

## Протокол обмена

1. `CreateImage()` → очередь пакетов по 242 байта
2. Подключение BLE, подписка на notify
3. Отправка пакетов на write characteristic
4. Ответы устройства → `BleCallBack()` → новые пакеты или `REFRESH_END`

## Запуск из корня проекта

```bash
python -m scripts.pm970.pm970_send --help
```

или из `scripts/pm970`:

```bash
python -m pm970_send --help
```
