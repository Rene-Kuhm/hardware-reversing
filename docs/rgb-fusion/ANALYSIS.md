# Reverse Engineering: RGB Fusion / Gigabyte Control Center

## Aplicación analizada
- **Nombre**: Gigabyte Control Center (GCC) + RGB Fusion
- **Ruta**: `C:\Program Files\GIGABYTE\Control Center\GCC.exe`
- **Versión**: 25.1.23.0
- **PID en ejecución**: 9856

---

## Arquitectura general

```
GCC.exe (WPF .NET)
  ├── SMBCtrl.dll        ← Canal SMBus/I2C para LEDs de placa madre
  │     └── (nativo C++ MFC, driver kernel YccDrvv3.dll)
  ├── GHidApi.dll        ← Canal USB HID para periféricos externos
  │     └── (nativo C++, usa hidapi de Windows)
  ├── Lib/GBT_rgbMotherboard_UC/
  │     ├── LedIoControl.dll    ← Wrapper .NET de SMBCtrl
  │     ├── RgbMotherboard.dll  ← Lógica de zonas RGB de la MB
  │     ├── cled.dll            ← Librería LED de bajo nivel
  │     ├── LedIoControl.dll    ← Control I/O de LEDs
  │     └── MB_RGB_Capability.dll ← Detección de capacidades
  ├── Lib/COMMDLL/
  │     ├── RgbCommon.dll       ← Tipos y estructuras comunes
  │     └── RGBFI.dll           ← Interfaz de abstracción RGB
  └── Lib/GBT_RGB_Sync_Control/
        └── GBT_RGB_Sync_Control.dll ← Sincronización entre zonas
```

---

## Canal 1: SMBus/I2C (Placa madre)

### Chips ITE detectados
El software detecta automáticamente cuál chip ITE está presente:

| Chip | ID | Boards |
|------|----|--------|
| IT8620E | 0x8620 | Older (200-series) |
| IT8686E | 0x8686 | Z390, H370 |
| IT8688  | 0x8688 | Z390, X570, Z490 |
| IT8295  | 0x8295 | B660, Z690, B760, Z790 (actual) |
| IT8297  | 0x8297 | AORUS high-end |

### Funciones exportadas de SMBCtrl.dll (DLL nativa C++)
```
dllexp_LibInitial               → Inicializar SMBus
dllexp_GetLEDId                 → Detectar chip LED (retorna IT ID)
dllexp_GetMBId                  → ID de la placa madre
dllexp_GetModelName             → Nombre del modelo
dllexp_GetSIVId                 → SIV chip ID
dllexp_ReGetSMBusInfo           → Re-detectar SMBus
dllexp_SetSMBMutex              → Mutex para acceso exclusivo

dllexp_MCU_Rw(addr, reg, val, pVal, rw, delay)     → R/W registro MCU
dllexp_MCU_Rw2(...)                                  → variante 2
dllexp_IT8295_Block_RW(addr, reg, len, buf, rw, delay) → Bloque I2C IT8295
dllexp_IT8295_Block_RW2(...)                         → variante 2

dllexp_I2C_Byte_RW(channel, addr, reg, val, pVal, rw)  → Byte I2C
dllexp_I2C_Word_RW(channel, addr, reg, data, out, rw)  → Word I2C
dllexp_I2C_Block_RW(channel, addr, reg, len, buf, rw)  → Bloque I2C
dllexp_I2C_ReceiveByte(channel, addr, reg, pVal)        → Receive byte
dllexp_I2C_Ready()                                      → ¿Bus listo?

dllexp_SMB_ReceiveByte(addr, reg, pVal)
dllexp_SMB_Word_RW(addr, reg, rw, data, out)
dllexp_SMB_Word_RW2(...)
dllexp_SMB_WordWrite_ProcCall(...)
dllexp_Skx_SMB_ByteRW(ctrl, addr, reg, val, pVal, rw)
dllexp_Skx_SMB_WordRW(ctrl, addr, reg, val, pVal, rw)

dllexp_SetLedModeToBios(iVal)   → Guardar modo en BIOS
dllexp_SaveToBios               → Persistir configuración
dllexp_GetLedModeCurrentValue   → Modo actual
dllexp_GetLedModeSetupData      → Datos de configuración del modo
dllexp_GetLedSetupDataLength    → Longitud datos config
dllexp_SetLedPwrStateToBios     → Estado LED en apagado
dllexp_GetLedPwrStateCurrentValue
dllexp_GetLedPwrStateSetupData
dllexp_SetLedPwrOnStateToBios   → Estado LED en encendido
dllexp_GetLedPwrOnStateCurrentValue
dllexp_GetLedPwrOnStateSetupData

dllexp_Get_IT8295_FwVer(addr, reg, len, buf) → Versión firmware IT8295
dllexp_ChkEzSetupSupport        → Soporte EZ setup
dllexp_BeatGpioCtrl(iCtrl)      → Control GPIO Beat
dllexp_GetTrueColorVal          → Valor TrueColor
dllexp_SetTrueColorValueToBios  → Guardar TrueColor en BIOS
dllexp_GetEzLedColorProfileSupport
dllexp_GetEzLedModeProfileSupport
dllexp_DelayMicroSeconds(us)    → Delay microsegundos
dllexp_Pch_D0_D1_D2_Ctrl(d0,d1,d2) → Control PCH GPIO
```

### Protocolo IT8295 (ARGB headers — Addressable RGB)

El IT8295 está en la dirección I2C **0x58** en el bus SMBus del PCH.

**Escribir modo/color** (bloque de 60 bytes a offset 0x00):
```
Byte  0  : Modo de efecto (ver tabla de modos)
Byte  1  : R (rojo)
Byte  2  : G (verde)
Byte  3  : B (azul)
Byte  4  : Velocidad (0-9)
Byte  5  : Brillo (0-9)
Byte  6  : Número de LEDs en el strip (0 = usar default)
Byte 7-59: Parámetros adicionales (ceros para efectos básicos)
```

**Modos IT8295 (ARGB)**:
```
0x01 = Static (fijo)
0x02 = Breathing (respiración)
0x03 = Flashing
0x04 = Color Cycle
0x05 = Wave
0x06 = Ripple
0x07 = Random
```

**Inicialización IT8295**:
```
1. LibInitial()         → Inicializar bus SMBus
2. GetLEDId()           → Verificar que retorna 0x8295
3. Get_IT8295_FwVer()   → Obtener versión firmware
4. IT8295_Block_RW(0x58, 0x00, 60, buf, WRITE, 0) → Escribir configuración
```

### Protocolo IT8297 (PWM RGB zones — non-addressable)

El IT8297 también usa I2C 0x58 pero con mapa de registros diferente.

**Modos (LMode_8297 enum)**:
```
0   = Null (apagado)
1   = Static
2   = Pulse (Breathing)
3   = Flash
4   = ColorCycle
5   = Meteor
6   = Wave
7   = Ripple
8   = Random
50  = Off
51  = DFlash
56  = Beat
100 = SWave
101 = StarSlide
103 = Shaking
104 = Explode
105 = Recover
106 = DoubleMeteor
107 = ColorStack
109 = ColorRain
```

---

## Canal 2: USB HID (Dispositivos externos)

### GHidApi.dll — API HID nativa
**Funciones exportadas**:
```
dllexp_ConnectDevice(VendorID, ProductID, CustomUP, CustomP, LengthInfo[])
dllexp_DisconnectDevice(VendorID, ProductID, DeviceNum)
dllexp_GetConnectedList(VendorID, ProductID, devList[])
dllexp_WriteDataToDevice(VendorID, ProductID, DeviceNum, Data[], DataSize)
dllexp_ReadDataFromDevice(VendorID, ProductID, DeviceNum, Data[], DataSize)
```

### Dispositivos USB conocidos (Device.ini)
| VID:PID | Modelo | Tipo |
|---------|--------|------|
| 1044:7A34 | AORUS H5 | Header |
| 1044:7A30 | AORUS C300 Glass | Chasis |
| 1044:7A4C | AORUS C700 Glass | Chasis |
| 1044:7A50 | AORUS P1200W | Fuente |
| 1044:7A52 | AORUS WATERFORCE G | Cooler |
| 1044:7A53 | AORUS WATERFORCE EX | Cooler |
| 1044:7A4D | AORUS WATERFORCE X | Cooler |
| 1044:7A51 | AORUS WATERFORCE | Cooler |
| 1044:7A4A | AORUS K1 Keyboard | Teclado |
| 1458:7A59 | AORUS RTX 4090 Box | VGA Box |

---

## Formato de configuración (rgbcfg.xml)

```xml
<lights wave="2">
  <light idx="N"
    mode="M"           <!-- ID de modo LED -->
    color0="00RRGGBB"  <!-- Color primario (ARGB, A siempre 00) -->
    color1="0"         <!-- Color secundario (para efectos multi-color) -->
    color2="0"         <!-- Color terciario -->
    sp="6"             <!-- Velocidad 0-9 -->
    bri="6"            <!-- Brillo 0-9 -->
  />
</lights>
```

**Modos en rgbcfg.xml** (PatternType enum):
```
0  = Still (estático)
1  = Breath (respiración)
2  = Beat (pulso)
3  = MixColor
4  = Flash
5  = Random
6  = Wave
7  = Scenes
8  = Off
9  = Auto
11 = DFlash
12 = StarSlide
13 = Meteor
14 = Shaking
50 = TriColor
51 = Gradient
52 = ColorShift
56 = SPIN
58 = DAZZLE
62 = AORURA (Aurora)
69 = AllRainbow
```

**Sync mode** (en `<sync_setting>`):
```xml
<sync_setting>
  <param mode="69" color="00FF0000" sp="8" bri="8" />
</sync_setting>
```
- mode=69 = AllRainbow sync en todas las zonas

---

## Configuración actual del sistema
```xml
<!-- De rgbcfg.xml del sistema -->
<sync_setting>
  <param mode="69" color="00FF0000" sp="8" bri="8" />
</sync_setting>
<!-- 22 zonas de luz, todas en mode=0 (Still), color=00FF0000 (rojo) -->
<!-- sp=6, bri=6 por defecto -->
```

---

## Implementación en Linux/NixOS

### Acceso SMBus
```
/dev/i2c-0, /dev/i2c-1, ... /dev/i2c-N
```

El IT8295 está en el bus **i2c del PCH** (Intel Z790). En Linux:
- Cargar módulo: `modprobe i2c-dev i2c-i801`
- Detectar bus: `i2cdetect -l` → buscar bus con nombre "SMBus I801"
- Detectar chip: `i2cdetect -y <bus_number>` → debe aparecer 0x58

### Dependencias Python
```
smbus2    → acceso I2C/SMBus
hid       → dispositivos USB HID
tomllib   → config TOML (Python 3.11+ built-in)
```

### Permisos requeridos
- Grupo `i2c` → acceso a `/dev/i2c-*`
- Grupo `plugdev` → acceso a `/dev/hidraw*` (para USB HID)
- Kernel modules: `i2c-dev`, `i2c-i801`
