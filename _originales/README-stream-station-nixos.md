# Stream Station NixOS

Daemon para controlar el **Mirabox Stream Dock** (vendido como "Stream Station") en NixOS/Linux.

## Dispositivo

| Campo | Valor |
|-------|-------|
| Fabricante | Mirabox / HotSpot |
| Nombre | Stream Station / Stream Dock |
| VID:PID | `0x3554:0xFA09` |
| Interfaz | USB HID (composite) |
| Compatibilidad | Elgato Stream Deck SDK (WebSocket) |

El dispositivo tiene botones físicos con pantalla LCD individual. Es similar al Elgato Stream Deck y usa un protocolo compatible con el Stream Deck SDK para la comunicación con plugins.

## Arquitectura

```
stream_station.py
  ├── StreamStationDevice    → HID USB directo (hidapi)
  │     ├── read_event()     → leer pulsaciones de botones
  │     ├── send_image()     → enviar JPEG al LCD del botón
  │     └── set_brightness() → ajustar brillo
  ├── StreamStationDaemon    → bucle principal
  │     ├── _read_loop()     → leer HID y ejecutar comandos
  │     └── _ws_server()     → WebSocket compatible Stream Deck SDK
  └── CLI                    → list / daemon / set-image / brightness / monitor
```

## Instalación en NixOS

### Opción 1: Flake (recomendado)

Añade a tu `flake.nix`:
```nix
{
  inputs.stream-station.url = "github:Rene-Kuhm/Datos-Stream-Station-nixos";

  outputs = { nixpkgs, stream-station, ... }: {
    nixosConfigurations.mi-maquina = nixpkgs.lib.nixosSystem {
      modules = [
        stream-station.nixosModules.default
        {
          services.streamStation = {
            enable     = true;
            brightness = 70;
            wsServer   = false;  # activar para compatibilidad con plugins SD
          };
          # Añadir usuario al grupo plugdev
          users.users.tu_usuario.extraGroups = [ "plugdev" ];
        }
      ];
    };
  };
}
```

### Opción 2: nix run (sin instalar)
```bash
nix run github:Rene-Kuhm/Datos-Stream-Station-nixos -- list
nix run github:Rene-Kuhm/Datos-Stream-Station-nixos -- daemon
```

### Opción 3: Instalación manual

1. Instalar dependencias:
```bash
pip install hid pillow websockets
```

2. Reglas udev (como root):
```bash
echo 'SUBSYSTEM=="hidraw", ATTRS{idVendor}=="3554", ATTRS{idProduct}=="fa09", MODE="0660", GROUP="plugdev", TAG+="uaccess"' \
  | sudo tee /etc/udev/rules.d/99-stream-station.rules
sudo udevadm control --reload-rules
sudo usermod -aG plugdev $USER
```

3. Ejecutar:
```bash
python3 stream_station.py daemon --config config.toml
```

## Configuración

Copia `config.example.toml` a `~/.config/stream-station/config.toml`:

```toml
brightness = 70
ws_server  = false
ws_port    = 23519

[buttons.0]
label   = "Terminal"
color   = "#1a1a2e"
command = "kitty &"

[buttons.1]
label   = "Firefox"
color   = "#ff6600"
command = "firefox &"

[buttons.5]
label   = "Play/Pause"
color   = "#ffffff"
command = "playerctl play-pause"

[buttons.6]
icon    = "/home/user/.config/stream-station/icons/obs.png"
command = "obs &"
```

### Opciones por botón

| Opción | Descripción |
|--------|-------------|
| `label` | Nombre descriptivo (solo documentación) |
| `icon` | Ruta a imagen PNG/JPG (se redimensiona a 72×72) |
| `color` | Color de fondo hex si no hay icono (`#RRGGBB`) |
| `command` | Comando al **pulsar** el botón |
| `on_release` | Comando al **soltar** el botón |

## Comandos CLI

```bash
# Listar dispositivos conectados
stream-station list

# Iniciar daemon
stream-station daemon

# Iniciar daemon con servidor WebSocket (para plugins Stream Deck)
stream-station daemon --ws

# Enviar imagen a un botón
stream-station set-image 0 /path/to/icon.png

# Color sólido en botón
stream-station set-color 3 "#ff0000"

# Ajustar brillo
stream-station brightness 80

# Monitorear eventos HID en bruto (debug)
stream-station monitor
```

## Servidor WebSocket compatible Stream Deck SDK

Activando `ws_server = true`, el daemon expone un servidor WebSocket en el puerto 23519 que implementa el protocolo Elgato Stream Deck SDK. Esto permite usar plugins de terceros compatibles con Stream Deck.

### Eventos soportados (backend → plugin)
- `deviceDidConnect` / `deviceDidDisconnect`
- `keyDown` / `keyUp`
- `dialDown` / `dialUp` / `dialRotate`
- `willAppear` / `willDisappear`

### Comandos soportados (plugin → backend)
- `setImage` — enviar imagen base64 al LCD del botón
- `deviceBrightness` — ajustar brillo
- `getSettings` / `setSettings`
- `getGlobalSettings` / `setGlobalSettings`
- `openUrl`
- `logMessage`

## Layout de botones

Numeración de izquierda a derecha, fila por fila (modelo 3×5):
```
[0]  [1]  [2]  [3]  [4]
[5]  [6]  [7]  [8]  [9]
[10] [11] [12] [13] [14]
```

## Permisos requeridos

- **Grupo `plugdev`**: acceso a `/dev/hidraw*` (dispositivos HID)
- El servicio systemd del flake lo configura automáticamente

## Herramientas de diagnóstico

```bash
# Verificar que el dispositivo está conectado
lsusb | grep "3554:fa09"

# Ver interfaces HID del dispositivo
ls -la /dev/hidraw*

# Monitorear eventos en bruto
stream-station monitor

# Ver descriptor HID completo
sudo usbhid-dump -d 3554:fa09
```

## Reverse Engineering

Ver carpeta `reverse-engineering/` para documentación del protocolo:
- `ANALYSIS.md` — arquitectura completa del software Windows
- `USB_PROTOCOL.md` — protocolo USB/HID del dispositivo

### Resumen técnico
- El dispositivo es un USB composite con 2 interfaces: keyboard (MI_00) y multi-colección HID (MI_01)
- La app Windows usa `libusb-1.0.dll` para comunicación USB directa
- Implementa protocolo **Elgato Stream Deck SDK** vía WebSocket (confirmado por strings en binario)
- Las imágenes se envían como JPEG 72×72 en chunks HID de ~1010 bytes

## Compatibilidad

| Modelo | VID:PID | Estado |
|--------|---------|--------|
| Stream Station (SD+ style) | `3554:FA09` | ✓ Testado |
| Otros modelos Mirabox | `3554:*` | ? Sin confirmar |

## Licencia

MIT — Ver `LICENSE`
