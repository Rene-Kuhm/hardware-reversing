# Enums y Modos — RGB Fusion / GCC

Extraídos por reflection de LedIoControl.dll y RgbCommon.dll

---

## LedMode (genérico, IT86xx chips)
```
Off          = 0
DarkOff      = 1
StillMode    = 2
BreathMode   = 3
BeatMode     = 4
AutoMode     = 5
FlashMode    = 6
RandomMode   = 7
WaveMode     = 8
SceneMode    = 9
ConditionMode = 10
DFlashMode   = 11
ColorCycle   = 12
Unknown      = -1
```

## LMode_8297 (IT8297 chip — AORUS high-end)
```
Null             = 0
Static           = 1
Pulse            = 2
Flash            = 3
ColorCycle       = 4
Meteor           = 5
Wave             = 6
Ripple           = 7
Random           = 8
Wava1            = 9
Wave2..Wave40    = 10..48
Off              = 50
DFlash           = 51
Transition       = 52
Demo             = 53
FlashUseBeatMode = 54
DFlashUseBeatMode = 55
Beat             = 56
SWave            = 100
StarSlide        = 101
SMeteor          = 102
Shaking          = 103
Explode          = 104
Recover          = 105
DoubleMeteor     = 106
ColorStack       = 107
ColorStack_Mono  = 108
ColorRain        = 109
ColorRain_Mono   = 110
DWave1           = 111
SWaveMode1       = 112
DG_Static        = 113
DG_Pulse         = 114
DG_Flash         = 115
DG_DFlash        = 116
DG_ColorCycle    = 117
Monitor_Mode0    = 118
Monitor_Mode1    = 119
Monitor_Mode2    = 120
TriColor         = 121
SysPattern1      = 122
SysPattern2      = 123
SysPattern1_MCU1 = 124
SysPattern2_MCU1 = 125
```

## PatternType (en configuración XML y UI)
```
Still          = 0
Breath         = 1
Beat           = 2
MixColor       = 3
Flash          = 4
Random         = 5
Wave           = 6
Scenes         = 7
Off            = 8
Auto           = 9
Other          = 10
DFlash         = 11
StarSlide      = 12
Meteor         = 13
Shaking        = 14
Explode        = 15
Recover        = 16
DoubleMeteor   = 17
ColorStack     = 18
ColorRain      = 19
ColorStack_Mono = 20
ColorRain_Mono = 21
Demo           = 22
Default        = 23
DDR1..DDR8     = 24..31
Keyboard1      = 30
Keyboard2      = 31
Game           = 32
DWave1         = 33
SWave          = 34
MCURandom      = 35
Wave1          = 36
Wave2          = 37
VGA_GRADIENT   = 38
VGA_COLOR_SHIFT = 39
VGA_CLAWS      = 40
VGA_RAINBOW_LOOP = 41
VGA_THREE_COLOR_CYCLING = 42
VGA_WAVE       = 43
VGA_COOL_CYCLE = 44
Monitor_Mode0  = 45
Monitor_Mode1  = 46
Monitor_Mode2  = 47
VGA_RADIATE    = 48
VGA_Monitor    = 49
TriColor       = 50
Gradient       = 51
ColorShift     = 52
_3_Wave        = 53
_7_Wave        = 54
VGA_PACMAN     = 55
SPIN           = 56
SWITCH         = 57
DAZZLE         = 58
_2_COLOR_CYCLING = 59
_7_COLOR_CYCLING = 60
LEGO           = 61
AORURA         = 62
CPU_TEMPA      = 63
CPU_TEMPB      = 64
COUNTER_CLOCK_WISE = 65
_3_COLOR_CYCLING = 66
DDR7           = 67
DDR8           = 68
AllRainbow     = 69
Custom1        = 70
ARGB20_Func    = 71
MCU_Wave       = 72
LEGO_2         = 611
```

## AudioLedMode
```
LedOff         = 0
LedOn          = 1
LedTempo       = 2
LedBreath      = 3
LedFlash       = 4
LedDoubleFlash = 5
LedColorCycle  = 6
LedRanDom      = 7
LedBoot        = 8
LedNotSupport  = 99
```

## LEDColor (3-color mode — boards antiguos)
```
Blue        = 1
Green       = 2
Light_Green = 3
Red         = 4
Pink        = 5
Yellow      = 6
White       = 7
Auto        = 8
Orange      = 9
```

## LedFunc (capacidades del chip)
```
NOT_SUPPORT                    = 0
ONOFF_CONTROL_ONLY             = 1
PLUSE_BAET_MODE_SUPPORT        = 2
REAR_PANEL_SUPPORT             = 3
TRHEE_COLOR_SUPPORT            = 4
TRHEE_COLOR_SUPPORT_BUT_REAR_PANEL = 5
TRUE_COLOR_SUPPORT             = 6
TRUE_COLOR_SUPPORT_BUT_REAR_PANEL  = 7
```

## LED_CTRL_BY (quién controla los LEDs)
```
Unknown       = 0
CannonLake_PCH = 1
IT8686        = 2
IT8688        = 3
IT8295        = 4
IT8297        = 5
```

## Chip IDs (ITE chips)
```
IT8620E  = 0x8620 (34336)
IT8626   = 0x8626 (34342)
IT8686E  = 0x8686 (34438)
IT8688   = 0x8688 (34440)
IT8689   = 0x8689 (34441)
IT8696   = 0x8696 (34454)
IT8728F  = 0x8728 (34600)
IT8791E  = 0x8791 (34611)
IT8790F  = 0x8790 (34704)
```

## MBIdentify (placa madre)
```
UnknownMB = 0
I_200Ser  = 1   Intel 200-series
I_X299    = 2
I_B360    = 3
I_Z370    = 4
I_H370    = 5
I_Z390    = 6   ← IT8688
I_H310    = 7
I_Z490    = 8   ← IT8688
I_B460    = 9
I_H410    = 10
I_H470    = 11
I_H510    = 12
I_Z590    = ?
I_Z690    = ?   ← IT8295
I_B660    = ?   ← IT8295
I_Z790    = ?   ← IT8295 (nuestro caso)
I_B760    = ?   ← IT8295
A_AM4     = 101 AMD AM4
A_AX370   = 102
A_X399    = 103
A_AX470   = 104
A_B450    = 105
A_X570    = 106 ← IT8688
```

---

## Velocidades (sp.xml — IT8295)

### Breathing
| sp | Period (ms) |
|----|-------------|
| 0  | 1600        |
| 5  | 800         |
| 9  | 400         |

### Flash
| sp | On | Fade | Off |
|----|-----|------|-----|
| 0  | 100 | 200  | 2400|
| 5  | 100 | 200  | 1400|
| 9  | 100 | 200  | 600 |

### Wave / Cycle
| sp | Period (ms) |
|----|-------------|
| 0  | 2400        |
| 5  | 700         |
| 9  | 300         |
