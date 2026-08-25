# Instalación en NixOS

Guía completa para instalar los drivers de hardware reversing en NixOS.

## Requisitos

- NixOS 24.05+ (unstable)
- Python 3.10+
- Acco a `configuration.nix` (sudo)

## Hardware soportado

| Dispositivo | Chip | Driver | Estado |
|---|---|---|---|
| AIO Cooler Display (HydroTemp FBB) | HID `5131:2007` | `monitor.py` | ✅ Producción |
| Motherboard RGB | IT5701 (Z790 AORUS) | OpenRGB | ✅ Producción |
| HyperX Fury RGB | — | OpenRGB | ✅ Producción |
| Super I/O fans/voltajes | IT8689E | `it87` module | ✅ Producción |
| Webcam (Logitech MX Brio) | `046d:0944` | V4L2 | ✅ Producción |
| Stream Station | HID `3554:fa09` | `stream_station.py` | ✅ |

## Instalación rápida

### 1. Clonar el repo

```bash
git clone https://github.com/tecnodespegue/hardware-reversing.git
cd hardware-reversing
```

### 2. Agregar a configuration.nix

Copia el siguiente bloque al final de tu `configuration.nix`:

```nix
# ----------------------------------------------------------------------
# Hardware reversing drivers (~/hardware-reversing)
# ----------------------------------------------------------------------

# I2C / SMBus kernel modules (RGB Fusion + it87)
boot.kernelModules = [ "i2c-dev" "i2c-i801" "it87" ];

# it87 necesita ignore_resource_conflict porque gigabyte_wmi
# entra en conflicto con el bus LPC.
boot.extraModprobeConfig = ''
  options it87 ignore_resource_conflict=1
'';

# Paquetes del sistema
environment.systemPackages = with pkgs; [
  (python3.withPackages (ps: with ps; [
    hid
    smbus2
    pillow
    websockets
  ]))
  i2c-tools
  lm_sensors
  openrgb
  usbutils
  v4l-utils
  ffmpeg
];

# Grupos del sistema
users.groups.hwmon = {};
users.groups.i2c = {};

# udev rules para los dispositivos HID
services.udev.extraRules = ''
  # AIO Cooler Display (HydroTemp FBB) — VID 5131 / PID 2007
  SUBSYSTEM=="hidraw", ATTRS{idVendor}=="5131", ATTRS{idProduct}=="2007", \
    GROUP="hwmon", MODE="0660", TAG+="uaccess"
  SUBSYSTEM=="usb",     ATTRS{idVendor}=="5131", ATTRS{idProduct}=="2007", \
    GROUP="hwmon", MODE="0660"

  # ITE8297 RGB LED controller (Gigabyte motherboard) — VID 048D / PID 5702
  SUBSYSTEM=="hidraw", ATTRS{idVendor}=="048d", ATTRS{idProduct}=="5702", \
    GROUP="hwmon", MODE="0660", TAG+="uaccess"
  SUBSYSTEM=="usb",     ATTRS{idVendor}=="048d", ATTRS{idProduct}=="5702", \
    GROUP="hwmon", MODE="0660"

  # i2c-dev / i2c SMBus
  SUBSYSTEM=="i2c-dev", GROUP="i2c", MODE="0660"
  SUBSYSTEM=="i2c",     GROUP="i2c", MODE="0660"

  # RAPL powercap (consumo CPU)
  SUBSYSTEM=="powercap", ACTION=="add", \
    RUN+="${pkgs.coreutils}/bin/chmod g+r /sys%p/energy_uj", \
    RUN+="${pkgs.coreutils}/bin/chgrp hwmon /sys%p/energy_uj"

  # V4L2 — webcam devices
  KERNEL=="video[0-9]*",   GROUP="video", MODE="0660"
  KERNEL=="vbi[0-9]*",     GROUP="video", MODE="0660"
'';

# Asegurar que el usuario esté en los grupos necesarios
users.users."TU_USUARIO" = {
  extraGroups = [ "hwmon" "i2c" "video" ];
};
```

### 3. Aplicar configuración

```bash
sudo nixos-rebuild switch
```

### 4. Agregar tu usuario a los grupos

```bash
sudo usermod -aG hwmon,i2c,video $USER
```

**Importante**: Cerrá sesión y volvé a entrar para que los cambios tengan efecto.

## Systemd services

### AIO Cooler Display (monitor.py)

El daemon lee sensores y escribe la temperatura al display cada 200ms.

```bash
# Crear servicio
cat > ~/.config/systemd/user/hydrotemp-aio.service << 'EOF'
[Unit]
Description=HydroTemp AIO monitor daemon
After=default.target

[Service]
Type=simple
ExecStart=/home/TU_USUARIO/hardware-reversing/hydrotemp-aio/monitor.py --log-level INFO
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
EOF

# Habilitar e iniciar
systemctl --user daemon-reload
systemctl --user enable --now hydrotemp-aio.service
```

### RGB Keepalive (OpenRGB)

Gigabyte resetea el RGB periódicamente. Este servicio re-aplica el color cada 20 segundos.

```bash
# Copiar el script
cp ~/hardware-reversing/aio-rgb-apply.sh ~/bin/
chmod +x ~/bin/aio-rgb-apply.sh

# Crear servicio
cat > ~/.config/systemd/user/aio-rgb.service << 'EOF'
[Unit]
Description=Keep motherboard RGB profile applied
After=default.target

[Service]
Type=oneshot
Environment=RGB_COLOR=FFFFFF
Environment=RGB_BRIGHTNESS=100
Environment=RGB_MODE=Static
ExecStart=/home/TU_USUARIO/bin/aio-rgb-apply.sh

[Install]
WantedBy=default.target
EOF

# Habilitar
systemctl --user daemon-reload
systemctl --user enable --now aio-rgb.service
```

### Webcam MX Brio (V4L2)

Configuración profesional de la webcam al boot.

```bash
# Copiar el script
cp ~/hardware-reversing/webcam-config.sh ~/bin/
chmod +x ~/bin/webcam-config.sh

# Crear servicio
cat > ~/.config/systemd/user/webcam-config.service << 'EOF'
[Unit]
Description=Logitech MX Brio — configuración V4L2 profesional
After=default.target

[Service]
Type=oneshot
ExecStart=/home/TU_USUARIO/bin/webcam-config.sh
RemainAfterExit=true

[Install]
WantedBy=default.target
EOF

# Habilitar
systemctl --user daemon-reload
systemctl --user enable --now webcam-config.service
```

## Verificación

### AIO Display

```bash
# Verificar que el daemon está corriendo
systemctl --user status hydrotemp-aio.service

# Ver logs
journalctl --user -u hydrotemp-aio.service -f

# Test manual (sin HID device)
python3 ~/hardware-reversing/hydrotemp-aio/monitor.py --dry-run --verbose
```

### RGB

```bash
# Verificar dispositivos OpenRGB
openrgb --list

# Aplicar color manualmente
export QT_QPA_PLATFORM=offscreen
export LIBGL_ALWAYS_SOFTWARE=1
openrgb --noautoconnect -d 1 -m Static --color FFFFFF

# Verificar servicio
systemctl --user status aio-rgb.service
```

### Super I/O (it87)

```bash
# Verificar módulo cargado
lsmod | grep it87

# Ver sensores
sensors
```

### Webcam

```bash
# Verificar dispositivo
v4l2-ctl --list-devices

# Ver configuración actual
v4l2-ctl -d /dev/video0 -l

# Test con ffmpeg
ffmpeg -f v4l2 -i /dev/video0 -frames 1 test.jpg
```

## Variables de entorno

El script `aio-rgb-apply.sh` soporta estas variables:

| Variable | Default | Descripción |
|---|---|---|
| `RGB_COLOR` | `FFFFFF` | Color hex |
| `RGB_BRIGHTNESS` | `100` | Brillo % |
| `RGB_MODE` | `Static` | Modo (Static, Breathing, etc.) |

## Troubleshooting

### "No HID device found"

El display expone `VID 5131 PID 2007` pero hay que seleccionar la interfaz correcta:

```bash
# Verificar que el device existe
lsusb | grep 5131

# Verificar hidraw
ls -la /dev/hidraw*
```

### RGB no aplica

OpenRGB necesita Qt offscreen en headless:

```bash
export QT_QPA_PLATFORM=offscreen
export LIBGL_ALWAYS_SOFTWARE=1
openrgb --list
```

### it87 no carga

Asegurar que `ignore_resource_conflict=1` esté en `configuration.nix`:

```bash
cat /proc/cmdline | grep it87
# Debe mostrar: options it87 ignore_resource_conflict=1
```

## Hardware probado

| Componente | Dispositivo |
|---|---|
| AIO display | HydroTemp / PC Monitor All — VID `5131` PID `2007` (FBB) |
| Motherboard RGB | Gigabyte Z790 AORUS ELITE AX (IT5701) |
| RAM RGB | HyperX Fury RGB (2 slots, 5 LEDs c/u) |
| Super I/O | IT8689E (fans, voltajes, temperaturas) |
| Webcam | Logitech MX Brio (`046d:0944`) |
| Sistema | NixOS unstable, kernel latest |
