# Reverse Engineering: Stream Station (Mirabox Stream Dock)

## Aplicación analizada
- **Nombre**: Stream Station (by Mirabox/HotSpot)
- **Ruta**: `C:\Program Files (x86)\Stream Station\Stream Station.exe`
- **Proceso secundario**: `streamdockSwitchAudio.exe` (plugin nativo de audio)
- **Puerto WebSocket**: `127.0.0.1:23519`

---

## Dispositivo físico

| Campo | Valor |
|-------|-------|
| Fabricante | Mirabox / HotSpot |
| Nombre | "2.4G Wireless Receiver" (receptor USB) |
| VID | `0x3554` (13652) |
| PID | `0xFA09` (64009) |
| Revisión | `0x0102` |
| Clase | USB Composite Device |
| Driver | `usbccgp` (composite) |

### Interfaces USB

| Interface | Tipo | Función |
|-----------|------|---------|
| MI_00 | HID Keyboard | Pulsaciones de botones como teclas HID |
| MI_01 COL01 | HID Vendor-defined | Control principal del dispositivo, imágenes LCD |
| MI_01 COL02 | HID Consumer Control | Teclas multimedia |
| MI_01 COL03 | HID System Control | Teclas de sistema |
| MI_01 COL04 | HID Keyboard | Teclado adicional |
| MI_01 COL05 | HID Mouse | Encoders/knobs como rueda de ratón |
| MI_01 COL06 | HID Vendor-defined | Canal secundario vendor-specific |

---

## Arquitectura del software

```
Stream Station.exe (Qt5 + libcef/Chromium)
  ├── SDLibrary1.dll          ← Lógica principal (C++, Qt5)
  │     ├── USB via libusb-1.0.dll    → Comunicación con dispositivo
  │     ├── HID image transfer        → Envío de imágenes a LCD
  │     └── WebSocket server :23519   → Plugin API
  ├── plugins/*.sdPlugin      ← Plugins web (HTML/JS en Chromium)
  │     ├── com.hotspot.streamdock.*
  │     └── com.mirabox.streamdock.*
  └── streamdockSwitchAudio.exe ← Plugin nativo C++ (audio)
```

---

## Protocolo WebSocket (Plugin API)

### Compatible con Elgato Stream Deck SDK

La aplicación implementa **ambos** protocolos:
- `connectMiraBoxSDSocket(port, pluginUUID, registerEvent, info)`
- `connectElgatoStreamDeckSocket(port, pluginUUID, registerEvent, info)` ← ¡compatible!

### Lanzamiento de plugins
El backend lanza cada plugin con argumentos:
```
plugin_executable -port 23519 -pluginUUID <uuid> -registerEvent registerPlugin -info <json>
```

### Flujo de conexión
```
1. Plugin se conecta a ws://127.0.0.1:23519
2. Plugin envía:
   {"event": "registerPlugin", "uuid": "<pluginUUID>"}

3. Backend confirma y envía eventos:
   {"event": "deviceDidConnect", "device": "<deviceUUID>", "deviceInfo": {...}}
   {"event": "willAppear", "action": "...", "context": "...", "device": "...", "payload": {...}}

4. Usuario pulsa botón → backend envía:
   {"event": "keyDown", "action": "<uuid>", "context": "...", "device": "...",
    "payload": {"settings": {}, "coordinates": {"column": 0, "row": 0},
                "state": 0, "userDesiredState": 0, "isInMultiAction": false}}

5. Usuario suelta botón → backend envía:
   {"event": "keyUp", ...}
```

### Eventos del backend → plugin

| Evento | Descripción |
|--------|-------------|
| `keyDown` | Botón pulsado |
| `keyUp` | Botón soltado |
| `dialDown` | Encoder pulsado |
| `dialUp` | Encoder soltado |
| `dialRotate` | Encoder girado |
| `willAppear` | Acción aparece en pantalla |
| `willDisappear` | Acción desaparece |
| `deviceDidConnect` | Dispositivo conectado |
| `deviceDidDisconnect` | Dispositivo desconectado |
| `applicationDidLaunch` | App monitorizada arrancada |
| `applicationDidTerminate` | App terminada |
| `systemDidWakeUp` | Sistema despertado |
| `titleParametersDidChange` | Parámetros de título cambiados |
| `propertyInspectorDidAppear` | PI visible |
| `sendToPlugin` | Datos del PI al plugin |

### Comandos del plugin → backend

| Evento | Descripción |
|--------|-------------|
| `setImage` | Enviar imagen base64 a un botón |
| `setTitle` | Poner texto en botón |
| `showAlert` | Mostrar alerta (✗) |
| `showOk` | Mostrar OK (✓) |
| `getSettings` | Obtener configuración |
| `setSettings` | Guardar configuración |
| `getGlobalSettings` | Config global |
| `setGlobalSettings` | Guardar config global |
| `openUrl` | Abrir URL en navegador |
| `logMessage` | Escribir en log |
| `deviceBrightness` | Ajustar brillo (0-100) |

### Formato setImage
```json
{
  "event": "setImage",
  "context": "<button_context_uuid>",
  "payload": {
    "image": "data:image/png;base64,iVBORw0KGgo...",
    "target": 0
  }
}
```
- `target`: 0 = hardware + software, 1 = hardware, 2 = software

---

## Protocolo USB directo

### Lectura de botones (MI_00 HID Keyboard)
El dispositivo envía eventos HID keyboard estándar cuando se pulsan los botones físicos.
Cada botón está mapeado a una combinación de teclas (configurable desde la app).

### Lectura de botones (MI_01 COL01 Vendor HID)
Para eventos más detallados (incluyendo estado de encoders), se usa la interfaz vendor-defined.
Formato de reporte de entrada (estimado por análisis de DLL):
```
Byte 0: Report ID
Byte 1: Tipo de evento (0x01=keyDown, 0x02=keyUp, 0x03=dial, ...)
Byte 2: Índice del botón (0-based)
Byte 3: Estado (0=released, 1=pressed)
Byte 4-7: Datos adicionales (encoders: valor delta)
```

### Envío de imágenes LCD (MI_01 COL01/COL06)
Imágenes enviadas como HID output reports en chunks. Formato estimado:
```
Byte 0: Report ID (0x02 para imágenes)
Byte 1: Índice del botón (0-based)
Byte 2: Número de chunk (0-based)
Byte 3: Chunk final (1 si es el último)
Byte 4-5: Longitud del chunk (little-endian)
Byte 6+: Datos JPEG (hasta ~1010 bytes por chunk)
```
Imágenes en formato JPEG, típicamente 72x72 o 96x96 píxeles.

---

## Manifest de plugins (formato .sdPlugin)

Compatible con Elgato Stream Deck SDK:
```json
{
  "SDKVersion": 1,
  "Actions": [
    {
      "UUID": "com.example.myplugin.myaction",
      "Name": "My Action",
      "States": [{"Image": "images/action"}],
      "Controllers": ["Keypad", "Information"],
      "PropertyInspectorPath": "index.html"
    }
  ],
  "CodePath": "plugin/index.html",
  "Author": "...",
  "Name": "My Plugin",
  "Category": "My Category",
  "Version": "1.0",
  "OS": [{"Platform": "windows", "MinimumVersion": "7"},
          {"Platform": "mac", "MinimumVersion": "10.11"}]
}
```

---

## Implementación en Linux/NixOS

### Acceso al dispositivo
```bash
# Verificar dispositivo
lsusb | grep "3554:fa09"
# → Bus 001 Device 004: ID 3554:fa09 ...

# Permisos udev
echo 'SUBSYSTEM=="hidraw", ATTRS{idVendor}=="3554", ATTRS{idProduct}=="fa09", MODE="0660", GROUP="plugdev"' \
  > /etc/udev/rules.d/99-stream-station.rules
```

### Interfaces en Linux
```
/dev/hidraw0  → MI_01 COL01 (vendor-defined) ← para imágenes y control
/dev/hidraw1  → MI_01 COL02 (consumer control)
/dev/hidraw2  → MI_01 COL03 (system control)
/dev/hidraw3  → MI_01 COL04 (keyboard)
/dev/hidraw4  → MI_01 COL05 (mouse/dial)
/dev/hidraw5  → MI_01 COL06 (vendor-defined)
```

### Dependencias Python
```
hid           → acceso a dispositivos HID (python-hidapi)
websockets    → servidor WebSocket para plugin API (compatible Stream Deck)
Pillow        → procesamiento de imágenes para LCD
tomllib       → configuración TOML (Python 3.11+ built-in)
```
