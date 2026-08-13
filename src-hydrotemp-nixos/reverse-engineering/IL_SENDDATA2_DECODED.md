# IL Decodificado — SendData2() y métodos clave

## SendData2() — El método que construye y envía el paquete HID

### IL raw (63 bytes)
```
0000: 1F 40 8D 84 00 00 01 0A 06 16 16 9C 06 17 17 9C
0010: 06 18 18 9C 16 0B 2B 12 06 19 07 58 02 7B A3 00
0020: 00 04 07 94 D2 9C 07 17 58 0B 07 1F 21 32 E9 02
0030: 06 1F 40 28 2C 00 00 06 26 DE 03 26 DE 00 2A
```

### Instrucción por instrucción

| Offset | Bytes | Opcode | C# equivalente |
|--------|-------|--------|----------------|
| 0000 | `1F 40` | `ldc.i4 64` | push 64 |
| 0002 | `8D 84 00 00 01` | `newarr System.Byte` | `buf = new byte[64]` |
| 0007 | `0A` | `stloc.0` | almacena en local[0] |
| 0008 | `06` | `ldloc.0` | push buf |
| 0009 | `16` | `ldc.i4.0` | push 0 (índice) |
| 000A | `16` | `ldc.i4.0` | push 0 (valor) |
| 000B | `9C` | `stelem.i1` | `buf[0] = 0` ← **Report ID** |
| 000C | `06` | `ldloc.0` | push buf |
| 000D | `17` | `ldc.i4.1` | push 1 (índice) |
| 000E | `17` | `ldc.i4.1` | push 1 (valor) |
| 000F | `9C` | `stelem.i1` | `buf[1] = 1` ← **Header 1** |
| 0010 | `06` | `ldloc.0` | push buf |
| 0011 | `18` | `ldc.i4.2` | push 2 (índice) |
| 0012 | `18` | `ldc.i4.2` | push 2 (valor) |
| 0013 | `9C` | `stelem.i1` | `buf[2] = 2` ← **Header 2** |
| 0014 | `16` | `ldc.i4.0` | push 0 |
| 0015 | `0B` | `stloc.1` | `i = 0` |
| 0016 | `2B 12` | `br.s +18` | saltar al check del loop |
| ---- | --- | --- | **CUERPO DEL LOOP** |
| 0018 | `06` | `ldloc.0` | push buf |
| 0019 | `19` | `ldc.i4.3` | push 3 |
| 001A | `07` | `ldloc.1` | push i |
| 001B | `58` | `add` | push (3 + i) |
| 001C | `02` | `ldarg.0` | push this |
| 001D | `7B A3 00 00 04` | `ldfld SendValueArray` | push this.SendValueArray |
| 0022 | `07` | `ldloc.1` | push i |
| 0023 | `94` | `ldelem.i4` | push SendValueArray[i] |
| 0024 | `D2` | `conv.u1` | cast to byte |
| 0025 | `9C` | `stelem.i1` | `buf[3+i] = (byte)SendValueArray[i]` |
| 0026 | `07` | `ldloc.1` | push i |
| 0027 | `17` | `ldc.i4.1` | push 1 |
| 0028 | `58` | `add` | push i+1 |
| 0029 | `0B` | `stloc.1` | `i = i + 1` |
| ---- | --- | --- | **CHECK DEL LOOP** |
| 002A | `07` | `ldloc.1` | push i |
| 002B | `1F 21` | `ldc.i4 33` | push 33 |
| 002D | `32 E9` | `blt.s -23` | if (i < 33) goto 0x18 |
| ---- | --- | --- | **LLAMADA A SEND** |
| 002F | `02` | `ldarg.0` | push this |
| 0030 | `06` | `ldloc.0` | push buf |
| 0031 | `1F 40` | `ldc.i4 64` | push 64 |
| 0033 | `28 2C 00 00 06` | `call send_usb_data` | `this.send_usb_data(buf, 64)` |
| 0038 | `26` | `pop` | descarta valor de retorno |
| 0039 | `DE 03` | `leave.s` | fin de bloque try |
| 003B | `26` | `pop` | |
| 003C | `DE 00` | `endfinally` | |
| 003E | `2A` | `ret` | return |

### C# equivalente reconstruido

```csharp
void SendData2() {
    byte[] buf = new byte[64];
    buf[0] = 0;   // Report ID
    buf[1] = 1;   // Header
    buf[2] = 2;   // Header
    for (int i = 0; i < 33; i++) {
        buf[3 + i] = (byte)this.SendValueArray[i];
    }
    this.send_usb_data(buf, 64);
}
```

---

## Thread_Send() — Hilo de envío periódico

### IL raw (150 bytes)
```
0000: 00 02 7B AB 00 00 04 6F A0 00 00 0A 17 31 43 16
0010: 0A 2B 2F 7E 05 00 00 04 06 6F A1 00 00 0A 2C 1E
0020: 02 02 7B AB 00 00 04 06 6F A2 00 00 0A 7D A8 00
0030: 00 04 02 28 26 00 00 06 02 28 34 00 00 06 06 17
0040: 58 0A 06 02 7B AB 00 00 04 6F A0 00 00 0A 32 C3
0050: 2B 0C 02 28 26 00 00 06 02 28 34 00 00 06 DE 22
0060: 0B 72 B5 08 00 70 07 6F 3E 00 00 0A 28 3F 00 00
0070: 0A 72 FB 01 00 70 20 E7 03 00 00 28 09 00 00 06
0080: DE 00 20 C8 00 00 00 28 82 00 00 0A 28 83 00 00
0090: 0A 38 6A FF FF FF
```

### C# equivalente reconstruido

```csharp
void Thread_Send() {
    while (true) {
        try {
            if (myHidDevice_List.Count <= 1) {
                // Un solo dispositivo
                for (int i = 0; i < myHidDevice_List.Count; i++) {
                    if (HIDDeviceList[i] != null) {
                        myHidDevice = myHidDevice_List[i];
                        GetPCParam();    // Lee sensores
                        SendData2();     // Envía paquete
                    }
                    i++;
                }
            } else {
                // Múltiples dispositivos
                GetPCParam();
                SendData2();
            }
        } catch (Exception ex) {
            SetAppendTxt("Error: " + ex.ToString(), ..., 999);
        }
        Thread.Sleep(200);   // 200ms = 5 Hz
    }
}
```

---

## Thread_GetPCParam() — Hilo de lectura de sensores

```csharp
void Thread_GetPCParam() {
    while (true) {
        try {
            GetPCParam();
        } catch (Exception ex) {
            SetAppendTxt("Error: " + ex.ToString(), ..., 999);
        }
        Thread.Sleep(1000);   // 1 segundo
    }
}
```

---

## USB_Init() — Inicialización del bus USB

```csharp
void USB_Init() {
    usbDevices = new UsbDevices(5);   // 5 = HID_GUID flag de CyUSB
    usbDevices.DeviceAttached += UsbDevices_DeviceAttached;
    usbDevices.DeviceRemoved  += UsbDevices_DeviceRemoved;
    Get_Devices();
}
```
