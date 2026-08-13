#!/usr/bin/env python3
"""
Stream Station NixOS Daemon
Mirabox Stream Dock (VID:0x3554 PID:0xFA09) — Compatible con Elgato Stream Deck SDK

Arquitectura:
  - Lee eventos de botones via HID (interfaz MI_01 COL01 vendor-defined)
  - Envía imágenes JPEG a botones LCD via HID output reports
  - Ejecuta comandos shell configurados en TOML al pulsar botones
  - Servidor WebSocket opcional (puerto 23519) compatible con Stream Deck SDK

Uso:
  stream_station list           → listar dispositivos
  stream_station daemon         → iniciar daemon
  stream_station set-image N img.png → enviar imagen al botón N
  stream_station set-title N "Texto" → poner título en botón N
  stream_station brightness N   → ajustar brillo (0-100)
"""

import sys
import os
import io
import time
import json
import asyncio
import logging
import signal
import struct
import subprocess
import threading
import tomllib
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

try:
    import hid
except ImportError:
    print("ERROR: instala python-hid: pip install hid", file=sys.stderr)
    sys.exit(1)

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import websockets
    import websockets.server
    HAS_WS = True
except ImportError:
    HAS_WS = False

# ─── Constantes del dispositivo ───────────────────────────────────────────────

VENDOR_ID  = 0x3554
PRODUCT_ID = 0xFA09

# Tamaño de imagen del botón LCD (JPEG 72×72)
IMG_W = 72
IMG_H = 72

# Tamaño máximo de datos por chunk HID
IMG_CHUNK_SIZE = 1010

# Report IDs (obtenidos por análisis de SDLibrary1.dll)
REPORT_INPUT   = 0x01   # Input: eventos de botones
REPORT_IMAGE   = 0x02   # Output: datos de imagen LCD
REPORT_BRIGHT  = 0x08   # Output: brillo de pantalla

# HID read timeout (ms)
HID_TIMEOUT = 100

# Puerto WebSocket compatible con Stream Deck SDK
WS_PORT = 23519

# ─── Configuración ────────────────────────────────────────────────────────────

@dataclass
class ButtonConfig:
    key:         int
    label:       str = ""
    icon:        str = ""
    command:     str = ""
    on_release:  str = ""
    color:       str = "#000000"      # color de fondo si no hay icono

@dataclass
class Config:
    brightness:  int = 70
    ws_server:   bool = False
    ws_port:     int = WS_PORT
    buttons:     dict[int, ButtonConfig] = field(default_factory=dict)

    @classmethod
    def from_file(cls, path: Path) -> "Config":
        if not path.exists():
            return cls()
        with open(path, "rb") as f:
            raw = tomllib.load(f)

        cfg = cls(
            brightness = raw.get("brightness", 70),
            ws_server  = raw.get("ws_server", False),
            ws_port    = raw.get("ws_port", WS_PORT),
        )
        for key, btn in raw.get("buttons", {}).items():
            idx = int(key)
            cfg.buttons[idx] = ButtonConfig(
                key        = idx,
                label      = btn.get("label", ""),
                icon       = btn.get("icon", ""),
                command    = btn.get("command", ""),
                on_release = btn.get("on_release", ""),
                color      = btn.get("color", "#000000"),
            )
        return cfg

# ─── Controlador del dispositivo ─────────────────────────────────────────────

class StreamStationDevice:
    """Comunicación directa con el dispositivo via HID."""

    def __init__(self):
        self._dev: Optional[hid.device] = None
        self._lock = threading.Lock()

    def open(self) -> bool:
        """Abre el dispositivo HID. Devuelve True si exitoso."""
        for info in hid.enumerate(VENDOR_ID, PRODUCT_ID):
            # Buscar la interfaz vendor-defined (usage_page >= 0xFF00)
            if info.get("usage_page", 0) >= 0xFF00:
                try:
                    dev = hid.device()
                    dev.open_path(info["path"])
                    dev.set_nonblocking(False)
                    self._dev = dev
                    logging.info(
                        "Dispositivo abierto: %s (path=%s)",
                        info.get("product_string", "Stream Station"),
                        info["path"],
                    )
                    return True
                except OSError as e:
                    logging.warning("No se pudo abrir %s: %s", info["path"], e)
                    continue

        # Fallback: abrir por VID/PID sin filtrar interfaz
        try:
            dev = hid.device()
            dev.open(VENDOR_ID, PRODUCT_ID)
            dev.set_nonblocking(False)
            self._dev = dev
            logging.info("Dispositivo abierto (fallback VID:PID)")
            return True
        except OSError as e:
            logging.error("No se pudo abrir el dispositivo: %s", e)
            return False

    def close(self):
        if self._dev:
            try:
                self._dev.close()
            except Exception:
                pass
            self._dev = None

    def is_open(self) -> bool:
        return self._dev is not None

    def read_event(self, timeout_ms: int = HID_TIMEOUT) -> Optional[bytes]:
        """Lee un evento HID. Devuelve bytes o None si timeout."""
        if not self._dev:
            return None
        try:
            with self._lock:
                data = self._dev.read(64, timeout_ms)
            if data:
                return bytes(data)
        except OSError as e:
            logging.error("Error leyendo HID: %s", e)
            self._dev = None
        return None

    def send_image(self, button_index: int, jpeg_data: bytes) -> bool:
        """Envía imagen JPEG al botón LCD especificado."""
        if not self._dev:
            return False

        total   = len(jpeg_data)
        offset  = 0
        chunk_n = 0

        while offset < total:
            chunk = jpeg_data[offset : offset + IMG_CHUNK_SIZE]
            is_last = (offset + len(chunk)) >= total

            # Header: Report ID, button index, chunk num, last flag, length (2 bytes)
            header = struct.pack("<BBBBB",
                REPORT_IMAGE,
                button_index & 0xFF,
                chunk_n & 0xFF,
                0x01 if is_last else 0x00,
                len(chunk) & 0xFF,
            ) + struct.pack("<B", (len(chunk) >> 8) & 0xFF)

            payload = header + chunk
            # Rellenar hasta 1024 bytes con ceros
            payload = payload.ljust(1024, b'\x00')

            try:
                with self._lock:
                    self._dev.write(list(payload))
            except OSError as e:
                logging.error("Error enviando imagen chunk %d: %s", chunk_n, e)
                return False

            offset  += len(chunk)
            chunk_n += 1

        return True

    def set_brightness(self, value: int) -> bool:
        """Ajusta el brillo de la pantalla (0-100)."""
        if not self._dev:
            return False
        value = max(0, min(100, value))
        payload = bytes([REPORT_BRIGHT, value]) + b'\x00' * 30
        try:
            with self._lock:
                self._dev.write(list(payload))
            return True
        except OSError as e:
            logging.error("Error ajustando brillo: %s", e)
            return False

    def send_solid_color(self, button_index: int, r: int, g: int, b: int) -> bool:
        """Envía un color sólido al botón (genera JPEG internamente)."""
        if not HAS_PIL:
            logging.warning("Pillow no disponible, no se puede generar imagen")
            return False
        img = Image.new("RGB", (IMG_W, IMG_H), (r, g, b))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return self.send_image(button_index, buf.getvalue())

    def send_image_file(self, button_index: int, path: str) -> bool:
        """Carga y envía una imagen desde archivo."""
        if not HAS_PIL:
            try:
                with open(path, "rb") as f:
                    return self.send_image(button_index, f.read())
            except OSError as e:
                logging.error("Error leyendo %s: %s", path, e)
                return False

        try:
            img = Image.open(path).convert("RGB").resize(
                (IMG_W, IMG_H), Image.LANCZOS
            )
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return self.send_image(button_index, buf.getvalue())
        except Exception as e:
            logging.error("Error procesando imagen %s: %s", path, e)
            return False

# ─── Parser de eventos HID ────────────────────────────────────────────────────

@dataclass
class ButtonEvent:
    button:  int
    pressed: bool
    encoder_delta: int = 0   # solo si es encoder

def parse_event(data: bytes) -> Optional[ButtonEvent]:
    """
    Parsea un reporte HID del dispositivo.
    Formato estimado (vendor HID):
      Byte 0: Report ID
      Byte 1: Tipo (0x01=down, 0x02=up, 0x03=encoder)
      Byte 2: Índice botón
      Byte 3: Estado / delta
    """
    if len(data) < 4:
        return None

    report_id = data[0]
    etype     = data[1]
    index     = data[2]
    state     = data[3]

    if report_id != REPORT_INPUT:
        return None

    if etype == 0x01:
        return ButtonEvent(button=index, pressed=True)
    elif etype == 0x02:
        return ButtonEvent(button=index, pressed=False)
    elif etype == 0x03:
        delta = struct.unpack("b", bytes([state]))[0]
        return ButtonEvent(button=index, pressed=False, encoder_delta=delta)

    return None

# ─── Daemon principal ─────────────────────────────────────────────────────────

class StreamStationDaemon:
    def __init__(self, config: Config):
        self.config   = config
        self.device   = StreamStationDevice()
        self._running = False
        self._ws_clients: set = set()

    def start(self):
        """Iniciar el daemon."""
        logging.info("Iniciando Stream Station daemon...")

        if not self.device.open():
            logging.error("No se encontró el dispositivo VID:%04x PID:%04x",
                         VENDOR_ID, PRODUCT_ID)
            sys.exit(1)

        self.device.set_brightness(self.config.brightness)
        self._apply_button_icons()

        self._running = True

        if self.config.ws_server and HAS_WS:
            ws_thread = threading.Thread(
                target=self._run_ws_server, daemon=True
            )
            ws_thread.start()

        try:
            self._read_loop()
        finally:
            self.device.close()

    def _apply_button_icons(self):
        """Cargar imágenes/colores iniciales en todos los botones configurados."""
        for idx, btn in self.config.buttons.items():
            if btn.icon:
                self.device.send_image_file(idx, btn.icon)
            elif btn.color and btn.color != "#000000":
                r, g, b = _hex_to_rgb(btn.color)
                self.device.send_solid_color(idx, r, g, b)

    def _read_loop(self):
        """Loop principal de lectura de eventos HID."""
        logging.info("Escuchando eventos del dispositivo...")
        reconnect_delay = 1.0

        while self._running:
            if not self.device.is_open():
                logging.info("Intentando reconectar en %.1fs...", reconnect_delay)
                time.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 30.0)
                if self.device.open():
                    reconnect_delay = 1.0
                    self._apply_button_icons()
                continue

            data = self.device.read_event(timeout_ms=200)
            if not data:
                continue

            reconnect_delay = 1.0
            event = parse_event(data)
            if event:
                self._handle_event(event)

    def _handle_event(self, event: ButtonEvent):
        """Procesar un evento de botón."""
        if event.encoder_delta:
            logging.debug("Encoder %d: delta=%+d", event.button, event.encoder_delta)
            return

        state = "pulsado" if event.pressed else "soltado"
        logging.debug("Botón %d %s", event.button, state)

        btn = self.config.buttons.get(event.button)
        if not btn:
            return

        if event.pressed and btn.command:
            _run_command(btn.command)
        elif not event.pressed and btn.on_release:
            _run_command(btn.on_release)

    # ── WebSocket Server (compatible Stream Deck SDK) ──────────────────────

    def _run_ws_server(self):
        """Ejecutar servidor WebSocket en hilo separado."""
        async def _main():
            logging.info("Servidor WebSocket en ws://127.0.0.1:%d", self.config.ws_port)
            async with websockets.serve(self._ws_handler, "127.0.0.1",
                                        self.config.ws_port):
                await asyncio.Future()  # run forever

        asyncio.run(_main())

    async def _ws_handler(self, websocket):
        """Manejar conexión de plugin WebSocket."""
        self._ws_clients.add(websocket)
        plugin_uuid = None
        try:
            # Enviar info del dispositivo al conectar
            await websocket.send(json.dumps({
                "event": "deviceDidConnect",
                "device": "stream-station-nixos",
                "deviceInfo": {
                    "type": 7,
                    "size": {"columns": 5, "rows": 3},
                    "name": "Stream Station",
                }
            }))

            async for raw in websocket:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                event = msg.get("event", "")
                logging.debug("WS← %s", event)

                if event == "registerPlugin":
                    plugin_uuid = msg.get("uuid", "")
                    logging.info("Plugin registrado: %s", plugin_uuid)

                elif event == "setImage":
                    ctx  = msg.get("context", "")
                    payload = msg.get("payload", {})
                    img_data = payload.get("image", "")
                    if img_data.startswith("data:"):
                        img_data = img_data.split(",", 1)[-1]
                    btn_idx = _context_to_button(ctx)
                    if btn_idx >= 0 and img_data:
                        import base64
                        raw_img = base64.b64decode(img_data)
                        self.device.send_image(btn_idx, raw_img)

                elif event == "setTitle":
                    # Ignorar en hardware (solo para UI de la app)
                    pass

                elif event == "deviceBrightness":
                    value = msg.get("payload", {}).get("brightness", 70)
                    self.device.set_brightness(value)

                elif event in ("getSettings", "getGlobalSettings"):
                    await websocket.send(json.dumps({
                        "event": "didReceiveSettings" if event == "getSettings"
                                 else "didReceiveGlobalSettings",
                        "context": msg.get("context", ""),
                        "payload": {"settings": {}}
                    }))

                elif event == "logMessage":
                    logging.info("[Plugin] %s",
                                 msg.get("payload", {}).get("message", ""))

                elif event == "openUrl":
                    url = msg.get("payload", {}).get("url", "")
                    if url:
                        _run_command(f"xdg-open {url!r}")

        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._ws_clients.discard(websocket)

    async def _broadcast_event(self, event_data: dict):
        """Enviar evento a todos los plugins conectados."""
        if not self._ws_clients:
            return
        msg = json.dumps(event_data)
        await asyncio.gather(
            *(ws.send(msg) for ws in self._ws_clients),
            return_exceptions=True
        )

# ─── Utilidades ───────────────────────────────────────────────────────────────

def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) == 6:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return 0, 0, 0

def _run_command(cmd: str):
    """Ejecutar comando shell en background."""
    logging.info("Ejecutando: %s", cmd)
    try:
        subprocess.Popen(
            cmd, shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        logging.error("Error ejecutando '%s': %s", cmd, e)

def _context_to_button(context: str) -> int:
    """Extraer índice de botón desde context UUID (heurística simple)."""
    try:
        parts = context.split("-")
        return int(parts[-1]) if parts else -1
    except (ValueError, IndexError):
        return -1

def _list_devices():
    """Listar dispositivos Stream Station conectados."""
    found = False
    for info in hid.enumerate(VENDOR_ID, PRODUCT_ID):
        found = True
        print(f"Dispositivo encontrado:")
        print(f"  Path:         {info.get('path', 'N/A')}")
        print(f"  Manufacturer: {info.get('manufacturer_string', 'N/A')}")
        print(f"  Product:      {info.get('product_string', 'N/A')}")
        print(f"  Serial:       {info.get('serial_number', 'N/A')}")
        print(f"  Usage Page:   0x{info.get('usage_page', 0):04X}")
        print(f"  Usage:        0x{info.get('usage', 0):04X}")
        print(f"  Interface:    {info.get('interface_number', -1)}")
        print()
    if not found:
        print(f"No se encontró ningún dispositivo VID:0x{VENDOR_ID:04X} "
              f"PID:0x{PRODUCT_ID:04X}")
        print("Verifica que el dispositivo esté conectado y tengas permisos")
        print("(añade tu usuario al grupo 'plugdev' o ejecuta con sudo)")

# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Stream Station NixOS daemon/CLI"
    )
    parser.add_argument(
        "--config", "-c",
        type=Path,
        default=Path(os.environ.get(
            "STREAM_STATION_CONFIG",
            os.path.expanduser("~/.config/stream-station/config.toml")
        )),
        help="Ruta al archivo de configuración TOML"
    )
    parser.add_argument(
        "--log-level", "-l",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )

    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("list", help="Listar dispositivos conectados")

    sub_daemon = subparsers.add_parser("daemon", help="Iniciar daemon")
    sub_daemon.add_argument("--ws", action="store_true",
                            help="Activar servidor WebSocket")

    sub_img = subparsers.add_parser("set-image",
                                     help="Enviar imagen a un botón")
    sub_img.add_argument("button", type=int, help="Índice del botón (0-based)")
    sub_img.add_argument("image", help="Ruta a la imagen")

    sub_title = subparsers.add_parser("set-title",
                                       help="Poner texto en un botón")
    sub_title.add_argument("button", type=int)
    sub_title.add_argument("title")

    sub_bright = subparsers.add_parser("brightness",
                                        help="Ajustar brillo (0-100)")
    sub_bright.add_argument("value", type=int)

    sub_color = subparsers.add_parser("set-color",
                                       help="Color sólido en botón")
    sub_color.add_argument("button", type=int)
    sub_color.add_argument("color", help="Color en hex (#RRGGBB)")

    sub_monitor = subparsers.add_parser("monitor",
                                         help="Monitorear eventos HID en bruto")

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if args.command == "list" or args.command is None:
        _list_devices()
        return

    config = Config.from_file(args.config)

    if args.command == "daemon":
        if args.ws:
            config.ws_server = True
        daemon = StreamStationDaemon(config)

        def _sigterm(sig, frame):
            daemon._running = False

        signal.signal(signal.SIGTERM, _sigterm)
        signal.signal(signal.SIGINT, _sigterm)
        daemon.start()

    elif args.command == "set-image":
        dev = StreamStationDevice()
        if dev.open():
            ok = dev.send_image_file(args.button, args.image)
            dev.close()
            print("OK" if ok else "ERROR")
        else:
            print("No se pudo abrir el dispositivo")
            sys.exit(1)

    elif args.command == "set-color":
        dev = StreamStationDevice()
        if dev.open():
            r, g, b = _hex_to_rgb(args.color)
            ok = dev.send_solid_color(args.button, r, g, b)
            dev.close()
            print("OK" if ok else "ERROR")
        else:
            sys.exit(1)

    elif args.command == "brightness":
        dev = StreamStationDevice()
        if dev.open():
            ok = dev.set_brightness(args.value)
            dev.close()
            print("OK" if ok else "ERROR")
        else:
            sys.exit(1)

    elif args.command == "monitor":
        print(f"Monitoreando VID:{VENDOR_ID:04X} PID:{PRODUCT_ID:04X}...")
        print("Pulsa Ctrl+C para salir")
        dev = StreamStationDevice()
        if not dev.open():
            print("No se pudo abrir el dispositivo")
            sys.exit(1)
        try:
            while True:
                data = dev.read_event(timeout_ms=500)
                if data:
                    hex_str = " ".join(f"{b:02x}" for b in data)
                    evt = parse_event(data)
                    extra = ""
                    if evt:
                        if evt.encoder_delta:
                            extra = f" → encoder {evt.button} delta={evt.encoder_delta:+d}"
                        else:
                            extra = f" → botón {evt.button} {'↓' if evt.pressed else '↑'}"
                    print(f"{hex_str}{extra}")
        except KeyboardInterrupt:
            pass
        finally:
            dev.close()

    elif args.command == "set-title":
        print("set-title no está soportado en modo directo (el hardware no tiene")
        print("overlay de texto — usa set-image con una imagen que incluya el texto)")

if __name__ == "__main__":
    main()
