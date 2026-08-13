# hardware-reversing

Reverse engineering y drivers en espacio de usuario para hardware de PC sin soporte oficial en Linux y macOS: pantallas AIO, iluminación RGB de placa base y controladoras de iluminación USB.

Todo el trabajo parte de capturas de tráfico USB/HID sobre los drivers propietarios de Windows, decodificación del protocolo, y reimplementación desde cero en Python.

## Dispositivos cubiertos

| Dispositivo | Qué es | Protocolo | Linux | macOS | NixOS |
|---|---|---|---|---|---|
| **HydroTemp AIO** | Pantalla del disipador líquido (CPU, temperaturas, RPM) | HID `5131:2007`, reportes de 64 B | ✅ producción | ✅ | ✅ |
| **RGB Fusion** | Iluminación de placa base Gigabyte (ITE8297) | HID vendor, DLL reversada | ✅ | ✅ | ✅ |
| **Stream Station** | Controladora de iluminación USB | USB raw, protocolo propio | — | — | ✅ |

## Documentación del reverse engineering

Es la parte más reutilizable del repositorio: sirve aunque no uses este código.

- [`docs/hydrotemp-aio/AIO-Display-Protocol-Analysis.md`](docs/hydrotemp-aio/AIO-Display-Protocol-Analysis.md) — análisis completo del protocolo de la pantalla (24 KB)
- [`docs/hydrotemp-aio/PROTOCOL_ANALYSIS.md`](docs/hydrotemp-aio/PROTOCOL_ANALYSIS.md) — estructura de los reportes HID
- [`docs/hydrotemp-aio/IL_SENDDATA2_DECODED.md`](docs/hydrotemp-aio/IL_SENDDATA2_DECODED.md) — decodificación de `IL_SENDDATA2`
- [`docs/rgb-fusion/ANALYSIS.md`](docs/rgb-fusion/ANALYSIS.md) — análisis de RGB Fusion
- [`docs/rgb-fusion/DLL_EXPORTS.md`](docs/rgb-fusion/DLL_EXPORTS.md) — exports de la DLL propietaria
- [`docs/rgb-fusion/ENUMS_AND_MODES.md`](docs/rgb-fusion/ENUMS_AND_MODES.md) — modos de efecto y enumeraciones
- [`docs/stream-station/USB_PROTOCOL.md`](docs/stream-station/USB_PROTOCOL.md) — protocolo USB de Stream Station

## Hallazgos destacados

- El display se expone como **`VID 0x5131 / PID 0x2007`**, no como el receptor inalámbrico CX que aparece primero al enumerar. Hay que seleccionar la interfaz HID de vendor por `usage_page` (`0xFF02`) o el kernel devuelve `EPIPE` al escribir sobre el teclado.
- Las escrituras requieren un buffer de **65 bytes** (64 de carga útil + 1 de prefijo de `hidapi`), replicando la transferencia raw de CyUSB en Windows.
- En el reporte de estado, **`buf[9]` es la temperatura de CPU**, no el máximo por hilo como parecía al principio. Y `buf[6]` (potencia de GPU) debe ir a 0 para que el display muestre la temperatura real de CPU.

## Estructura

```
docs/                     Análisis de protocolo por dispositivo
hydrotemp-aio/
  monitor.py              ← implementación canónica (Linux, en producción)
  linux/                  Unidades systemd y scripts de arranque
  macos/                  monitor_macos.py, LaunchAgent e instaladores PKG/DMG
  nixos/                  flake.nix y variante NixOS
rgb-fusion/               rgb_fusion.py, controlador ITE8297, flake
stream-station/           stream_station.py, flake
_originales/              READMEs de los 5 repos originales
```

## Qué versión usar

`hydrotemp-aio/monitor.py` es la **canónica**: es la que corre en producción sobre CachyOS y la más reciente (mayo 2026). Frente a la variante de NixOS añade el escaneo de `fan*_input` en lugar de solo `fan1_input`, y distingue "ventilador parado" (0 RPM) de "no se encontró ventilador".

`hydrotemp-aio/macos/monitor_macos.py` es una implementación aparte, no una copia: macOS usa otras APIs de sistema para leer sensores.

## Procedencia

Este repositorio unifica cinco repos anteriores **conservando su historial completo** (41 commits). El recorrido del reverse engineering está en los mensajes de commit y es parte del valor:

| Repo original | Aporte |
|---|---|
| `hydrotemp-rgb-arch` | Implementación canónica de Linux (mayo 2026) |
| `Datos-xyz-hydrotemp` | Protocolo real del display, docs de reversing |
| `hydrotemp-aio-mac` | Puerto a macOS, instaladores, controlador ITE8297 |
| `Datos-RGB-Fusion-nixOS` | Reversing de RGB Fusion + módulo NixOS |
| `Datos-Stream-Station-nixos` | Reversing de Stream Station + módulo NixOS |

## Licencia

MIT — ver [LICENSE](LICENSE).
