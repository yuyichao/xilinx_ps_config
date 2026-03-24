#!/usr/bin/env python

from dataclasses import dataclass, field
from enum import Enum
from math import ceil
import re

class APUClkRatio(Enum):
    RATIO_621 = 0
    RATIO_421 = 1
    @classmethod
    def load(cls, s):
        if s == '6:2:1':
            return cls.RATIO_621
        elif s == '4:2:1':
            return cls.RATIO_421

class ClockSource(Enum):
    ARM = 0
    DDR = 1
    IO = 2
    Extern = 3
    @classmethod
    def load(cls, s):
        val = cls.load_pll(s)
        if val is not None:
            return val
        if s == 'External':
            return cls.Extern

    @classmethod
    def load_pll(cls, s):
        if s == 'ARM PLL':
            return cls.ARM
        elif s == 'DDR PLL':
            return cls.DDR
        elif s == 'IO PLL':
            return cls.IO

class DDRPriority(Enum):
    Low = 0x3ff
    Medium = 0x200
    High = 0x4
    @classmethod
    def load(cls, s):
        if s == 'Low':
            return cls.Low
        elif s == 'Medium':
            return cls.Medium
        elif s == 'High':
            return cls.High

class DDRQueuePartition(Enum):
    # Values are the corresponding ddrc_lpr_num_entries
    HPR0_LPR32 = 31
    HPR8_LPR24 = 23
    HPR16_LPR16 = 15
    HPR24_LPR8 = 7
    HPR32_LPR0 = 0
    @classmethod
    def load(cls, s):
        if s == 'HPR(0)/LPR(32)':
            return cls.HPR0_LPR32
        elif s == 'HPR(8)/LPR(24)':
            return cls.HPR8_LPR24
        elif s == 'HPR(16)/LPR(16)':
            return cls.HPR16_LPR16
        elif s == 'HPR(24)/LPR(8)':
            return cls.HPR24_LPR8
        elif s == 'HPR(32)/LPR(0)':
            return cls.HPR32_LPR0

class IOType(Enum):
    LVCMOS18 = 1
    LVCMOS25 = 2
    LVCMOS33 = 3
    HSTL = 4
    def is18(self):
        return (self.value == IOType.LVCMOS18.value or
                self.value == IOType.HSTL.value)
    @classmethod
    def load(cls, s):
        if s == 'LVCMOS 1.8V':
            return cls.LVCMOS18
        elif s == 'LVCMOS 2.5V':
            return cls.LVCMOS25
        elif s == 'LVCMOS 3.3V':
            return cls.LVCMOS33
        elif s == 'HSTL 1.8V':
            return cls.HSTL

class IOSlew(Enum):
    Slow = 0
    Fast = 1
    @classmethod
    def load(cls, s):
        if s == "slow":
            return cls.Slow
        elif s == "fast":
            return cls.Fast

class IODirection(Enum):
    In = 0
    Out = 1
    InOut = 2
    @classmethod
    def load(cls, s):
        if s == "in":
            return cls.In
        elif s == "out":
            return cls.Out
        elif s == "inout":
            return cls.InOut

class QSPIMode(Enum):
    Disabled = 0
    Single_x1 = 1
    Single_x2 = 2
    Single_x4 = 3
    Dual_x1 = 4
    Dual_x2 = 5
    Dual_x4 = 6
    Parallel_x8 = 7

class NORMIO0Role(Enum):
    Disabled = 0
    CS1 = 1
    ADDR25 = 2

class ENET0IO(Enum):
    EMIO = 0
    MIO_16_27 = 1
    @classmethod
    def load(cls, s):
        if s == "MIO 16 .. 27":
            return cls.MIO_16_27
        elif s == "EMIO":
            return cls.EMIO

class ENET1IO(Enum):
    EMIO = 0
    MIO_28_39 = 1
    @classmethod
    def load(cls, s):
        if s == "MIO 28 .. 39":
            return cls.MIO_16_27
        elif s == "EMIO":
            return cls.EMIO

class I2C0IO(Enum):
    EMIO = 0
    MIO_10_11 = 10
    MIO_14_15 = 14
    MIO_18_19 = 18
    MIO_22_23 = 22
    MIO_26_27 = 26
    MIO_30_31 = 30
    MIO_34_35 = 34
    MIO_38_39 = 38
    MIO_42_43 = 42
    MIO_46_47 = 46
    MIO_50_51 = 50
    @classmethod
    def load(cls, s):
        if s == "EMIO":
            return cls.EMIO
        elif s == "MIO 10 .. 11":
            return cls.MIO_10_11
        elif s == "MIO 14 .. 15":
            return cls.MIO_14_15
        elif s == "MIO 18 .. 19":
            return cls.MIO_18_19
        elif s == "MIO 22 .. 23":
            return cls.MIO_22_23
        elif s == "MIO 26 .. 27":
            return cls.MIO_26_27
        elif s == "MIO 30 .. 31":
            return cls.MIO_30_31
        elif s == "MIO 34 .. 35":
            return cls.MIO_34_35
        elif s == "MIO 38 .. 39":
            return cls.MIO_38_39
        elif s == "MIO 42 .. 43":
            return cls.MIO_42_43
        elif s == "MIO 46 .. 47":
            return cls.MIO_46_47
        elif s == "MIO 50 .. 51":
            return cls.MIO_50_51

class I2C1IO(Enum):
    EMIO = 0
    MIO_12_13 = 12
    MIO_16_17 = 16
    MIO_20_21 = 20
    MIO_24_25 = 24
    MIO_28_29 = 28
    MIO_32_33 = 32
    MIO_36_37 = 36
    MIO_40_41 = 40
    MIO_44_45 = 44
    MIO_48_49 = 48
    MIO_52_53 = 52
    @classmethod
    def load(cls, s):
        if s == "EMIO":
            return cls.EMIO
        elif s == "MIO 12 .. 13":
            return cls.MIO_12_13
        elif s == "MIO 16 .. 17":
            return cls.MIO_16_17
        elif s == "MIO 20 .. 21":
            return cls.MIO_20_21
        elif s == "MIO 24 .. 25":
            return cls.MIO_24_25
        elif s == "MIO 28 .. 29":
            return cls.MIO_28_29
        elif s == "MIO 32 .. 33":
            return cls.MIO_32_33
        elif s == "MIO 36 .. 37":
            return cls.MIO_36_37
        elif s == "MIO 40 .. 41":
            return cls.MIO_40_41
        elif s == "MIO 44 .. 45":
            return cls.MIO_44_45
        elif s == "MIO 48 .. 49":
            return cls.MIO_48_49
        elif s == "MIO 52 .. 53":
            return cls.MIO_52_53

class SD0IO(Enum):
    EMIO = 0
    MIO_16_21 = 16
    MIO_28_33 = 28
    MIO_40_45 = 40
    @classmethod
    def load(cls, s):
        if s == "EMIO":
            return cls.EMIO
        elif s == "MIO 16 .. 21":
            return cls.MIO_16_21
        elif s == "MIO 28 .. 33":
            return cls.MIO_28_33
        elif s == "MIO 40 .. 45":
            return cls.MIO_40_45

class SD1IO(Enum):
    EMIO = 0
    MIO_10_15 = 10
    MIO_22_27 = 22
    MIO_34_39 = 34
    MIO_46_51 = 46
    @classmethod
    def load(cls, s):
        if s == "EMIO":
            return cls.EMIO
        elif s == "MIO 10 .. 15":
            return cls.MIO_10_15
        elif s == "MIO 22 .. 27":
            return cls.MIO_22_27
        elif s == "MIO 34 .. 39":
            return cls.MIO_34_39
        elif s == "MIO 46 .. 51":
            return cls.MIO_46_51

class UART0IO(Enum):
    EMIO = 0
    MIO_10_11 = 10
    MIO_14_15 = 14
    MIO_18_19 = 18
    MIO_22_23 = 22
    MIO_26_27 = 26
    MIO_30_31 = 30
    MIO_34_35 = 34
    MIO_38_39 = 38
    MIO_42_43 = 42
    MIO_46_47 = 46
    MIO_50_51 = 50
    @classmethod
    def load(cls, s):
        if s == "EMIO":
            return cls.EMIO
        elif s == "MIO 10 .. 11":
            return cls.MIO_10_11
        elif s == "MIO 14 .. 15":
            return cls.MIO_14_15
        elif s == "MIO 18 .. 19":
            return cls.MIO_18_19
        elif s == "MIO 22 .. 23":
            return cls.MIO_22_23
        elif s == "MIO 26 .. 27":
            return cls.MIO_26_27
        elif s == "MIO 30 .. 31":
            return cls.MIO_30_31
        elif s == "MIO 34 .. 35":
            return cls.MIO_34_35
        elif s == "MIO 38 .. 39":
            return cls.MIO_38_39
        elif s == "MIO 42 .. 43":
            return cls.MIO_42_43
        elif s == "MIO 46 .. 47":
            return cls.MIO_46_47
        elif s == "MIO 50 .. 51":
            return cls.MIO_50_51

class UART1IO(Enum):
    EMIO = 0
    MIO_8_9 = 8
    MIO_12_13 = 12
    MIO_16_17 = 16
    MIO_20_21 = 20
    MIO_24_25 = 24
    MIO_28_29 = 28
    MIO_32_33 = 32
    MIO_36_37 = 36
    MIO_40_41 = 40
    MIO_44_45 = 44
    MIO_48_49 = 48
    MIO_52_53 = 52
    @classmethod
    def load(cls, s):
        if s == "EMIO":
            return cls.EMIO
        elif s == "MIO 8 .. 9":
            return cls.MIO_8_9
        elif s == "MIO 12 .. 13":
            return cls.MIO_12_13
        elif s == "MIO 16 .. 17":
            return cls.MIO_16_17
        elif s == "MIO 20 .. 21":
            return cls.MIO_20_21
        elif s == "MIO 24 .. 25":
            return cls.MIO_24_25
        elif s == "MIO 28 .. 29":
            return cls.MIO_28_29
        elif s == "MIO 32 .. 33":
            return cls.MIO_32_33
        elif s == "MIO 36 .. 37":
            return cls.MIO_36_37
        elif s == "MIO 40 .. 41":
            return cls.MIO_40_41
        elif s == "MIO 44 .. 45":
            return cls.MIO_44_45
        elif s == "MIO 48 .. 49":
            return cls.MIO_48_49
        elif s == "MIO 52 .. 53":
            return cls.MIO_52_53

class SPI0IO(Enum):
    EMIO = 0
    MIO_16_21 = 16
    MIO_28_33 = 28
    MIO_40_45 = 40
    @classmethod
    def load(cls, s):
        if s == "EMIO":
            return cls.EMIO
        elif s == "MIO 16 .. 21":
            return cls.MIO_16_21
        elif s == "MIO 28 .. 33":
            return cls.MIO_28_33
        elif s == "MIO 40 .. 45":
            return cls.MIO_40_45

class SPI1IO(Enum):
    EMIO = 0
    MIO_10_15 = 10
    MIO_22_27 = 22
    MIO_34_39 = 34
    MIO_46_51 = 46
    @classmethod
    def load(cls, s):
        if s == "EMIO":
            return cls.EMIO
        elif s == "MIO 10 .. 15":
            return cls.MIO_10_15
        elif s == "MIO 22 .. 27":
            return cls.MIO_22_27
        elif s == "MIO 34 .. 39":
            return cls.MIO_34_39
        elif s == "MIO 46 .. 51":
            return cls.MIO_46_51

class CAN0IO(Enum):
    EMIO = 0
    MIO_10_11 = 10
    MIO_14_15 = 14
    MIO_18_19 = 18
    MIO_22_23 = 22
    MIO_26_27 = 26
    MIO_30_31 = 30
    MIO_34_35 = 34
    MIO_38_39 = 38
    MIO_42_43 = 42
    MIO_46_47 = 46
    MIO_50_51 = 50
    @classmethod
    def load(cls, s):
        if s == "EMIO":
            return cls.EMIO
        elif s == "MIO 10 .. 11":
            return cls.MIO_10_11
        elif s == "MIO 14 .. 15":
            return cls.MIO_14_15
        elif s == "MIO 18 .. 19":
            return cls.MIO_18_19
        elif s == "MIO 22 .. 23":
            return cls.MIO_22_23
        elif s == "MIO 26 .. 27":
            return cls.MIO_26_27
        elif s == "MIO 30 .. 31":
            return cls.MIO_30_31
        elif s == "MIO 34 .. 35":
            return cls.MIO_34_35
        elif s == "MIO 38 .. 39":
            return cls.MIO_38_39
        elif s == "MIO 42 .. 43":
            return cls.MIO_42_43
        elif s == "MIO 46 .. 47":
            return cls.MIO_46_47
        elif s == "MIO 50 .. 51":
            return cls.MIO_50_51

class CAN1IO(Enum):
    EMIO = 0
    MIO_8_9 = 8
    MIO_12_13 = 12
    MIO_16_17 = 16
    MIO_20_21 = 20
    MIO_24_25 = 24
    MIO_28_29 = 28
    MIO_32_33 = 32
    MIO_36_37 = 36
    MIO_40_41 = 40
    MIO_44_45 = 44
    MIO_48_49 = 48
    MIO_52_53 = 52
    @classmethod
    def load(cls, s):
        if s == "EMIO":
            return cls.EMIO
        elif s == "MIO 8 .. 9":
            return cls.MIO_8_9
        elif s == "MIO 12 .. 13":
            return cls.MIO_12_13
        elif s == "MIO 16 .. 17":
            return cls.MIO_16_17
        elif s == "MIO 20 .. 21":
            return cls.MIO_20_21
        elif s == "MIO 24 .. 25":
            return cls.MIO_24_25
        elif s == "MIO 28 .. 29":
            return cls.MIO_28_29
        elif s == "MIO 32 .. 33":
            return cls.MIO_32_33
        elif s == "MIO 36 .. 37":
            return cls.MIO_36_37
        elif s == "MIO 40 .. 41":
            return cls.MIO_40_41
        elif s == "MIO 44 .. 45":
            return cls.MIO_44_45
        elif s == "MIO 48 .. 49":
            return cls.MIO_48_49
        elif s == "MIO 52 .. 53":
            return cls.MIO_52_53

class TTC0IO(Enum):
    EMIO = 0
    MIO_18_19 = 18
    MIO_30_31 = 30
    MIO_42_43 = 42
    @classmethod
    def load(cls, s):
        if s == "EMIO":
            return cls.EMIO
        elif s == "MIO 18 .. 19":
            return cls.MIO_18_19
        elif s == "MIO 30 .. 31":
            return cls.MIO_30_31
        elif s == "MIO 42 .. 43":
            return cls.MIO_42_43

class TTC1IO(Enum):
    EMIO = 0
    MIO_10_15 = 10
    MIO_22_27 = 22
    MIO_34_39 = 34
    MIO_46_51 = 46
    @classmethod
    def load(cls, s):
        if s == "EMIO":
            return cls.EMIO
        elif s == "MIO 10 .. 15":
            return cls.MIO_10_15
        elif s == "MIO 22 .. 27":
            return cls.MIO_22_27
        elif s == "MIO 34 .. 39":
            return cls.MIO_34_39
        elif s == "MIO 46 .. 51":
            return cls.MIO_46_51

class WDTIO(Enum):
    EMIO = 0
    MIO_14_15 = 14
    MIO_26_27 = 26
    MIO_38_39 = 38
    MIO_50_51 = 50
    MIO_52_53 = 52
    @classmethod
    def load(cls, s):
        if s == "EMIO":
            return cls.EMIO
        elif s == "MIO 14 .. 15":
            return cls.MIO_14_15
        elif s == "MIO 26 .. 27":
            return cls.MIO_26_27
        elif s == "MIO 38 .. 39":
            return cls.MIO_38_39
        elif s == "MIO 50 .. 51":
            return cls.MIO_50_51
        elif s == "MIO 52 .. 53":
            return cls.MIO_52_53

def _load_val(kws, name, default):
    val = kws.get(name, default)
    if val == '':
        val = default
    if val is None:
        raise ValueError(f"Missing configure key {name}")
    return val

def _load_val_opt(kws, name):
    val = kws.get(name)
    if val == '':
        return
    return val

def _load_int(kws, name, default=None):
    val = _load_val(kws, name, default)
    if not isinstance(val, int):
        raise TypeError(f"Configure key {name} has the wrong type: {val}")
    return val

def _load_bool(kws, name, default=None):
    val = _load_val(kws, name, default)
    if isinstance(val, bool):
        return val
    if isinstance(val, int):
        if val not in (0, 1):
            raise TypeError(f"Configure key {name} has the wrong value: {val}")
        return bool(val)
    raise TypeError(f"Configure key {name} has the wrong type: {val}")

def _load_float(kws, name, default=None):
    val = _load_val(kws, name, default)
    if not isinstance(val, float):
        if not isinstance(val, int):
            raise TypeError(f"Configure key {name} has the wrong type: {val}")
        val = float(val)
    return val

def _load_cb(kws, name, cb, default=None):
    strval = kws.get(name)
    if strval == '' or strval is None:
        if default is None:
            raise ValueError(f"Missing configure key {name}")
        return default
    if isinstance(cb, type):
        cb = cb.load
    val = cb(strval)
    if val is None:
        raise TypeError(f"Invalid value {strval} for option: {name}")
    return val

def _load_cb_opt(kws, name, cb):
    strval = _load_val_opt(kws, name)
    if strval is None:
        return
    if isinstance(cb, type):
        cb = cb.load
    val = cb(strval)
    if val is None:
        raise TypeError(f"Invalid value {strval} for option: {name}")
    return val

@dataclass
class FClock:
    ENABLE: bool
    CLKSRC: ClockSource
    DIVISOR0: int
    DIVISOR1: int
    config: object = field(repr=False)

    @property
    def FREQMHZ(self):
        return self.config.get_freqmhz(self.CLKSRC) / (self.DIVISOR0 * self.DIVISOR1)

    @classmethod
    def load(cls, kws, idx, parent):
        en = _load_bool(kws, f'EN_CLK{idx}_PORT', False)
        return cls(en, _load_cb(kws, f'FCLK{idx}_PERIPHERAL_CLKSRC',
                                ClockSource, ClockSource.IO),
                   _load_int(kws, f'FCLK{idx}_PERIPHERAL_DIVISOR0', None if en else 1),
                   _load_int(kws, f'FCLK{idx}_PERIPHERAL_DIVISOR1', None if en else 1),
                   parent)

@dataclass
class MIOPin:
    ID: int
    IOTYPE: IOType | None = None
    DIRECTION: IODirection | None = None
    SLEW: IOSlew = IOSlew.Slow
    PULLUP: bool = False
    IS_GPIO: bool = False
    SEL: int = 0

    @property
    def used(self):
        return self.IOTYPE is not None

    def reset(self):
        self.IOTYPE = None
        self.DIRECTION = None
        self.SLEW = IOSlew.Slow
        self.PULLUP = False
        self.IS_GPIO = False
        self.SELECT = 0

    def set_use(self, iotype, direction, is_gpio, select):
        self.IOTYPE = iotype
        self.DIRECTION = direction
        self.IS_GPIO = is_gpio
        self.SELECT = select

    def get_reg(self):
        tri_enable = self.DIRECTION == IODirection.In
        select = self.SELECT
        speed = self.SLEW.value
        io_type = self.IOTYPE.value
        pullup = self.PULLUP
        disable_rcvr = self.IOTYPE == IOType.HSTL and self.DIRECTION == IODirection.Out

        return (tri_enable | (select << 1) | (speed << 8) |
                (io_type << 9) | (pullup << 12) | (disable_rcvr << 13))

@dataclass(kw_only=True)
class SMCCycles:
    T_RC: int = 2 # T0
    T_WC: int = 2 # T1
    T_CEOE: int = 1 # T2
    T_WP: int = 1 # T3
    T_PC: int = 1 # T4
    T_TR: int = 1 # T5
    WE_TIME: int = 1 # T6

    def get_reg(self):
        # [3:0] Set_t0 = T_RC
        # [7:4] Set_t1 = T_WC
        # [10:8] Set_t2 = T_CEOE
        # [13:11] Set_t3 = T_WP
        # [16:14] Set_t4 = T_PC
        # [19:17] Set_t5 = T_TR
        # [23:20] Set_t6 = WE_TIME
        return (self.T_RC | (self.T_WC << 4) | (self.T_CEOE << 8) | (self.T_WP << 11) |
                (self.T_PC << 14) | (self.T_TR << 17) | (self.WE_TIME << 20))

    @classmethod
    def load(cls, kws, prefix):
        return cls(**{name: _load_int(kws, f'{prefix}{name}')
                      for name in ('T_CEOE', 'T_PC', 'T_RC', 'T_TR', 'T_WC', 'T_WP')})

_mio_pin_regex = re.compile('MIO ([0-9]+)')

class ZynqConfig:
    def __init__(self, **kws):
        self.CRYSTAL_FREQMHZ = _load_float(kws, 'CRYSTAL_PERIPHERAL_FREQMHZ')
        self.ARM_FBDIV = _load_int(kws, 'ARMPLL_CTRL_FBDIV')
        self.DDR_FBDIV = _load_int(kws, 'DDRPLL_CTRL_FBDIV')
        self.IO_FBDIV = _load_int(kws, 'IOPLL_CTRL_FBDIV')

        self.APU_CLK_RATIO = _load_cb(kws, 'APU_CLK_RATIO_ENABLE', APUClkRatio)

        def load_pllsrc(name, default):
            return _load_cb(kws, name, ClockSource.load_pll, default)

        self.CPU_CLKSRC = load_pllsrc('CPU_PERIPHERAL_CLKSRC', ClockSource.ARM)
        self.CPU_DIVISOR0 = _load_int(kws, 'CPU_PERIPHERAL_DIVISOR0', 2)

        if load_pllsrc('DDR_PERIPHERAL_CLKSRC', ClockSource.DDR) != ClockSource.DDR:
            raise ValueError("Unsupported clock source for DDR")
        # self.DDR_CLKSRC = ClockSource.DDR # Hardwired
        self.DDR_DIVISOR0 = _load_int(kws, 'DDR_PERIPHERAL_DIVISOR0', 2)
        self.DDR_PRIORITY_READPORT = (
            _load_cb(kws, 'DDR_PRIORITY_READPORT_0', DDRPriority, DDRPriority.Low),
            _load_cb(kws, 'DDR_PRIORITY_READPORT_1', DDRPriority, DDRPriority.Low),
            _load_cb(kws, 'DDR_PRIORITY_READPORT_2', DDRPriority, DDRPriority.Low),
            _load_cb(kws, 'DDR_PRIORITY_READPORT_3', DDRPriority, DDRPriority.Low),
        )
        self.DDR_PRIORITY_WRITEPORT = (
            _load_cb(kws, 'DDR_PRIORITY_WRITEPORT_0', DDRPriority, DDRPriority.Low),
            _load_cb(kws, 'DDR_PRIORITY_WRITEPORT_1', DDRPriority, DDRPriority.Low),
            _load_cb(kws, 'DDR_PRIORITY_WRITEPORT_2', DDRPriority, DDRPriority.Low),
            _load_cb(kws, 'DDR_PRIORITY_WRITEPORT_3', DDRPriority, DDRPriority.Low),
        )
        self.DDR_PORT_HPR_ENABLE = (
            _load_bool(kws, 'DDR_PORT0_HPR_ENABLE', False),
            _load_bool(kws, 'DDR_PORT1_HPR_ENABLE', False),
            _load_bool(kws, 'DDR_PORT2_HPR_ENABLE', False),
            _load_bool(kws, 'DDR_PORT3_HPR_ENABLE', False),
        )
        self.DDR_HPRLPR_QUEUE_PARTITION = _load_cb(kws, 'DDR_HPRLPR_QUEUE_PARTITION',
                                                   DDRQueuePartition,
                                                   DDRQueuePartition.HPR0_LPR32)
        self.DDR_HPR_TO_CRITICAL_PRIORITY_LEVEL = _load_int(
            kws, 'DDR_HPR_TO_CRITICAL_PRIORITY_LEVEL', 15)
        self.DDR_LPR_TO_CRITICAL_PRIORITY_LEVEL = _load_int(
            kws, 'DDR_LPR_TO_CRITICAL_PRIORITY_LEVEL', 2)
        self.DDR_WRITE_TO_CRITICAL_PRIORITY_LEVEL = _load_int(
            kws, 'DDR_WRITE_TO_CRITICAL_PRIORITY_LEVEL', 2)
        if load_pllsrc('DCI_PERIPHERAL_CLKSRC', ClockSource.DDR) != ClockSource.DDR:
            raise ValueError("Unsupported clock source for DCI")
        # self.DCI_CLKSRC = ClockSource.DDR # Hardwired
        self.DCI_DIVISOR0 = _load_int(kws, 'DCI_PERIPHERAL_DIVISOR0')
        self.DCI_DIVISOR1 = _load_int(kws, 'DCI_PERIPHERAL_DIVISOR1')

        # TODO:
        # DDR_TRAIN_DATA_EYE: bool = True
        # DDR_TRAIN_READ_GATE: bool = True
        # DDR_TRAIN_WRITE_LEVEL: bool = True (False for LPDDR2)
        # DDR_MEMORY_TYPE: str = "DDR 3"
        # DDR_SPEED_BIN: str = "DDR3_1066F"

        self.DDR_AL = _load_int(kws, 'UIPARAM_DDR_AL', 0)
        self.DDR_BL = _load_int(kws, 'UIPARAM_DDR_BL') # 4 or 8 (or 16 for LPDDR2)
        self.DDR_CL = _load_int(kws, 'UIPARAM_DDR_CL')
        self.DDR_CWL = _load_int(kws, 'UIPARAM_DDR_CWL')
        self.DDR_T_FAW = _load_float(kws, 'UIPARAM_DDR_T_FAW')
        self.DDR_T_RAS_MIN = _load_float(kws, 'UIPARAM_DDR_T_RAS_MIN')
        self.DDR_T_RC = _load_float(kws, 'UIPARAM_DDR_T_RC')
        self.DDR_T_RCD = _load_int(kws, 'UIPARAM_DDR_T_RCD')
        self.DDR_T_RP = _load_int(kws, 'UIPARAM_DDR_T_RP')

        self.DDR_DQS_TO_CLK_DELAY = (
            _load_float(kws, 'UIPARAM_DDR_DQS_TO_CLK_DELAY_0'),
            _load_float(kws, 'UIPARAM_DDR_DQS_TO_CLK_DELAY_1'),
            _load_float(kws, 'UIPARAM_DDR_DQS_TO_CLK_DELAY_2'),
            _load_float(kws, 'UIPARAM_DDR_DQS_TO_CLK_DELAY_3'),
        )
        self.DDR_BOARD_DELAY = (
            _load_float(kws, 'UIPARAM_DDR_BOARD_DELAY0'),
            _load_float(kws, 'UIPARAM_DDR_BOARD_DELAY1'),
            _load_float(kws, 'UIPARAM_DDR_BOARD_DELAY2'),
            _load_float(kws, 'UIPARAM_DDR_BOARD_DELAY3'),
        )
        self.FCLK = [FClock.load(kws, i, self) for i in range(4)]
        self.BANK_VOLTAGE = (_load_cb(kws, 'PRESET_BANK0_VOLTAGE',
                                      IOType, IOType.LVCMOS18),
                             _load_cb(kws, 'PRESET_BANK1_VOLTAGE',
                                      IOType, IOType.LVCMOS18))

        self.MIO_PINS = [MIOPin(i) for i in range(54)]
        self.ENET0_RESET_IO = -1
        self.ENET1_RESET_IO = -1
        self.USB0_RESET_IO = -1
        self.USB1_RESET_IO = -1
        self.I2C0_RESET_IO = -1
        self.I2C1_RESET_IO = -1

        self.QSPI_MODE = QSPIMode.Disabled
        self.NOR_ENABLE = False
        self.NAND_ENABLE = False

        qspi_single_enable = _load_bool(kws, 'QSPI_GRP_SINGLE_SS_ENABLE', False)
        qspi_dual_enable = _load_bool(kws, 'QSPI_GRP_SS1_ENABLE', False)
        qspi_parallel_enable = _load_bool(kws, 'QSPI_GRP_IO1_ENABLE', False)
        qspi_enable = _load_bool(kws, 'QSPI_PERIPHERAL_ENABLE', False)

        if qspi_enable != (qspi_single_enable or qspi_dual_enable or qspi_parallel_enable):
            raise ValueError('Inconsistent QSPI settings')
        if qspi_single_enable + qspi_dual_enable + qspi_parallel_enable > 1:
            raise ValueError('Multiple QSPI modes enabled')

        if qspi_single_enable:
            mode = _load_val(kws, 'SINGLE_QSPI_DATA_MODE', 'x4')
            if mode == 'x1':
                qspi_mode = QSPIMode.Single_x1
            elif mode == 'x2':
                qspi_mode = QSPIMode.Single_x2
            elif mode == 'x4':
                qspi_mode = QSPIMode.Single_x4
            else:
                raise TypeError(f"Invalid value {mode} for option: SINGLE_QSPI_DATA_MODE")
        elif qspi_dual_enable:
            mode = _load_val(kws, 'DUAL_STACK_QSPI_DATA_MODE', 'x4')
            if mode == 'x1':
                qspi_mode = QSPIMode.Dual_x1
            elif mode == 'x2':
                qspi_mode = QSPIMode.Dual_x2
            elif mode == 'x4':
                qspi_mode = QSPIMode.Dual_x4
            else:
                raise TypeError(f"Invalid value {mode} for option: DUAL_STACK_QSPI_DATA_MODE")
        elif qspi_parallel_enable:
            mode = _load_val(kws, 'DUAL_PARALLEL_QSPI_DATA_MODE', "x8")
            if mode != 'x8':
                raise TypeError(f"Invalid value {mode} for option: DUAL_PARALLEL_QSPI_DATA_MODE")
            qspi_mode = QSPIMode.Parallel_x8
        else:
            qspi_mode = QSPIMode.Disabled

        self.QSPI_FBCLK_ENABLE = False
        if qspi_mode != QSPIMode.Disabled:
            self.enable_qspi(qspi_mode,
                             fbclk=_load_bool(kws, 'QSPI_GRP_FBCLK_ENABLE', False))

        self.QSPI_CLKSRC = load_pllsrc('QSPI_PERIPHERAL_CLKSRC', ClockSource.ARM)
        self.QSPI_DIVISOR0 = _load_int(kws, 'QSPI_PERIPHERAL_DIVISOR0', 1)

        self.SMC_CLKSRC = load_pllsrc('SMC_PERIPHERAL_CLKSRC', ClockSource.ARM)
        self.SMC_DIVISOR0 = _load_int(kws, 'SMC_PERIPHERAL_DIVISOR0', 1)

        self.NOR_MIO0_ROLE = NORMIO0Role.Disabled
        self.NOR_CS0_ENABLE = False
        self.NOR_CS0_CYCLES = SMCCycles()
        self.NOR_CS1_CYCLES = SMCCycles()
        if _load_bool(kws, 'NOR_PERIPHERAL_ENABLE', False):
            a25 = _load_bool(kws, 'NOR_GRP_A25_ENABLE', False)
            nor_cs0 = _load_bool(kws, 'NOR_GRP_CS0_ENABLE', False)
            sram_cs0 = _load_bool(kws, 'NOR_GRP_SRAM_CS0_ENABLE', False)
            nor_cs1 = _load_bool(kws, 'NOR_GRP_CS1_ENABLE', False)
            sram_cs1 = _load_bool(kws, 'NOR_GRP_SRAM_CS1_ENABLE', False)
            cs0 = nor_cs0 or sram_cs0
            cs1 = nor_cs1 or sram_cs1
            if a25:
                if cs1:
                    raise ValueError("MIO pin 0 cannot be used for both addr[25] and cs1")
                mio0_role = NORMIO0Role.ADDR25
            elif cs1:
                mio0_role = NORMIO0Role.CS1
            else:
                mio0_role = NORMIO0Role.Disabled
            if nor_cs0:
                cs0_cycles=SMCCycles.load(kws, 'NOR_CS0_')
            elif sram_cs0:
                cs0_cycles=SMCCycles.load(kws, 'NOR_SRAM_CS0_')
            else:
                cs0_cycles=SMCCycles()
            if nor_cs1:
                cs1_cycles=SMCCycles.load(kws, 'NOR_CS1_')
            elif sram_cs1:
                cs1_cycles=SMCCycles.load(kws, 'NOR_SRAM_CS1_')
            else:
                cs1_cycles=SMCCycles()
            self.enable_nor(mio0_role, cs0, cs0_cycles, cs1_cycles)

        self.NAND_D8_ENABLE = False
        self.NAND_CYCLES = SMCCycles()
        if _load_bool(kws, 'NAND_PERIPHERAL_ENABLE', False):
            self.enable_nand(SMCCycles.load(kws, 'NAND_CYCLES_'),
                             _load_bool(kws, 'NAND_GRP_D8_ENABLE', False))

        self.SDIO_CLKSRC = load_pllsrc('SDIO_PERIPHERAL_CLKSRC', ClockSource.IO)
        self.SDIO_DIVISOR0 = _load_int(kws, 'SDIO_PERIPHERAL_DIVISOR0', 1)

        self.SD0_ENABLE = False
        self.SD0_CD_IO = 56
        self.SD0_WP_IO = 55
        self.SD0_POW_IO = -1
        if _load_bool(kws, 'SD0_PERIPHERAL_ENABLE', False):
            io = _load_cb(kws, 'SD0_SD0_IO', SD0IO)
            cd_io = 56 # Connect to EMIO by default to match vivado behavior
            if _load_bool(kws, 'SD0_GRP_CD_ENABLE', False):
                cd_io_str = _load_val(kws, 'SD0_GRP_CD_IO', None)
                if cd_io_str != "EMIO":
                    m = _mio_pin_regex.fullmatch(cd_io_str)
                    if m is not None:
                        cd_io = int(m[1])
                    if cd_io >= 54:
                        raise ValueError(f"Invalid SD0 CD IO: {cd_io_str}")
            wp_io = 55 # Connect to EMIO by default to match vivado behavior
            if _load_bool(kws, 'SD0_GRP_WP_ENABLE', False):
                wp_io_str = _load_val(kws, 'SD0_GRP_WP_IO', None)
                if wp_io_str != "EMIO":
                    m = _mio_pin_regex.fullmatch(wp_io_str)
                    if m is not None:
                        wp_io = int(m[1])
                    if wp_io >= 54:
                        raise ValueError(f"Invalid SD0 WP IO: {wp_io_str}")
            pow_io = -1 # Connect to EMIO by default to match vivado behavior
            if _load_bool(kws, 'SD0_GRP_POW_ENABLE', False):
                pow_io_str = _load_val(kws, 'SD0_GRP_POW_IO', None)
                m = _mio_pin_regex.fullmatch(pow_io_str)
                if m is not None:
                    pow_io = int(m[1])
                if pow_io < 0 or pow_io >= 54 or pow_io % 2 != 0:
                    raise ValueError(f"Invalid SD0 POW IO: {pow_io_str}")
            self.enable_sd0(io, cd_io, wp_io, pow_io)

        self.SD1_ENABLE = False
        self.SD1_CD_IO = 58
        self.SD1_WP_IO = 57
        self.SD1_POW_IO = -1
        if _load_bool(kws, 'SD1_PERIPHERAL_ENABLE', False):
            io = _load_cb(kws, 'SD1_SD1_IO', SD1IO)
            cd_io = 58 # Connect to EMIO by default to match vivado behavior
            if _load_bool(kws, 'SD1_GRP_CD_ENABLE', False):
                cd_io_str = _load_val(kws, 'SD1_GRP_CD_IO', None)
                if cd_io_str != "EMIO":
                    m = _mio_pin_regex.fullmatch(cd_io_str)
                    if m is not None:
                        cd_io = int(m[1])
                    if cd_io >= 54:
                        raise ValueError(f"Invalid SD1 CD IO: {cd_io_str}")
            wp_io = 57 # Connect to EMIO by default to match vivado behavior
            if _load_bool(kws, 'SD1_GRP_WP_ENABLE', False):
                wp_io_str = _load_val(kws, 'SD1_GRP_WP_IO', None)
                if wp_io_str != "EMIO":
                    m = _mio_pin_regex.fullmatch(wp_io_str)
                    if m is not None:
                        wp_io = int(m[1])
                    if wp_io >= 54:
                        raise ValueError(f"Invalid SD1 WP IO: {wp_io_str}")
            pow_io = -1 # Connect to EMIO by default to match vivado behavior
            if _load_bool(kws, 'SD1_GRP_POW_ENABLE', False):
                pow_io_str = _load_val(kws, 'SD1_GRP_POW_IO', None)
                m = _mio_pin_regex.fullmatch(pow_io_str)
                if m is not None:
                    pow_io = int(m[1])
                if pow_io < 0 or pow_io >= 54 or pow_io % 2 != 1:
                    raise ValueError(f"Invalid SD1 POW IO: {pow_io_str}")
            self.enable_sd1(io, cd_io, wp_io, pow_io)

        self.UART_CLKSRC = _load_cb(kws, 'UART_PERIPHERAL_CLKSRC',
                                    ClockSource, ClockSource.IO)
        self.UART_DIVISOR0 = _load_int(kws, 'UART_PERIPHERAL_DIVISOR0')

        self.UART0_ENABLE = False
        if _load_bool(kws, 'UART0_PERIPHERAL_ENABLE', False):
            io = _load_cb(kws, 'UART0_UART0_IO', UART0IO)
            baud = _load_int(kws, 'UART0_BAUD_RATE')
            self.enable_uart0(io, baud)

        self.UART1_ENABLE = False
        if _load_bool(kws, 'UART1_PERIPHERAL_ENABLE', False):
            io = _load_cb(kws, 'UART1_UART1_IO', UART1IO)
            baud = _load_int(kws, 'UART1_BAUD_RATE')
            self.enable_uart1(io, baud)

        self.SPI_CLKSRC = _load_cb(kws, 'SPI_PERIPHERAL_CLKSRC',
                                   ClockSource, ClockSource.IO)
        self.SPI_DIVISOR0 = _load_int(kws, 'SPI_PERIPHERAL_DIVISOR0')

        self.SPI0_ENABLE = False
        self.SPI0_SS1_ENABLE = False
        self.SPI0_SS2_ENABLE = False
        if _load_bool(kws, 'SPI0_PERIPHERAL_ENABLE', False):
            io = _load_cb(kws, 'SPI0_SPI0_IO', SPI0IO)
            ss1 = _load_bool(kws, 'SPI0_GRP_SS1_ENABLE', False)
            ss2 = _load_bool(kws, 'SPI0_GRP_SS2_ENABLE', False)
            self.enable_spi0(io, ss1, ss2)

        self.SPI1_ENABLE = False
        self.SPI1_SS1_ENABLE = False
        self.SPI1_SS2_ENABLE = False
        if _load_bool(kws, 'SPI1_PERIPHERAL_ENABLE', False):
            io = _load_cb(kws, 'SPI1_SPI1_IO', SPI1IO)
            ss1 = _load_bool(kws, 'SPI1_GRP_SS1_ENABLE', False)
            ss2 = _load_bool(kws, 'SPI1_GRP_SS2_ENABLE', False)
            self.enable_spi1(io, ss1, ss2)

        self.CAN_CLKSRC = _load_cb(kws, 'CAN_PERIPHERAL_CLKSRC',
                                   ClockSource, ClockSource.IO)
        self.CAN_DIVISOR0 = _load_int(kws, 'CAN_PERIPHERAL_DIVISOR0')
        self.CAN_DIVISOR1 = _load_int(kws, 'CAN_PERIPHERAL_DIVISOR1')

        self.CAN0_ENABLE = False
        self.CAN0_CLK_IO = -1
        if _load_bool(kws, 'CAN0_PERIPHERAL_ENABLE', False):
            io = _load_cb(kws, 'CAN0_CAN0_IO', CAN0IO)
            clk_io = -1
            if _load_bool(kws, 'CAN0_GRP_CLK_ENABLE', False):
                clk_io_str = _load_val(kws, 'CAN0_GRP_CLK_IO', None)
                m = _mio_pin_regex.fullmatch(clk_io_str)
                if m is not None:
                    clk_io = int(m[1])
                if clk_io < 0 or clk_io >= 54:
                    raise ValueError(f"Invalid CAN0 CLK IO: {clk_io_str}")
            self.enable_can0(io, clk_io)

        self.CAN1_ENABLE = False
        self.CAN1_CLK_IO = -1
        if _load_bool(kws, 'CAN1_PERIPHERAL_ENABLE', False):
            io = _load_cb(kws, 'CAN1_CAN1_IO', CAN1IO)
            clk_io = -1
            if _load_bool(kws, 'CAN1_GRP_CLK_ENABLE', False):
                clk_io_str = _load_val(kws, 'CAN1_GRP_CLK_IO', None)
                m = _mio_pin_regex.fullmatch(clk_io_str)
                if m is not None:
                    clk_io = int(m[1])
                if clk_io < 0 or clk_io >= 54:
                    raise ValueError(f"Invalid CAN1 CLK IO: {clk_io_str}")
            self.enable_can1(io, clk_io)

        self.TTC0_IO = TTC0IO.EMIO
        if _load_bool(kws, 'TTC0_PERIPHERAL_ENABLE', False):
            io = _load_cb(kws, 'TTC0_TTC0_IO', TTC0IO)
            self.enable_ttc0(io)

        self.TTC1_IO = TTC1IO.EMIO
        if _load_bool(kws, 'TTC1_PERIPHERAL_ENABLE', False):
            io = _load_cb(kws, 'TTC1_TTC1_IO', TTC1IO)
            self.enable_ttc1(io)

        self.WDT_ENABLE = False
        self.WDT_IO = WDTIO.EMIO
        self.WDT_CLK_EXTERNAL = False
        if _load_bool(kws, 'WDT_PERIPHERAL_ENABLE', False):
            io = _load_cb(kws, 'WDT_WDT_IO', WDTIO)
            clksrc = _load_val(kws, 'WDT_PERIPHERAL_CLKSRC', None)
            if clksrc == "CPU_1X":
                clk_extern = False
            elif clksrc == "External":
                clk_extern = True
            else:
                raise ValueError(f'Unknown WDT clock source: {clk_extern}')
            self.enable_wdt(io, clk_extern)

        self.GPIO_MIO_ENABLE = False
        if _load_bool(kws, 'GPIO_MIO_GPIO_ENABLE', False):
            self.enable_mio_gpio()

        self.ENET0_CLKSRC = _load_cb(kws, 'ENET0_PERIPHERAL_CLKSRC',
                                     ClockSource, ClockSource.IO)
        self.ENET0_DIVISOR0 = _load_int(kws, 'ENET0_PERIPHERAL_DIVISOR0')
        self.ENET0_DIVISOR1 = _load_int(kws, 'ENET0_PERIPHERAL_DIVISOR1')
        self.ENET0_ENABLE = False
        self.ENET0_MDIO_ENABLE = False

        if _load_bool(kws, 'ENET0_PERIPHERAL_ENABLE', False):
            mdio = _load_bool(kws, 'ENET0_GRP_MDIO_ENABLE', False)
            if mdio:
                mdio_io = _load_val(kws, 'ENET0_GRP_MDIO_IO', "MIO 52 .. 53")
                if mdio_io == "EMIO":
                    mdio = False
                elif mdio_io != "MIO 52 .. 53":
                    raise ValueError(f"Invalid MDIO IO: {mdio_io}")
            reset_io = -1
            if _load_bool(kws, 'ENET0_RESET_ENABLE', False):
                reset_io_str = _load_val(kws, 'ENET0_RESET_IO', None)
                m = _mio_pin_regex.fullmatch(reset_io_str)
                if m is not None:
                    reset_io = int(m[1])
                if reset_io < 0:
                    raise ValueError(f"Invalid ENET0 reset IO: {reset_io_str}")
            self.enable_enet0(_load_cb(kws, 'ENET0_ENET0_IO',
                                       ENET0IO, ENET0IO.MIO_16_27), mdio, reset_io)

        self.ENET1_CLKSRC = _load_cb(kws, 'ENET1_PERIPHERAL_CLKSRC',
                                     ClockSource, ClockSource.IO)
        self.ENET1_DIVISOR0 = _load_int(kws, 'ENET1_PERIPHERAL_DIVISOR0')
        self.ENET1_DIVISOR1 = _load_int(kws, 'ENET1_PERIPHERAL_DIVISOR1')
        self.ENET1_ENABLE = False
        self.ENET1_MDIO_ENABLE = False

        if _load_bool(kws, 'ENET1_PERIPHERAL_ENABLE', False):
            mdio = _load_bool(kws, 'ENET1_GRP_MDIO_ENABLE', False)
            if mdio:
                mdio_io = _load_val(kws, 'ENET1_GRP_MDIO_IO', "MIO 52 .. 53")
                if mdio_io == "EMIO":
                    mdio = False
                elif mdio_io != "MIO 52 .. 53":
                    raise ValueError(f"Invalid MDIO IO: {mdio_io}")
            reset_io = -1
            if _load_bool(kws, 'ENET1_RESET_ENABLE', False):
                if (_load_val(kws, 'ENET_RESET_SELECT', None) == "Share reset pin" and
                    self.ENET0_ENABLE and self.ENET0_RESET_IO > 0):
                    reset_io = self.ENET0_RESET_IO
                else:
                    reset_io_str = _load_val(kws, 'ENET1_RESET_IO', None)
                    m = _mio_pin_regex.fullmatch(reset_io_str)
                    if m is not None:
                        reset_io = int(m[1])
                    if reset_io < 0:
                        raise ValueError(f"Invalid ENET1 reset IO: {reset_io_str}")
            self.enable_enet1(_load_cb(kws, 'ENET1_ENET1_IO',
                                       ENET1IO, ENET1IO.MIO_28_39), mdio, reset_io)

        self.USB0_ENABLE = False

        if _load_bool(kws, 'USB0_PERIPHERAL_ENABLE', False):
            reset_io = -1
            if _load_bool(kws, 'USB0_RESET_ENABLE', False):
                reset_io_str = _load_val(kws, 'USB0_RESET_IO', None)
                m = _mio_pin_regex.fullmatch(reset_io_str)
                if m is not None:
                    reset_io = int(m[1])
                if reset_io < 0:
                    raise ValueError(f"Invalid USB0 reset IO: {reset_io_str}")
            self.enable_usb0(reset_io)

        self.USB1_ENABLE = False

        if _load_bool(kws, 'USB1_PERIPHERAL_ENABLE', False):
            reset_io = -1
            if _load_bool(kws, 'USB1_RESET_ENABLE', False):
                if (_load_val(kws, 'USB_RESET_SELECT', None) == "Share reset pin" and
                    self.USB0_ENABLE and self.USB0_RESET_IO > 0):
                    reset_io = self.USB0_RESET_IO
                else:
                    reset_io_str = _load_val(kws, 'USB1_RESET_IO', None)
                    m = _mio_pin_regex.fullmatch(reset_io_str)
                    if m is not None:
                        reset_io = int(m[1])
                    if reset_io < 0:
                        raise ValueError(f"Invalid USB1 reset IO: {reset_io_str}")
            self.enable_usb1(reset_io)

        self.I2C0_ENABLE = False

        if _load_bool(kws, 'I2C0_PERIPHERAL_ENABLE', False):
            io = _load_cb(kws, 'I2C0_I2C0_IO', I2C0IO)
            reset_io = -1
            if _load_bool(kws, 'I2C0_RESET_ENABLE', False):
                reset_io_str = _load_val(kws, 'I2C0_RESET_IO', None)
                m = _mio_pin_regex.fullmatch(reset_io_str)
                if m is not None:
                    reset_io = int(m[1])
                if reset_io < 0:
                    raise ValueError(f"Invalid I2C0 reset IO: {reset_io_str}")
            # TODO: Not supported by the Vivado GUI so I don't know what to do yet
            if (_load_bool(kws, 'I2C0_GRP_INT_ENABLE', False) and
                _load_val(kws, 'I2C0_GRP_INT_IO', None) != "EMIO"):
                raise NotImplementedError
            self.enable_i2c0(io, reset_io)

        self.I2C1_ENABLE = False

        if _load_bool(kws, 'I2C1_PERIPHERAL_ENABLE', False):
            io = _load_cb(kws, 'I2C1_I2C1_IO', I2C1IO)
            reset_io = -1
            if _load_bool(kws, 'I2C1_RESET_ENABLE', False):
                if (_load_val(kws, 'I2C_RESET_SELECT', None) == "Share reset pin" and
                    self.I2C0_ENABLE and self.I2C0_RESET_IO > 0):
                    reset_io = self.I2C0_RESET_IO
                else:
                    reset_io_str = _load_val(kws, 'I2C1_RESET_IO', None)
                    m = _mio_pin_regex.fullmatch(reset_io_str)
                    if m is not None:
                        reset_io = int(m[1])
                    if reset_io < 0:
                        raise ValueError(f"Invalid I2C1 reset IO: {reset_io_str}")
            # TODO: Not supported by the Vivado GUI so I don't know what to do yet
            if (_load_bool(kws, 'I2C1_GRP_INT_ENABLE', False) and
                _load_val(kws, 'I2C1_GRP_INT_IO', None) != "EMIO"):
                raise NotImplementedError
            self.enable_i2c1(io, reset_io)

        for n in range(54):
            pin = self.MIO_PINS[n]
            direction = _load_cb_opt(kws, f'MIO_{n}_DIRECTION', IODirection)
            iotype = _load_cb_opt(kws, f'MIO_{n}_IOTYPE', IOType)
            pullup_str = _load_val_opt(kws, f'MIO_{n}_PULLUP')
            slew = _load_cb_opt(kws, f'MIO_{n}_SLEW', IOSlew)
            if pin.used:
                if direction is not None and direction != pin.DIRECTION:
                    raise ValueError(f"MIO pin {n} direction mismatch")
                if iotype is not None:
                    self._check_mio_iotype(n, iotype)
                    pin.IOTYPE = iotype
                if pullup_str is not None:
                    if pullup_str == "enabled":
                        pullup = True
                    elif pullup_str == "disabled":
                        pullup = False
                    else:
                        raise TypeError(f"Invalid value {pullup_str} for option: 'MIO_{n}_PULLUP'")
                    self._check_mio_pullup(n, pullup)
                    pin.PULLUP = pullup
                if slew is not None:
                    pin.SLEW = slew
            elif ((direction is not None) or (iotype is not None) or
                  (pullup_str is not None) or (slew is not None)):
                raise ValueError(f"Cannot specify properties on unused MIO pin {n}")

    def get_fbdiv(self, pll):
        return (self.ARM_FBDIV, self.DDR_FBDIV, self.IO_FBDIV)[pll.value]
    def get_freqmhz(self, pll):
        return self.CRYSTAL_FREQMHZ * self.get_fbdiv(pll)

    @property
    def CPU_PLL_FREQMHZ(self):
        return self.get_freqmhz(self.CPU_CLKSRC)
    @property
    def DDR_PLL_FREQMHZ(self):
        return self.CRYSTAL_FREQMHZ * self.DDR_FBDIV
    @property
    def IO_PLL_FREQMHZ(self):
        return self.CRYSTAL_FREQMHZ * self.IO_FBDIV

    @property
    def CPU_FREQMHZ(self):
        return self.CPU_PLL_FREQMHZ / self.CPU_DIVISOR0
    @property
    def DDR_FREQMHZ(self):
        freq = self.DDR_PLL_FREQMHZ / self.DDR_DIVISOR0
        return ceil(freq * 1000000) / 1000000
    @property
    def DCI_FREQMHZ(self):
        return self.DDR_PLL_FREQMHZ / (self.DCI_DIVISOR0 * self.DCI_DIVISOR1)

    @property
    def DDR_RL(self):
        return self.DDR_AL + self.DDR_CL
    @property
    def DDR_T_WR(self):
        return ceil(0.015 * self.DDR_FREQMHZ)
    @property
    def DDR_T_WTR(self):
        return max(ceil(0.0075 * self.DDR_FREQMHZ), 4)

    def _get_used_mio(self, n):
        pin = self.MIO_PINS[n]
        if not pin.used:
            raise ValueError("Cannot set properties on unused MIO pin {n}")
        return pin

    def _release_mio_pin(self, n):
        self.MIO_PINS[n].reset()

    def _get_mio_iotype(self, n):
        return self.BANK_VOLTAGE[n >= 16]

    def _check_mio_pullup(self, n, pullup):
        if n >= 2 and n <= 8 and pullup:
            raise ValueError("Cannot enable pullup on MIO pin [2, 8]")

    def set_mio_pullup(self, n, pullup=True):
        pin = self._get_used_mio(n)
        self._check_mio_pullup(n, pullup)
        pin.PULLUP = pullup

    def set_mio_slew(self, n, slew):
        self._get_used_mio(n).SLEW = slew

    def _check_mio_iotype(self, n, iotype):
        bank_type = self._get_mio_iotype(n)
        if iotype != bank_type and (not iotype.is18() or not bank_type.is18()):
            raise ValueError("Incompatible io type")

    def set_mio_iotype(self, n, iotype):
        self._check_mio_iotype(n, iotype)
        self._get_used_mio(n).IOTYPE = iotype

    def _enable_single_mio_gpio(self, n, pin):
        iotype = self._get_mio_iotype(n)
        direction = IODirection.Out if n in (7, 8) else IODirection.InOut
        # Selector is 0 for all MIO pins for GPIO
        pin.set_use(iotype, direction, True, 0)

    def enable_mio_gpio(self):
        self.GPIO_MIO_ENABLE = True
        for n in range(54):
            pin = self.MIO_PINS[n]
            if pin.used:
                continue
            self._enable_single_mio_gpio(n, pin)
        self.update_gpio_resets()

    def disable_mio_gpio(self):
        if not self.GPIO_MIO_ENABLE:
            return
        self.GPIO_MIO_ENABLE = False
        self.update_gpio_resets() # Raise error if there's still reset enabled
        for n in range(54):
            pin = self.MIO_PINS[n]
            if pin.IS_GPIO:
                pin.reset()

    @property
    def GPIO_RESETS(self):
        ios = set()
        res = []
        for io in (self.USB0_RESET_IO, self.USB1_RESET_IO,
                   self.ENET0_RESET_IO, self.ENET1_RESET_IO,
                   self.I2C0_RESET_IO, self.I2C1_RESET_IO):
            if io < 0 or io in ios:
                continue
            ios.add(io)
            res.append(io)
        return res

    def update_gpio_resets(self, removed=-1):
        ios = set()
        for io in self.GPIO_RESETS:
            if io == removed:
                removed = -1
            if not self.GPIO_MIO_ENABLE:
                raise ValueError("Reset function requires GPIO to be enabled")
            pin = self.MIO_PINS[io]
            if not pin.IS_GPIO:
                raise ValueError("Reset PIN is not a GPIO pin")
            pin.DIRECTION = IODirection.Out
        if removed >= 0:
            pin = self.MIO_PINS[removed]
            if pin.IS_GPIO and pin.DIRECTION == IODirection.Out and pin not in (7, 8):
                pin.DIRECTION == IODirection.InOut

    def _use_mio(self, n, direction, select):
        pin = self.MIO_PINS[n]
        if pin.used and (not pin.IS_GPIO or n in self.GPIO_RESETS):
            raise ValueError(f"Conflict use of MIO pin {n}")
        iotype = self._get_mio_iotype(n)
        pin.set_use(iotype, direction, False, select)
        if n < 2 or n > 8:
            # Turn pull up on by default to match vivado behavior
            pin.PULLUP = True

    def _release_mio(self, n):
        pin = self.MIO_PINS[n]
        pin.reset()
        if self.GPIO_MIO_ENABLE:
            self._enable_single_mio_gpio(n, pin)

    @property
    def MEMORY_INTERFACE_ENABLED(self):
        return self.QSPI_ENABLE or self.NOR_ENABLE or self.NAND_ENABLE
    @property
    def QSPI_ENABLE(self):
        return self.QSPI_MODE != QSPIMode.Disabled

    @property
    def QSPI_FREQMHZ(self):
        return self.get_freqmhz(self.QSPI_CLKSRC) / self.QSPI_DIVISOR0

    def enable_qspi(self, qspi_mode, fbclk=False):
        if self.MEMORY_INTERFACE_ENABLED and not self.QSPI_ENABLE:
            raise ValueError("Only one memory interface can be enabled")
        self.disable_qspi()
        if qspi_mode == QSPIMode.Single_x1:
            self._use_mio(1, IODirection.Out, 0b000_00_0_1)
            self._use_mio(2, IODirection.Out, 0b000_00_0_1)
            self._use_mio(3, IODirection.In, 0b000_00_0_1)
            self._use_mio(5, IODirection.InOut, 0b000_00_0_1)
            self._use_mio(6, IODirection.Out, 0b000_00_0_1)
        elif qspi_mode == QSPIMode.Single_x2:
            self._use_mio(1, IODirection.Out, 0b000_00_0_1)
            self._use_mio(2, IODirection.InOut, 0b000_00_0_1)
            self._use_mio(3, IODirection.InOut, 0b000_00_0_1)
            self._use_mio(5, IODirection.InOut, 0b000_00_0_1)
            self._use_mio(6, IODirection.Out, 0b000_00_0_1)
        elif qspi_mode == QSPIMode.Single_x4:
            self._use_mio(1, IODirection.Out, 0b000_00_0_1)
            self._use_mio(2, IODirection.InOut, 0b000_00_0_1)
            self._use_mio(3, IODirection.InOut, 0b000_00_0_1)
            self._use_mio(4, IODirection.InOut, 0b000_00_0_1)
            self._use_mio(5, IODirection.InOut, 0b000_00_0_1)
            self._use_mio(6, IODirection.Out, 0b000_00_0_1)
        elif qspi_mode == QSPIMode.Dual_x1:
            self._use_mio(0, IODirection.Out, 0b000_00_0_1)
            self._use_mio(1, IODirection.Out, 0b000_00_0_1)
            self._use_mio(2, IODirection.Out, 0b000_00_0_1)
            self._use_mio(3, IODirection.In, 0b000_00_0_1)
            self._use_mio(5, IODirection.InOut, 0b000_00_0_1)
            self._use_mio(6, IODirection.Out, 0b000_00_0_1)
        elif qspi_mode == QSPIMode.Dual_x2:
            self._use_mio(0, IODirection.Out, 0b000_00_0_1)
            self._use_mio(1, IODirection.Out, 0b000_00_0_1)
            self._use_mio(2, IODirection.InOut, 0b000_00_0_1)
            self._use_mio(3, IODirection.InOut, 0b000_00_0_1)
            self._use_mio(5, IODirection.InOut, 0b000_00_0_1)
            self._use_mio(6, IODirection.Out, 0b000_00_0_1)
        elif qspi_mode == QSPIMode.Dual_x4:
            self._use_mio(0, IODirection.Out, 0b000_00_0_1)
            self._use_mio(1, IODirection.Out, 0b000_00_0_1)
            self._use_mio(2, IODirection.InOut, 0b000_00_0_1)
            self._use_mio(3, IODirection.InOut, 0b000_00_0_1)
            self._use_mio(4, IODirection.InOut, 0b000_00_0_1)
            self._use_mio(5, IODirection.InOut, 0b000_00_0_1)
            self._use_mio(6, IODirection.Out, 0b000_00_0_1)
        elif qspi_mode == QSPIMode.Parallel_x8:
            self._use_mio(0, IODirection.Out, 0b000_00_0_1)
            self._use_mio(1, IODirection.Out, 0b000_00_0_1)
            self._use_mio(2, IODirection.InOut, 0b000_00_0_1)
            self._use_mio(3, IODirection.InOut, 0b000_00_0_1)
            self._use_mio(4, IODirection.InOut, 0b000_00_0_1)
            self._use_mio(5, IODirection.InOut, 0b000_00_0_1)
            self._use_mio(6, IODirection.Out, 0b000_00_0_1)

            self._use_mio(9, IODirection.Out, 0b000_00_0_1)
            self._use_mio(10, IODirection.InOut, 0b000_00_0_1)
            self._use_mio(11, IODirection.InOut, 0b000_00_0_1)
            self._use_mio(12, IODirection.InOut, 0b000_00_0_1)
            self._use_mio(13, IODirection.InOut, 0b000_00_0_1)
        else:
            raise ValueError(f"Invalid QSPI mode {qspi_mode}")
        if fbclk:
            self._use_mio(8, IODirection.Out, 0b000_00_0_1)
        self.QSPI_FBCLK_ENABLE = fbclk
        self.QSPI_MODE = qspi_mode

    def disable_qspi(self):
        if not self.QSPI_ENABLE:
            return
        if self.QSPI_FBCLK_ENABLE:
            self.QSPI_FBCLK_ENABLE = False
            self._release_mio(8)
        if qspi_mode in (QSPIMode.Single_x1, QSPIMode.Single_x2):
            for n in (1, 2, 3, 5, 6):
                self._release_mio(n)
        elif qspi_mode == QSPIMode.Single_x4:
            for n in range(1, 7):
                self._release_mio(n)
        elif qspi_mode in (QSPIMode.Dual_x1, QSPIMode.Dual_x2):
            for n in (0, 1, 2, 3, 5, 6):
                self._release_mio(n)
        elif qspi_mode == QSPIMode.Dual_x4:
            for n in range(7):
                self._release_mio(n)
        elif qspi_mode == QSPIMode.Parallel_x8:
            for n in range(7):
                self._release_mio(n)
            for n in range(9, 14):
                self._release_mio(n)
        self.QSPI_ENABLE = QSPIMode.Disabled

    @property
    def SMC_FREQMHZ(self):
        return self.get_freqmhz(self.SMC_CLKSRC) / self.SMC_DIVISOR0

    @property
    def SDIO_FREQMHZ(self):
        return self.get_freqmhz(self.SDIO_CLKSRC) / self.SDIO_DIVISOR0

    @property
    def NOR_A25_ENABLE(self):
        return self.NOR_MIO0_ROLE == NORMIO0Role.ADDR25
    @property
    def NOR_CS1_ENABLE(self):
        return self.NOR_MIO0_ROLE == NORMIO0Role.CS1

    def enable_nor(self, mio0_role=NORMIO0Role.Disabled, cs0=False,
                   cs0_cycles=SMCCycles(), cs1_cycles=SMCCycles()):
        if self.MEMORY_INTERFACE_ENABLED and not self.NOR_ENABLE:
            raise ValueError("Only one memory interface can be enabled")
        self.disable_nor()
        if mio0_role == NORMIO0Role.ADDR25:
            self._use_mio(1, IODirection.Out, 0b000_01_0_0)
        elif mio0_role == NORMIO0Role.CS1:
            self._use_mio(1, IODirection.Out, 0b000_10_0_0)
        self.NOR_MIO0_ROLE = mio0_role
        if cs0:
            self._use_mio(0, IODirection.Out, 0b000_10_0_0)
        self.NOR_CS0_ENABLE = cs0
        for n in range(3, 7):
            self._use_mio(n, IODirection.InOut, 0b000_01_0_0)
        self._use_mio(7, IODirection.Out, 0b000_01_0_0)
        self._use_mio(8, IODirection.Out, 0b010_00_0_0)
        for n in range(9, 12):
            self._use_mio(n, IODirection.InOut, 0b000_01_0_0)
        self._use_mio(13, IODirection.InOut, 0b000_01_0_0)
        for n in range(15, 40):
            self._use_mio(n, IODirection.Out, 0b000_01_0_0)
        self.NOR_CS0_CYCLES = cs0_cycles
        self.NOR_CS1_CYCLES = cs1_cycles
        self.NOR_ENABLE = True

    def disable_nor(self):
        if not self.NOR_ENABLE:
            return
        self.NOR_ENABLE = False
        if self.NOR_CS0_ENABLE:
            self._release_mio(0)
            self.NOR_CS0_ENABLE = False
        if self.NOR_MIO0_ROLE != NORMIO0Role.Disabled:
            self._release_mio(1)
            self.NOR_MIO0_ROLE = NORMIO0Role.Disabled
        for n in range(3, 40):
            if n == 12 or n == 14:
                continue
            self._release_mio(n)

    def enable_nand(self, cycles, d8=False):
        if self.MEMORY_INTERFACE_ENABLED and not self.NAND_ENABLE:
            raise ValueError("Only one memory interface can be enabled")
        self.disable_nand()
        self._use_mio(0, IODirection.Out, 0b000_10_0_0)
        for n in range(2, 4):
            self._use_mio(n, IODirection.Out, 0b000_10_0_0)
        for n in range(4, 7):
            self._use_mio(n, IODirection.InOut, 0b000_10_0_0)
        for n in range(7, 9):
            self._use_mio(n, IODirection.Out, 0b000_10_0_0)
        for n in range(9, 14):
            self._use_mio(n, IODirection.InOut, 0b000_10_0_0)
        self._use_mio(14, IODirection.In, 0b000_10_0_0)
        self.NAND_CYCLES = cycles
        if d8:
            for n in range(16, 24):
                self._use_mio(n, IODirection.InOut, 0b000_10_0_0)
            self.NAND_D8_ENABLE = True
        self.NAND_ENABLE = True

    def disable_nand(self):
        if not self.NAND_ENABLE:
            return
        self.NAND_ENABLE = False
        for n in range(15):
            if n == 1:
                continue
            self._release_mio(n)
        if self.NAND_D8_ENABLE:
            for n in range(16, 24):
                self._release_mio(n)

    @property
    def ENET0_RESET_ENABLE(self):
        return self.ENET0_RESET_IO >= 0

    def enable_enet0(self, io, mdio, reset_io):
        self.disable_enet0()
        if io == ENET0IO.MIO_16_27:
            for n in range(16, 22):
                self._use_mio(n, IODirection.Out, 0b000_00_0_1)
            for n in range(22, 28):
                self._use_mio(n, IODirection.In, 0b000_00_0_1)
        elif self.ENET0_CLKSRC != ClockSource.Extern:
            raise ValueError("ENET0 clock must be External when using EMIO")
        self.ENET0_IO = io
        self.ENET0_ENABLE = True
        if mdio:
            self._use_mio(52, IODirection.Out, 0b100_00_0_0)
            self._use_mio(53, IODirection.InOut, 0b100_00_0_0)
        self.ENET0_RESET_IO = reset_io
        if reset_io >= 0:
            self.update_gpio_resets()
        self.ENET0_MDIO_ENABLE = mdio

    def disable_enet0(self):
        if not self.ENET0_ENABLE:
            return
        if self.ENET0_IO == ENET0IO.MIO_16_27:
            for n in range(16, 28):
                self._release_mio(n)
        if self.ENET0_MDIO_ENABLE:
            self._release_mio(52)
            self._release_mio(53)
            self.ENET0_MDIO_ENABLE = False
        if self.ENET0_RESET_IO >= 0:
            old_reset_io = self.ENET0_RESET_IO
            self.ENET0_RESET_IO = -1
            self.update_gpio_resets(old_reset_io)
        self.ENET0_ENABLE = False

    @property
    def ENET1_RESET_ENABLE(self):
        return self.ENET1_RESET_IO >= 0

    def enable_enet1(self, io, mdio, reset_io):
        self.disable_enet1()
        if io == ENET1IO.MIO_28_39:
            for n in range(28, 34):
                self._use_mio(n, IODirection.Out, 0b000_00_0_1)
            for n in range(34, 40):
                self._use_mio(n, IODirection.In, 0b000_00_0_1)
        elif self.ENET1_CLKSRC != ClockSource.Extern:
            raise ValueError("ENET1 clock must be External when using EMIO")
        self.ENET1_IO = io
        self.ENET1_ENABLE = True
        if mdio:
            self._use_mio(52, IODirection.Out, 0b100_00_0_0)
            self._use_mio(53, IODirection.InOut, 0b100_00_0_0)
        self.ENET1_RESET_IO = reset_io
        if reset_io >= 0:
            self.update_gpio_resets()
        self.ENET1_MDIO_ENABLE = mdio

    def disable_enet1(self):
        if not self.ENET1_ENABLE:
            return
        if self.ENET1_IO == ENET1IO.MIO_28_39:
            for n in range(28, 40):
                self._release_mio(n)
        if self.ENET1_MDIO_ENABLE:
            self._release_mio(52)
            self._release_mio(53)
            self.ENET1_MDIO_ENABLE = False
        if self.ENET1_RESET_IO >= 0:
            old_reset_io = self.ENET1_RESET_IO
            self.ENET1_RESET_IO = -1
            self.update_gpio_resets(old_reset_io)
        self.ENET1_ENABLE = False

    @property
    def USB0_RESET_ENABLE(self):
        return self.USB0_RESET_IO >= 0

    def enable_usb0(self, reset_io):
        self.disable_usb0()
        self._use_mio(28, IODirection.InOut, 0b000_00_1_0)
        self._use_mio(29, IODirection.In, 0b000_00_1_0)
        self._use_mio(30, IODirection.Out, 0b000_00_1_0)
        self._use_mio(31, IODirection.In, 0b000_00_1_0)
        for n in range(32, 36):
            self._use_mio(n, IODirection.InOut, 0b000_00_1_0)
        self._use_mio(36, IODirection.In, 0b000_00_1_0)
        for n in range(37, 40):
            self._use_mio(n, IODirection.InOut, 0b000_00_1_0)
        self.USB0_ENABLE = True
        self.USB0_RESET_IO = reset_io
        if reset_io >= 0:
            self.update_gpio_resets()

    def disable_usb0(self):
        if not self.USB0_ENABLE:
            return
        for n in range(28, 40):
            self._release_mio(n)
        if self.USB0_RESET_IO >= 0:
            old_reset_io = self.USB0_RESET_IO
            self.USB0_RESET_IO = -1
            self.update_gpio_resets(old_reset_io)
        self.USB0_ENABLE = False

    @property
    def USB1_RESET_ENABLE(self):
        return self.USB1_RESET_IO >= 0

    def enable_usb1(self, reset_io):
        self.disable_usb1()
        self._use_mio(40, IODirection.InOut, 0b000_00_1_0)
        self._use_mio(41, IODirection.In, 0b000_00_1_0)
        self._use_mio(42, IODirection.Out, 0b000_00_1_0)
        self._use_mio(43, IODirection.In, 0b000_00_1_0)
        for n in range(44, 48):
            self._use_mio(n, IODirection.InOut, 0b000_00_1_0)
        self._use_mio(48, IODirection.In, 0b000_00_1_0)
        for n in range(49, 52):
            self._use_mio(n, IODirection.InOut, 0b000_00_1_0)
        self.USB1_ENABLE = True
        self.USB1_RESET_IO = reset_io
        if reset_io >= 0:
            self.update_gpio_resets()

    def disable_usb1(self):
        if not self.USB1_ENABLE:
            return
        for n in range(40, 52):
            self._release_mio(n)
        if self.USB1_RESET_IO >= 0:
            old_reset_io = self.USB1_RESET_IO
            self.USB1_RESET_IO = -1
            self.update_gpio_resets(old_reset_io)
        self.USB1_ENABLE = False

    @property
    def I2C0_RESET_ENABLE(self):
        return self.I2C0_RESET_IO >= 0

    def enable_i2c0(self, io, reset_io):
        self.disable_i2c0()
        if io.value > 0:
            self._use_mio(io.value, IODirection.InOut, 0b010_00_0_0)
            self._use_mio(io.value + 1, IODirection.InOut, 0b010_00_0_0)
        self.I2C0_IO = io
        self.I2C0_ENABLE = True
        self.I2C0_RESET_IO = reset_io
        if reset_io >= 0:
            self.update_gpio_resets()

    def disable_i2c0(self):
        if not self.I2C0_ENABLE:
            return
        io = self.I2C0_IO
        if io.value > 0:
            self._release_mio(io.value)
            self._release_mio(io.value + 1)
        if self.I2C0_RESET_IO >= 0:
            old_reset_io = self.I2C0_RESET_IO
            self.I2C0_RESET_IO = -1
            self.update_gpio_resets(old_reset_io)
        self.I2C0_ENABLE = False

    @property
    def I2C1_RESET_ENABLE(self):
        return self.I2C1_RESET_IO >= 0

    def enable_i2c1(self, io, reset_io):
        self.disable_i2c1()
        if io.value > 0:
            self._use_mio(io.value, IODirection.InOut, 0b010_00_0_0)
            self._use_mio(io.value + 1, IODirection.InOut, 0b010_00_0_0)
        self.I2C1_IO = io
        self.I2C1_ENABLE = True
        self.I2C1_RESET_IO = reset_io
        if reset_io >= 0:
            self.update_gpio_resets()

    def disable_i2c1(self):
        if not self.I2C1_ENABLE:
            return
        io = self.I2C1_IO
        if io.value > 0:
            self._release_mio(io.value)
            self._release_mio(io.value + 1)
        if self.I2C1_RESET_IO >= 0:
            old_reset_io = self.I2C1_RESET_IO
            self.I2C1_RESET_IO = -1
            self.update_gpio_resets(old_reset_io)
        self.I2C1_ENABLE = False

    @property
    def SD0_POW_ENABLE(self):
        return self.SD0_POW_IO >= 0

    def enable_sd0(self, io, cd_io, wp_io, pow_io):
        self.disable_sd0()
        if io.value > 0:
            for n in range(6):
                self._use_mio(io.value + n, IODirection.InOut, 0b100_00_0_0)
        self.SD0_IO = io
        if cd_io < 54:
            self._use_mio(cd_io, IODirection.In, 0)
        self.SD0_CD_IO = cd_io
        if wp_io < 54:
            self._use_mio(wp_io, IODirection.In, 0)
        self.SD0_WP_IO = wp_io
        if pow_io > 0:
            self._use_mio(pow_io, IODirection.Out, 0b000_11_0_0)
        self.SD0_POW_IO = pow_io
        self.SD0_ENABLE = True

    def disable_sd0(self):
        if not self.SD0_ENABLE:
            return
        io = self.SD0_IO
        if io.value > 0:
            for n in range(6):
                self._release_mio(io.value + n)
        if self.SD0_CD_IO < 54:
            self._release_mio(self.SD0_CD_IO)
        self.SD0_CD_IO = 56
        if self.SD0_WP_IO < 54:
            self._release_mio(self.SD0_WP_IO)
        self.SD0_WP_IO = 55
        if self.SD0_POW_IO >= 0:
            self._release_mio(self.SD0_POW_IO)
        self.SD0_POW_IO = -1
        self.SD0_ENABLE = False

    @property
    def SD1_POW_ENABLE(self):
        return self.SD1_POW_IO >= 0

    def enable_sd1(self, io, cd_io, wp_io, pow_io):
        self.disable_sd1()
        if io.value > 0:
            for n in range(6):
                self._use_mio(io.value + n, IODirection.InOut, 0b100_00_0_0)
        self.SD1_IO = io
        if cd_io < 54:
            self._use_mio(cd_io, IODirection.In, 0)
        self.SD1_CD_IO = cd_io
        if wp_io < 54:
            self._use_mio(wp_io, IODirection.In, 0)
        self.SD1_WP_IO = wp_io
        if pow_io > 0:
            self._use_mio(pow_io, IODirection.Out, 0b000_11_0_0)
        self.SD1_POW_IO = pow_io
        self.SD1_ENABLE = True

    def disable_sd1(self):
        if not self.SD1_ENABLE:
            return
        io = self.SD1_IO
        if io.value > 0:
            for n in range(6):
                self._release_mio(io.value + n)
        if self.SD1_CD_IO < 54:
            self._release_mio(self.SD1_CD_IO)
        self.SD1_CD_IO = 58
        if self.SD1_WP_IO < 54:
            self._release_mio(self.SD1_WP_IO)
        self.SD1_WP_IO = 57
        if self.SD1_POW_IO >= 0:
            self._release_mio(self.SD1_POW_IO)
        self.SD1_POW_IO = -1
        self.SD1_ENABLE = False

    @property
    def UART_FREQMHZ(self):
        return self.get_freqmhz(self.UART_CLKSRC) / self.UART_DIVISOR0

    def enable_uart0(self, io, baud):
        self.disable_uart0()
        if io.value > 0:
            self._use_mio(io.value, IODirection.In, 0b111_00_0_0)
            self._use_mio(io.value + 1, IODirection.Out, 0b111_00_0_0)
        self.UART0_IO = io
        self.UART0_BAUD_RATE = baud
        self.UART0_ENABLE = True

    def disable_uart0(self):
        if not self.UART0_ENABLE:
            return
        io = self.UART0_IO
        if io.value > 0:
            self._release_mio(io.value)
            self._release_mio(io.value + 1)
        self.UART0_ENABLE = False

    def enable_uart1(self, io, baud):
        self.disable_uart1()
        if io.value > 0:
            self._use_mio(io.value, IODirection.Out, 0b111_00_0_0)
            self._use_mio(io.value + 1, IODirection.In, 0b111_00_0_0)
        self.UART1_IO = io
        self.UART1_BAUD_RATE = baud
        self.UART1_ENABLE = True

    def disable_uart1(self):
        if not self.UART1_ENABLE:
            return
        io = self.UART1_IO
        if io.value > 0:
            self._release_mio(io.value)
            self._release_mio(io.value + 1)
        self.UART1_ENABLE = False

    @property
    def SPI_FREQMHZ(self):
        return self.get_freqmhz(self.SPI_CLKSRC) / self.SPI_DIVISOR0

    def enable_spi0(self, io, ss1, ss2):
        self.disable_spi0()
        if io.value > 0:
            for n in range(3):
                self._use_mio(io.value + n, IODirection.InOut, 0b101_00_0_0)
            if ss1:
                self._use_mio(io.value + 3, IODirection.Out, 0b101_00_0_0)
            if ss2:
                self._use_mio(io.value + 4, IODirection.Out, 0b101_00_0_0)
            self._use_mio(io.value + 5, IODirection.InOut, 0b101_00_0_0)
        self.SPI0_SS1_ENABLE = ss1
        self.SPI0_SS2_ENABLE = ss2
        self.SPI0_IO = io
        self.SPI0_ENABLE = True

    def disable_spi0(self):
        if not self.SPI0_ENABLE:
            return
        io = self.SPI0_IO
        if io.value > 0:
            for n in range(3):
                self._release_mio(io.value + n)
            if self.SPI0_SS1_ENABLE:
                self._release_mio(io.value + 3)
            if self.SPI0_SS2_ENABLE:
                self._release_mio(io.value + 4)
            self._release_mio(io.value + 5)
        self.SPI0_ENABLE = False

    def enable_spi1(self, io, ss1, ss2):
        self.disable_spi1()
        if io.value > 0:
            for n in range(3):
                self._use_mio(io.value + n, IODirection.InOut, 0b101_00_0_0)
            if ss1:
                self._use_mio(io.value + 3, IODirection.Out, 0b101_00_0_0)
            if ss2:
                self._use_mio(io.value + 4, IODirection.Out, 0b101_00_0_0)
            self._use_mio(io.value + 5, IODirection.InOut, 0b101_00_0_0)
        self.SPI1_SS1_ENABLE = ss1
        self.SPI1_SS2_ENABLE = ss2
        self.SPI1_IO = io
        self.SPI1_ENABLE = True

    def disable_spi1(self):
        if not self.SPI1_ENABLE:
            return
        io = self.SPI1_IO
        if io.value > 0:
            for n in range(3):
                self._release_mio(io.value + n)
            if self.SPI1_SS1_ENABLE:
                self._release_mio(io.value + 3)
            if self.SPI1_SS2_ENABLE:
                self._release_mio(io.value + 4)
            self._release_mio(io.value + 5)
        self.SPI1_ENABLE = False

    @property
    def CAN_FREQMHZ(self):
        return self.get_freqmhz(self.CAN_CLKSRC) / (self.CAN_DIVISOR0 * self.CAN_DIVISOR1)

    @property
    def CAN0_CLK_ENABLE(self):
        return self.CAN0_CLK_IO >= 0

    def enable_can0(self, io, clk_io):
        self.disable_can0()
        if io.value > 0:
            self._use_mio(io.value, IODirection.In, 0b001_00_0_0)
            self._use_mio(io.value + 1, IODirection.Out, 0b001_00_0_0)
        if clk_io >= 0:
            self._use_mio(clk_io, IODirection.InOut, 0)
        self.CAN0_CLK_IO = clk_io
        self.CAN0_IO = io
        self.CAN0_ENABLE = True

    def disable_can0(self):
        if not self.CAN0_ENABLE:
            return
        io = self.CAN0_IO
        if io.value > 0:
            self._release_mio(io.value)
            self._release_mio(io.value + 1)
        if self.CAN0_CLK_IO >= 0:
            self._release_mio(self.CAN0_CLK_IO)
        self.CAN0_CLK_IO = -1
        self.CAN0_ENABLE = False

    @property
    def CAN1_CLK_ENABLE(self):
        return self.CAN1_CLK_IO >= 0

    def enable_can1(self, io, clk_io):
        self.disable_can1()
        if io.value > 0:
            self._use_mio(io.value, IODirection.Out, 0b001_00_0_0)
            self._use_mio(io.value + 1, IODirection.In, 0b001_00_0_0)
        if clk_io >= 0:
            self._use_mio(clk_io, IODirection.InOut, 0)
        self.CAN1_CLK_IO = clk_io
        self.CAN1_IO = io
        self.CAN1_ENABLE = True

    def disable_can1(self):
        if not self.CAN1_ENABLE:
            return
        io = self.CAN1_IO
        if io.value > 0:
            self._release_mio(io.value)
            self._release_mio(io.value + 1)
        if self.CAN1_CLK_IO >= 0:
            self._release_mio(self.CAN1_CLK_IO)
        self.CAN1_CLK_IO = -1
        self.CAN1_ENABLE = False

    @property
    def TTC0_ENABLE(self):
        return self.TTC0_IO != TTC0IO.EMIO

    def enable_ttc0(self, io):
        self.disable_ttc0()
        if io == TTC0IO.EMIO:
            return
        self._use_mio(io.value, IODirection.Out, 0b110_00_0_0)
        self._use_mio(io.value + 1, IODirection.In, 0b110_00_0_0)
        self.TTC0_IO = io

    def disable_ttc0(self):
        if not self.TTC0_ENABLE:
            return
        io = self.TTC0_IO
        self._release_mio(io.value)
        self._release_mio(io.value + 1)
        self.TTC0_IO = TTC0IO.EMIO

    @property
    def TTC1_ENABLE(self):
        return self.TTC1_IO != TTC1IO.EMIO

    def enable_ttc1(self, io):
        self.disable_ttc1()
        if io == TTC1IO.EMIO:
            return
        self._use_mio(io.value, IODirection.Out, 0b110_00_0_0)
        self._use_mio(io.value + 1, IODirection.In, 0b110_00_0_0)
        self.TTC1_IO = io

    def disable_ttc1(self):
        if not self.TTC1_ENABLE:
            return
        io = self.TTC1_IO
        self._release_mio(io.value)
        self._release_mio(io.value + 1)
        self.TTC1_IO = TTC1IO.EMIO

    def enable_wdt(self, io, clk_extern):
        self.disable_wdt()
        if io.value > 0:
            self._use_mio(io.value, IODirection.In, 0b011_00_0_0)
            self._use_mio(io.value + 1, IODirection.Out, 0b011_00_0_0)
        self.WDT_CLK_EXTERNAL = clk_extern
        self.WDT_IO = io
        self.WDT_ENABLE = True

    def disable_wdt(self):
        if not self.WDT_ENABLE:
            return
        io = self.WDT_IO
        if io.value > 0:
            self._release_mio(io.value)
            self._release_mio(io.value + 1)
        self.WDT_ENABLE = False
