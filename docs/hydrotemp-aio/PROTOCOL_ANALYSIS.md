# Reverse Engineering: PC Monitor All → Protocolo USB HID

## Aplicación original
- **Nombre**: PC Monitor All (`PC Monitor All.exe`)
- **Ruta**: `C:\Program Files (x86)\PC\PC Monitor All\`
- **Framework**: .NET Framework 4.7.2 (C#)
- **Archivos**: `PC Monitor All.exe`, `PC Monitor All.pdb` (símbolos), `HWiNFO32.dll`, `HWiNFO64.dll`, `CyUSB.dll`, `ComputereMonitor.sys`

---

## Arquitectura

```
HWiNFO32/64.dll  →  ComputereMonitor.HWInfo
    (sensores hw)       (wrapper P/Invoke)
                              ↓
                   ComputereMonitor.frmMain
                   ┌──────────────────────────┐
                   │  Thread_GetPCParam()     │  ← lee sensores cada 1000ms
                   │  GetPCParam()            │  ← procesa y escala valores
                   │  SendData2()             │  ← construye paquete HID 64 bytes
                   │  send_usb_data()         │  ← envía al dispositivo
                   └──────────────────────────┘
                              ↓
                   CyUSB.dll (Cypress USB library)
                   ComputereMonitor.sys (kernel driver)
                              ↓
                   Dispositivo físico USB HID
                   VID: 0x3554  PID: 0xFA09
```

---

## Dispositivo USB

| Campo | Valor |
|-------|-------|
| Vendor ID | `0x3554` |
| Product ID | `0xFA09` |
| Clase Windows | Dispositivo compuesto USB |
| Interfaces | Teclado (MI_00), HID vendor (MI_01 COL01), Mouse, Consumer Control, System Controller |

### Interfaces HID en Windows Device Manager
```
USB\VID_3554&PID_FA09                        → Dispositivo compuesto USB
HID\VID_3554&PID_FA09&MI_00                  → Teclado
HID\VID_3554&PID_FA09&MI_01&COL01            → Vendor-defined (MONITOREO ← esta)
HID\VID_3554&PID_FA09&MI_01&COL02            → Consumer Control
HID\VID_3554&PID_FA09&MI_01&COL03            → System Controller
HID\VID_3554&PID_FA09&MI_01&COL04            → Teclado 2
HID\VID_3554&PID_FA09&MI_01&COL05            → Mouse
HID\VID_3554&PID_FA09&MI_01&COL06            → Vendor-defined 2
```

En Linux: aparece como `/dev/hidrawN` (la interfaz vendor-defined).

---

## Protocolo HID — Paquete de 64 bytes

Decodificado del IL del método `SendData2()` en `ComputereMonitor.frmMain`.

### Formato completo

```
Offset  Valor    Descripción
──────  ───────  ───────────────────────────────────────────
  0     0x00     Report ID (fijo, siempre 0)
  1     0x01     Header byte 1 (fijo)
  2     0x02     Header byte 2 (fijo)
  3     0-255    CPU temperatura °C     (SendValueArray[0])
  4     0-255    CPU uso %              (SendValueArray[1])
  5     0-255    CPU potencia W         (SendValueArray[2])
  6     0-255    CPU frecuencia MHz     (SendValueArray[3])
  7     0-255    CPU voltaje V          (SendValueArray[4])
  8     0-255    GPU temperatura °C     (SendValueArray[5])
  9     0-255    GPU uso %              (SendValueArray[6])
 10     0-255    GPU potencia W         (SendValueArray[7])
 11     0-255    GPU frecuencia MHz     (SendValueArray[8])
 12     0-255    Fan agua/refrigeración (SendValueArray[9])
 13     0-255    Fan sistema RPM        (SendValueArray[10])
 14-35  0-255    SendValueArray[11-32]  (reservado, ceros)
 36-63  0x00     Padding
```

### Fórmula de escalado
```python
valor_envio = int(clamp(valor_real, 0, valor_maximo) / valor_maximo * 255)
```

Los valores máximos son configurables (originalmente controles `NumericUpDown` en la UI).

---

## Frecuencia de actualización

Del IL de `Thread_Send()`:
```
20 C8 00 00 00    ldc.i4 0xC8 = 200
28 82 00 00 0A    call Thread.Sleep(200)
```

**Envío cada 200ms (5 Hz)** — Lectura de sensores cada 1000ms.

---

## Hardware del sistema (del config.ini original)

| Componente | Modelo |
|------------|--------|
| CPU | Intel Core i7-14700F |
| GPU | AMD Radeon RX 6600 XT |
| Display USB | VID:3554 PID:FA09 |

---

## Valores máximos por defecto (del config.ini + análisis)

| Sensor | Máximo | Unidad |
|--------|--------|--------|
| CPU Temp | 100 | °C |
| CPU Uso | 100 | % |
| CPU Potencia | 253 | W (TDP i7-14700F) |
| CPU Frecuencia | 5287 | MHz (boost máx) |
| CPU Voltaje | 1.5 | V |
| GPU Temp | 110 | °C |
| GPU Uso | 100 | % |
| GPU Potencia | 160 | W (TDP RX 6600 XT) |
| GPU Frecuencia | 2589 | MHz (boost máx) |
| Fan Agua | 3000 | RPM |
| Fan Sistema | 3000 | RPM |

---

## Método de análisis

1. Identificar proceso: `tasklist` → `PC Monitor All.exe` (PID 16932)
2. Encontrar el .exe: `C:\Program Files (x86)\PC\PC Monitor All\PC Monitor All.exe`
3. Detectar framework: .NET Framework 4.7.2, con `.pdb`
4. Listar clases con `System.Reflection.Assembly.LoadFile()` → 50 clases
5. Extraer métodos con `Type.GetMethods(BindingFlags.NonPublic|...)`
6. Extraer IL con `MethodInfo.GetMethodBody().GetILAsByteArray()`
7. Decodificar IL manualmente opcode por opcode
8. Identificar dispositivo USB: `Get-PnpDevice` → VID_3554&PID_FA09

No se necesitó captura de paquetes USB ni Wireshark.
