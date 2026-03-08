# Protocolo USB — Stream Station (VID:3554 PID:FA09)

## Identificación del dispositivo
```
Vendor ID  : 0x3554 (Mirabox/HotSpot)
Product ID : 0xFA09
Revision   : 0x0102
Class      : 0x00 (device-level)
Subclass   : 0x00
Protocol   : 0x00
BusDesc    : "2.4G Wireless Receiver"
```

---

## Interfaces USB (composite device)

### Interface 0 (MI_00) — HID Keyboard
- **Usage Page**: Generic Desktop (0x01)
- **Usage**: Keyboard (0x06)
- **Función**: Botones físicos emulando teclado estándar
- **Endpoint IN**: Interrupt, 8 bytes, 10ms polling
- **Lectura en Linux**: `/dev/input/eventX` o `evdev`

```
Reporte HID estándar de teclado (8 bytes):
Byte 0: Modifier keys (Ctrl/Shift/Alt/GUI)
Byte 1: Reserved (0x00)
Byte 2-7: Keycodes (hasta 6 teclas simultáneas)
```

### Interface 1 (MI_01) — Multiple HID Collections

#### COL01 — Vendor Defined (control principal)
- **Usage Page**: Vendor (0xFF00 o similar)
- **Función**: Imágenes LCD, estado del dispositivo
- **HID Report IDs**: 0x01 (input), 0x02 (output para imágenes)

#### COL02 — Consumer Control
- **Usage Page**: Consumer (0x0C)
- **Función**: Teclas multimedia (play/pause, volumen, etc.)

#### COL03 — System Control
- **Usage Page**: Generic Desktop (0x01)
- **Usage**: System Control (0x80)
- **Función**: Power, sleep, wake

#### COL04 — Keyboard (secundario)
- **Usage Page**: Generic Desktop (0x01)
- **Usage**: Keyboard (0x06)
- **Función**: Teclado adicional para funciones especiales

#### COL05 — Mouse / Encoder
- **Usage Page**: Generic Desktop (0x01)
- **Usage**: Mouse (0x02)
- **Función**: Encoders/knobs como rueda del ratón

#### COL06 — Vendor Defined (secundario)
- **Función**: Canal auxiliar vendor-specific

---

## Protocolo de imágenes LCD

### Formato de imagen
- **Formato**: JPEG
- **Tamaño**: 72×72 píxeles (estimado, puede variar según modelo)
- **Calidad JPEG**: ~85%

### Envío de imagen (HID Output Reports)
Las imágenes se envían en chunks mediante HID output reports a la interfaz COL01:

```
Chunk header (estimado, basado en análisis de SDLibrary1.dll):
Byte  0   : Report ID = 0x02
Byte  1   : Índice del botón (0-based)
Byte  2   : Número de chunk (0-based)
Byte  3   : Flag "último chunk" (0x01 si es el último, 0x00 si no)
Byte  4-5 : Longitud de datos en este chunk (uint16 little-endian)
Byte  6-N : Datos JPEG del chunk (max ~1010 bytes)
```

### Confirmación
Después de enviar el último chunk, el dispositivo puede responder con un report de confirmación.

---

## Protocolo de lectura de botones

### Via HID Keyboard (MI_00) — método simple
Los botones están configurados como teclas de teclado estándar.
Se puede leer con cualquier biblioteca HID o directamente con `evdev` en Linux.

### Via Vendor HID (MI_01 COL01) — método completo
Para información más detallada sobre qué botón fue pulsado, encoder state, etc.

```
Input Report (estimado):
Byte 0: Report ID = 0x01
Byte 1: Tipo evento
        0x00 = ningún evento
        0x01 = botón pulsado
        0x02 = botón soltado
        0x03 = encoder girado
        0x04 = encoder pulsado
Byte 2: Índice del botón o encoder (0-based)
Byte 3: Estado (1=pressed, 0=released) o delta del encoder (signed byte)
Byte 4-7: Datos adicionales
```

---

## Comandos de control del dispositivo

### Brillo de pantalla
```
Report ID: 0x08 (estimado)
Byte 1: Valor de brillo (0-100)
```

### Vibración/feedback háptico
Si el dispositivo lo soporta:
```
Report ID: 0x0B (estimado)
Byte 1: Patrón de vibración (0-7)
```

---

## Herramientas de análisis

Para obtener el descriptor HID completo en Linux:
```bash
# Ver descriptor HID del dispositivo
sudo usbhid-dump -d 3554:fa09

# O con hidrd-convert
sudo usbhid-dump -d 3554:fa09 | grep -v : | xxd -r -p | hidrd-convert -o xml

# Monitor de eventos HID raw
sudo python3 -c "
import hid
dev = hid.device()
dev.open(0x3554, 0xfa09)
dev.set_nonblocking(0)
while True:
    data = dev.read(64)
    if data:
        print(' '.join(f'{b:02x}' for b in data))
"
```

---

## Notas de compatibilidad

El dispositivo es compatible con el **Elgato Stream Deck SDK** a nivel de protocolo WebSocket.
Las diferencias principales con un Stream Deck original son:
1. VID/PID diferente (0x3554:0xFA09 vs 0x0fd9:*)
2. Posible tamaño de imagen diferente
3. Posible formato de chunk diferente para LCD

Proyectos de referencia para protocolo Stream Deck:
- `python-elgato-streamdeck` (Python, MIT)
- `streamdeck-ui` (Python/Qt, GPL)
- `deckmaster` (Go, Apache)
