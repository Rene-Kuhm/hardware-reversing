# hydrotemp-rgb-arch

HydroTemp AIO monitor + RGB Fusion keepalive for Arch Linux / CachyOS.

Adaptado de [Datos-xyz-hydrotemp](https://github.com/Rene-Kuhm/Datos-xyz-hydrotemp) y [Datos-RGB-Fusion-nixOS](https://github.com/Rene-Kuhm/Datos-RGB-Fusion-nixOS) para Arch Linux.

## Componentes

### monitor.py — Daemon HID display HydroTemp

Envía datos de sensores (temp CPU, temp GPU, RPM fan/pump) al display USB HID (VID:5131 PID:2007) de coolers AIO.

Dependencias:
- `python-hid` (Arch: `pacman -S hidapi`)
- Python 3.10+

```bash
python3 monitor.py --verbose
python3 monitor.py --dry-run --verbose
```

### bin/rgb-keepalive.sh — OpenRGB Keepalive

Re-aplica periódicamente el perfil RGB con OpenRGB para que la placa no resetee los colores.

Dependencias:
- `openrgb` (Arch: `pacman -S openrgb`)

Variables de entorno (con defaults):
- `RGB_DEVICE_ID=1`
- `RGB_MEMORY_DEVICE_ID=0`
- `RGB_MODE=static`
- `RGB_COLOR=FFFFFF`
- `RGB_BRIGHTNESS=100`
- `RGB_ARG_SIZE=30`
- `RGB_INTERVAL_SEC=20`

### bin/hydrotemp-start.sh — Launcher del monitor

Script que lanza `monitor.py`. Usado por el servicio de systemd.

### systemd/ — Servicios de usuario

- `hydrotemp.service` — Daemon del monitor HydroTemp
- `rgb-init.service` — Keepalive RGB con OpenRGB

## Instalación

1. Clonar:
```bash
git clone https://github.com/Rene-Kuhm/hydrotemp-rgb-arch.git ~/hydrotemp-rgb-arch
```

2. Instalar dependencias:
```bash
sudo pacman -S hidapi openrgb
```

3. Copiar scripts de inicio a `~/bin/`:
```bash
cp bin/hydrotemp-start.sh ~/bin/
cp bin/rgb-keepalive.sh ~/bin/
chmod +x ~/bin/hydrotemp-start.sh ~/bin/rgb-keepalive.sh
```

4. Copiar servicios de systemd:
```bash
mkdir -p ~/.config/systemd/user/
cp systemd/hydrotemp.service ~/.config/systemd/user/
cp systemd/rgb-init.service ~/.config/systemd/user/
```

5. Habilitar e iniciar:
```bash
systemctl --user daemon-reload
systemctl --user enable --now hydrotemp.service
systemctl --user enable --now rgb-init.service
```

## Hardware

- **HydroTemp display**: VID `5131` PID `2007` (FBB display)
- **Motherboard RGB**: Gigabyte Z790 AORUS (via OpenRGB)