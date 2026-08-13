# DLL Exports — SMBCtrl.dll y GHidApi.dll

## SMBCtrl.dll (DLL nativa C++ MFC)
**Ruta**: `C:\Program Files\GIGABYTE\Control Center\SMBCtrl.dll`
**PDB**: `F:\0Work\KabyLED\x64\Release\SMBCtrl.pdb`
**Tamaño**: 2,635,432 bytes

### Funciones exportadas
```c
// Inicialización
uint32_t dllexp_LibInitial()
uint32_t dllexp_ReGetSMBusInfo()
void     dllexp_SetSMBMutex()
void     dllexp_DelayMicroSeconds(float microseconds)

// Detección de dispositivo
uint32_t dllexp_GetLEDId()
int32_t  dllexp_GetMBId()
void     dllexp_GetModelName(uint8_t* mdName)
uint32_t dllexp_GetSIVId()
int32_t  dllexp_GetTrueColorVal()
int32_t  dllexp_GetSkxCpuType()
uint32_t dllexp_GetPlatform()

// I2C/SMBus genérico
uint32_t dllexp_I2C_Ready()
uint32_t dllexp_I2C_Byte_RW(int channel, uint8_t slaveAddr, uint8_t regOffset,
                              uint8_t val, uint8_t* pVal, uint8_t rw)
uint32_t dllexp_I2C_Word_RW(int channel, uint8_t slaveAddr, uint8_t regOffset,
                              uint16_t inData, uint16_t* outData, uint8_t rw)
uint32_t dllexp_I2C_Block_RW(int channel, uint8_t slaveAddr, uint8_t regOffset,
                               uint8_t* len, uint8_t* datArry, uint8_t rw)
uint32_t dllexp_I2C_ReceiveByte(int channel, uint8_t slaveAddr,
                                  uint8_t regOffset, uint8_t* pVal)

// MCU (IT8295 vía SMBus)
uint32_t dllexp_MCU_Rw(uint8_t mcuAddr, uint8_t regOffset, uint8_t val,
                        uint8_t* pVal, uint8_t rw, uint32_t delayTime)
uint32_t dllexp_MCU_Rw2(uint8_t mcuAddr, uint8_t regOffset, uint8_t val,
                         uint8_t* pVal, uint8_t rw, uint32_t delayTime)

// IT8295 bloque
uint32_t dllexp_IT8295_Block_RW(uint8_t mcuAddr, uint8_t regOffset,
                                  uint8_t* len, uint8_t* datArry,
                                  uint8_t rw, uint32_t delayTime)
uint32_t dllexp_IT8295_Block_RW2(uint8_t mcuAddr, uint8_t regOffset,
                                   uint8_t* len, uint8_t* datArry,
                                   uint8_t rw, uint32_t delayTime)
uint32_t dllexp_Get_IT8295_FwVer(uint8_t mcuAddr, uint8_t regOffset,
                                   uint8_t* len, uint8_t* datArry)

// SMBus word
uint32_t dllexp_SMB_ReceiveByte(uint8_t mcuAddr, uint8_t regOffset, uint8_t* pVal)
uint32_t dllexp_SMB_Word_RW(uint8_t mcuAddr, uint8_t regOffset, uint8_t rw,
                              uint16_t inData, uint16_t* outData)
uint32_t dllexp_SMB_Word_RW2(uint8_t mcuAddr, uint8_t regOffset, uint8_t rw,
                               uint16_t inData, uint16_t* outData)
uint32_t dllexp_SMB_WordWrite_ProcCall(...)

// Skylake-X (X299)
uint32_t dllexp_Skx_SMB_ByteRW(uint8_t controller, uint8_t mcuAddr, uint8_t regOffset,
                                 uint8_t val, uint8_t* pVal, uint8_t rw)
uint32_t dllexp_Skx_SMB_WordRW(uint8_t controller, uint8_t mcuAddr, uint8_t regOffset,
                                 uint16_t val, uint16_t* pVal, uint8_t rw)

// Configuración LED
uint32_t dllexp_SetLedModeToBios(int iVal)
int32_t  dllexp_GetLedModeCurrentValue()
uint32_t dllexp_GetLedModeSetupData(char* lpReturnBuf, int bufLen)
int32_t  dllexp_GetLedSetupDataLength()

uint32_t dllexp_SetLedPwrStateToBios(int iVal)        // estado en S3/S4/S5
int32_t  dllexp_GetLedPwrStateCurrentValue()
uint32_t dllexp_GetLedPwrStateSetupData(char* buf, int len)
int32_t  dllexp_GetLedPwrSteSetupDataLength()

uint32_t dllexp_SetLedPwrOnStateToBios(int iVal)      // estado en power-on
int32_t  dllexp_GetLedPwrOnStateCurrentValue()
uint32_t dllexp_GetLedPwrOnStateSetupData(char* buf, int len)
int32_t  dllexp_GetLedPwrOnSteSetupDataLength()

uint32_t dllexp_SaveToBios()
uint32_t dllexp_SetTrueColorValueToBios(uint32_t iVal)
uint32_t dllexp_ChkEzSetupSupport()
uint32_t dllexp_BeatGpioCtrl(int iCtrl)
uint32_t dllexp_GetEzLedColorProfileSupport()
uint32_t dllexp_GetEzLedModeProfileSupport()

// PCH GPIO
uint32_t dllexp_Pch_D0_D1_D2_Ctrl(int d0Val, int d1Val, int d2Val)
```

---

## GHidApi.dll (DLL nativa C++)
**Ruta**: `C:\Program Files\GIGABYTE\Control Center\GHidApi.dll`
**PDB**: `D:\0_WORK\Test_GHidApi\Release\x64\GHidApi.pdb`
**Tamaño**: 2,529,392 bytes

### Funciones exportadas
```c
// Gestión de conexión
int32_t dllexp_ConnectDevice(uint16_t VendorID, uint16_t ProductID,
                               uint16_t CustomDeviceUP, uint16_t CustomDeviceP,
                               HID_ReportByteLengt* LengthInfo)

int32_t dllexp_DisconnectDevice(uint16_t VendorID, uint16_t ProductID,
                                  uint8_t DeviceNum)

int32_t dllexp_GetConnectedList(uint16_t VendorID, uint16_t ProductID,
                                  Connected_Devices* devList)

// I/O de datos
int32_t dllexp_WriteDataToDevice(uint16_t VendorID, uint16_t ProductID,
                                   uint8_t DeviceNum, uint8_t* Data, uint8_t DataSize)

int32_t dllexp_ReadDataFromDevice(uint16_t VendorID, uint16_t ProductID,
                                    uint8_t DeviceNum, uint8_t* Data, uint8_t DataSize)
```

### Estructuras clave
```c
typedef struct {
    uint16_t FeatureLength;
    uint16_t InputReportLength;
    uint16_t OutputReportLength;
} HID_ReportByteLengt;

typedef struct {
    int devNum;
    McuOnDevice device;
} Connected_Devices;
```

---

## YccDrvv3.dll (Driver de bajo nivel para acceso I/O)
**Ruta**: `C:\Program Files\GIGABYTE\Control Center\YccDrvv3.dll`
**Tamaño**: 252,528 bytes

Esta DLL provee acceso a puertos I/O del hardware (necesita privilegios):
```c
uint8_t  gb_inp(uint32_t Port)      // in byte
uint16_t gb_inpw(uint32_t Port)     // in word
uint32_t gb_inpd(uint32_t Port)     // in dword
void     gb_outp(uint32_t Port, uint8_t DataValue)   // out byte
void     gb_outpw(uint32_t Port, uint16_t DataValue) // out word
void     gb_outpd(uint32_t Port, uint64_t DataValue) // out dword
```

Estos son los métodos directos de I/O de puerto (usando instrucciones IN/OUT del x86).
En Linux, esto se hace con `/dev/port` o `ioperm()`.
