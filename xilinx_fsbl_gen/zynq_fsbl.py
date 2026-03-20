#!/usr/bin/env python

from dataclasses import dataclass, field
from math import floor, ceil
from enum import Enum

def pll_index(pll):
    if pll == "ARM PLL":
        return 0
    elif pll == "DDR PLL":
        return 1
    elif pll == "IO PLL":
        return 2
    else:
        raise ValueError(f"Invalid PLL name: {pll}")

def clamp_val(val, maxval):
    if val < 0:
        return 0
    elif val > maxval:
        return maxval
    return val

def clamp_floor(val, maxval):
    return clamp_val(floor(val), maxval)

def clamp_round(val, maxval):
    return clamp_val(round(val), maxval)

def clamp_ceil(val, maxval):
    return clamp_val(ceil(val), maxval)

class BankIOType(Enum):
    LVCMOS18 = 1
    LVCMOS25 = 2
    LVCMOS33 = 3
    HSTL = 4

_BANK_TYPE_18 = (BankIOType.LVCMOS18, BankIOType.HSTL)

class IOSlew(Enum):
    Slow = 0
    Fast = 1

class IODirection(Enum):
    In = 0
    Out = 1
    InOut = 2

class MIOPin:
    def __init__(self, mio_id):
        self.id = mio_id
        self.reset()

    @property
    def used(self):
        return self.iotype is not None

    def reset(self):
        self.iotype = None
        self.direction = None
        self.slew = IOSlew.Slow
        self.pullup = False
        self.is_gpio = False
        self.select = 0

    def set_use(self, iotype, direction, is_gpio, select):
        self.iotype = iotype
        self.direction = direction
        self.is_gpio = is_gpio
        self.select = select

    def get_reg(self):
        tri_enable = self.direction == IODirection.In
        select = self.select
        speed = self.slew.value
        io_type = self.iotype.value
        pullup = self.pullup
        disable_rcvr = self.iotype == BankIOType.HSTL and self.direction == IODirection.Out

        return (try_enable |
                (select << 1) |
                (speed << 8) |
                (io_type << 9) |
                (pullup << 12) |
                (disable_rcvr << 13))

@dataclass(kw_only=True)
class Config:
    CRYSTAL_PERIPHERAL_FREQMHZ: float
    APU_CLK_RATIO_ENABLE: str = "6:2:1" # "6:2:1" or "4:2:1"

    def get_fbdiv(self, pll):
        return (self.ARMPLL_CTRL_FBDIV,
                self.DDRPLL_CTRL_FBDIV,
                self.IOPLL_CTRL_FBDIV)[pll_index(pll)]
    def get_freqmhz(self, pll):
        return self.CRYSTAL_PERIPHERAL_FREQMHZ * self.get_fbdiv(pll)

    CPU_PERIPHERAL_CLKSRC: str = "ARM PLL"

    ARMPLL_CTRL_FBDIV: int
    @property
    def CPU_CPU_PLL_FREQMHZ(self):
        return self.get_freqmhz(self.CPU_PERIPHERAL_CLKSRC)

    CPU_PERIPHERAL_DIVISOR0: int = 2
    @property
    def APU_PERIPHERAL_FREQMHZ(self):
        return self.CPU_CPU_PLL_FREQMHZ / self.CPU_PERIPHERAL_DIVISOR0

    DDRPLL_CTRL_FBDIV: int
    @property
    def DDR_DDR_PLL_FREQMHZ(self):
        return self.CRYSTAL_PERIPHERAL_FREQMHZ * self.DDRPLL_CTRL_FBDIV

    DDR_PRIORITY_READPORT_0: str = "Low"
    DDR_PRIORITY_READPORT_1: str = "Low"
    DDR_PRIORITY_READPORT_2: str = "Low"
    DDR_PRIORITY_READPORT_3: str = "Low"
    def get_arb_pri_rd_portn(self, n):
        priority = (self.DDR_PRIORITY_READPORT_0, self.DDR_PRIORITY_READPORT_1,
                    self.DDR_PRIORITY_READPORT_2, self.DDR_PRIORITY_READPORT_3)[n]
        if priority == "Low":
            return 0x3ff
        elif priority == "Medium":
            return 0x200
        elif priority == "High":
            return 0x4
        else:
            raise ValueError(f"Invalid read port priority: {priority}")

    DDR_PRIORITY_WRITEPORT_0: str = "Low"
    DDR_PRIORITY_WRITEPORT_1: str = "Low"
    DDR_PRIORITY_WRITEPORT_2: str = "Low"
    DDR_PRIORITY_WRITEPORT_3: str = "Low"
    def get_arb_pri_wr_portn(self, n):
        priority = (self.DDR_PRIORITY_WRITEPORT_0, self.DDR_PRIORITY_WRITEPORT_1,
                    self.DDR_PRIORITY_WRITEPORT_2, self.DDR_PRIORITY_WRITEPORT_3)[n]
        if priority == "Low":
            return 0x3ff
        elif priority == "Medium":
            return 0x200
        elif priority == "High":
            return 0x4
        else:
            raise ValueError(f"Invalid write port priority: {priority}")

    DDR_PORT0_HPR_ENABLE: bool = False
    DDR_PORT1_HPR_ENABLE: bool = False
    DDR_PORT2_HPR_ENABLE: bool = False
    DDR_PORT3_HPR_ENABLE: bool = False
    def get_ddrc_force_low_pri_n(self):
        return self.DDR_PORT0_HPR_ENABLE or self.DDR_PORT1_HPR_ENABLE or self.DDR_PORT2_HPR_ENABLE or self.DDR_PORT3_HPR_ENABLE

    DDR_HPRLPR_QUEUE_PARTITION: str = "HPR(0)/LPR(32)"
    def get_ddrc_lpr_num_entries(self):
        partition = self.DDR_HPRLPR_QUEUE_PARTITION
        if partition == "HPR(0)/LPR(32)":
            return 31
        elif partition == "HPR(8)/LPR(24)":
            return 23
        elif partition == "HPR(16)/LPR(16)":
            return 15
        elif partition == "HPR(24)/LPR(8)":
            return 7
        elif partition == "HPR(32)/LPR(0)":
            return 0
        else:
            raise ValueError(f"Invalid HPR/LPR partition: {partition}")
    DDR_HPR_TO_CRITICAL_PRIORITY_LEVEL: int = 15
    DDR_LPR_TO_CRITICAL_PRIORITY_LEVEL: int = 2

    # DDR_PERIPHERAL_CLKSRC: str = "DDR PLL" # Hardcoded
    DDR_PERIPHERAL_DIVISOR0: int = 2
    DDR_WRITE_TO_CRITICAL_PRIORITY_LEVEL: int = 2

    @property
    def DDR_FREQ_MHZ(self):
        freq = self.DDR_DDR_PLL_FREQMHZ / self.DDR_PERIPHERAL_DIVISOR0
        return ceil(freq * 1000000) / 1000000

    # DCI_PERIPHERAL_CLKSRC: str = "DDR PLL" # Appears to be hardwired
    DCI_PERIPHERAL_DIVISOR0: int
    DCI_PERIPHERAL_DIVISOR1: int
    @property
    def DCI_PERIPHERAL_FREQMHZ(self):
        return (self.DDR_DDR_PLL_FREQMHZ /
                (self.DCI_PERIPHERAL_DIVISOR0 * self.DCI_PERIPHERAL_DIVISOR1))

    IOPLL_CTRL_FBDIV: int
    @property
    def IO_IO_PLL_FREQMHZ(self):
        return self.CRYSTAL_PERIPHERAL_FREQMHZ * self.IOPLL_CTRL_FBDIV

    # DDR_TRAIN_DATA_EYE: bool = True
    # DDR_TRAIN_READ_GATE: bool = True
    # DDR_TRAIN_WRITE_LEVEL: bool = True (False for LPDDR2)
    # DDR_MEMORY_TYPE: str = "DDR 3"
    # DDR_SPEED_BIN: str = "DDR3_1066F"

    DDR_AL: int = 0
    DDR_BL: int # 4 or 8 (or 16 for LPDDR2)
    DDR_CL: int
    DDR_CWL: int
    DDR_T_FAW: float
    DDR_T_RAS_MIN: float
    DDR_T_RC: float
    DDR_T_RCD: int
    DDR_T_RP: int

    @property
    def _DDR_RL(self):
        return self.DDR_AL + self.DDR_CL
    @property
    def _DDR_T_WR(self):
        return ceil(0.015 * self.DDR_FREQ_MHZ)
    @property
    def _DDR_T_WTR(self):
        return max(ceil(0.0075 * self.DDR_FREQ_MHZ), 4)

    # 0xF8006004:0
    def get_ddrc_t_rfc_nom_x32(self):
        # 64ms / 8192 rows
        return clamp_floor(64000 / 8192 * self.DDR_FREQ_MHZ / 32, 0xfff)
    # 0xF8006014:0
    def get_ddrc_t_rc(self):
        return clamp_ceil(self.DDR_FREQ_MHZ * self.DDR_T_RC / 1000, 0x3f)
    # 0xF8006014:6
    def get_ddrc_t_rfc_min(self):
        # Base on vivado behavior
        return clamp_ceil(0.16 * self.DDR_FREQ_MHZ, 0xff)
    # 0xF8006018:0
    def get_ddrc_wr2pre(self):
        wr2pre = self.DDR_CWL + self.DDR_BL//2 + self._DDR_T_WR
        if False: # LPDDR2
            return clamp_val(wr2pre + 1, 0x1f)
        return clamp_val(wr2pre, 0x1f)
    # 0xF8006018:10
    def get_ddrc_t_faw(self):
        return clamp_ceil(self.DDR_FREQ_MHZ * self.DDR_T_FAW / 1000, 0x3f)
    # 0xF8006018:16
    def get_ddrc_t_ras_max(self):
        # 70 us, 1024 cycle unit
        return clamp_floor(70 * self.DDR_FREQ_MHZ / 1024, 0x3f)
    # 0xF8006018:22
    def get_ddrc_t_ras_min(self):
        return clamp_ceil(self.DDR_FREQ_MHZ * self.DDR_T_RAS_MIN / 1000, 0x1f)
    # 0xF800601C:0
    def get_ddrc_write_latency(self):
        if False: # LPDDR2
            return self.DDR_CWL
        return clamp_val(self.DDR_CWL - 1, 0x1f)
    # 0xF800601C:5
    def get_ddrc_rd2wr(self):
        val = self._DDR_RL + self.DDR_BL//2 - self.DDR_CWL
        if False: # LPDDR2
            raise NotImplementedError
        return clamp_val(val + 2, 0x1f)
    # 0xF800601C:10
    def get_ddrc_wr2rd(self):
        wr2rd = self.DDR_CWL + self._DDR_T_WTR + self.DDR_BL//2
        if False: # LPDDR2
            return clamp_val(wr2rd + 1, 0x1f)
        return clamp_val(wr2rd, 0x1f)
    # 0xF800601C:23
    def get_ddrc_rd2pre(self):
        if False: # LPDDR2 or DDR2
            # DDR2: AL + BL/2 + max(tRTP, 2) - 2
            # LPDDR2: BL/2 + tRTP - 1
            raise NotImplementedError
        return clamp_ceil(max(0.0075 * self.DDR_FREQ_MHZ, 4) + self.DDR_AL,
                              0x1f)
    # 0xF8006020:5
    def get_ddrc_t_rrd(self):
        return max(ceil(0.0075 * self.DDR_FREQ_MHZ), 4)
    # 0xF800602C:0
    def get_ddrc_emr2(self):
        return max(self.DDR_CWL - 5, 0) << 3
    # 0xF8006030:0
    def get_ddrc_mr(self):
        if False: # LPDDR2 or DDR2
            raise NotImplementedError
        # MR0 for DDR3
        bl = 0 if self.DDR_BL == 8 else 2
        cl2 = self.DDR_CL > 13
        cl46 = (self.DDR_CL - 5) & 0x7
        dll = 1
        wr = self._DDR_T_WR - 4
        return bl | (cl2 << 2) | (cl46 << 4) | (dll << 8) | (wr << 9)
    # 0xF8006034:0
    def get_ddrc_burst_rdwr(self):
        return self.DDR_BL // 2
    # 0xF8006034:4
    def get_ddrc_pre_cke_x1024(self):
        # 700 us based on vivado output
        return clamp_ceil(700 * self.DDR_FREQ_MHZ / 1024, 0x3ff)
    # 0xF800605C:12
    def get_ddrc_wr_odt_hold(self):
        return self.DDR_BL // 2 + 1
    # 0xF8006068:0
    def get_ddrc_wrlvl_ww(self):
        return clamp_val(self.DDR_CL + 58, 0xff)
    # 0xF8006068:8
    def get_ddrc_rdlvl_rr(self):
        return clamp_val(self.DDR_CL + 58, 0xff)
    # 0xF8006078:12
    def get_ddrc_t_cksre(self):
        return max(ceil(0.0075 * self.DDR_FREQ_MHZ), 4) + 1
    # 0xF8006078:16
    def get_ddrc_t_cksrx(self):
        return max(ceil(0.0075 * self.DDR_FREQ_MHZ), 4) + 1
    # 0xF80060A8:0
    def get_t_zq_short_interval_x1024(self):
        # 100 ms based on vivado output
        return clamp_floor(100000 * self.DDR_FREQ_MHZ / 1024, 0xfffff)
    # 0xF80060A8:20
    def get_dram_rstn_x1024(self):
        # 200 us based on vivado output
        return clamp_ceil(200 * self.DDR_FREQ_MHZ / 1024, 0xff)
    # 0xF80060AC:1
    def get_deeppowerdown_to_x1024(self):
        # 500 us based on vivado output
        return clamp_ceil(500 * self.DDR_FREQ_MHZ / 1024, 0xff)
    # 0xF80060B8:0
    def get_ddrc_dfi_t_rddata_en(self):
        if False: # LPDDR2
            return self.DDR_CL
        return clamp_val(self.DDR_CL - 1, 0x1f)
    # 0xF8006194:0
    def get_phy_wr_rl_delay(self):
        return max(self.DDR_CWL - 4, 1)
    # 0xF8006194:5
    def get_phy_rd_rl_delay(self):
        return max(self.DDR_CL - 3, 1)
    # 0xF80062B0:4
    def get_ddrc_idle_after_reset_x32(self):
        # 1.08 us based on vivado output
        return clamp_ceil(1.08 * self.DDR_FREQ_MHZ / 32, 0xff)
    # 0xF80062B4:0
    def get_ddrc_max_auto_init_x1024(self):
        # 322.5 us based on vivado output
        return clamp_ceil(322.5 * self.DDR_FREQ_MHZ / 1024, 0xff)
    # 0xF80062B4:8
    def get_ddrc_dev_zqinit_x32(self):
        # 1.08 us based on vivado output
        return clamp_ceil(1.08 * self.DDR_FREQ_MHZ / 32, 0x3ff)

    DDR_DQS_TO_CLK_DELAY_0: float
    DDR_DQS_TO_CLK_DELAY_1: float
    DDR_DQS_TO_CLK_DELAY_2: float
    DDR_DQS_TO_CLK_DELAY_3: float
    def get_ddr_dqs_to_clk_delay(self, n):
        return (self.DDR_DQS_TO_CLK_DELAY_0,
                self.DDR_DQS_TO_CLK_DELAY_1,
                self.DDR_DQS_TO_CLK_DELAY_2,
                self.DDR_DQS_TO_CLK_DELAY_3)[n]
    def get_wrlvl_init_ratio(self, n):
        dqs_to_clk_delay = self.get_ddr_dqs_to_clk_delay(n)
        return clamp_floor(dqs_to_clk_delay * self.DDR_FREQ_MHZ * 0.256, 0x3ff)
    def get_wr_dqs_slave_ratio(self, n):
        return self.get_wrlvl_init_ratio(n) + 128
    def get_wr_data_slave_ratio(self, n):
        return self.get_wrlvl_init_ratio(n) + 192

    DDR_BOARD_DELAY0: float
    DDR_BOARD_DELAY1: float
    DDR_BOARD_DELAY2: float
    DDR_BOARD_DELAY3: float
    def get_ddr_board_delay(self, n):
        return (self.DDR_BOARD_DELAY0,
                self.DDR_BOARD_DELAY1,
                self.DDR_BOARD_DELAY2,
                self.DDR_BOARD_DELAY3)[n]
    def get_gatelvl_init_ratio(self, n):
        board_delay = self.get_ddr_board_delay(n)
        return clamp_floor(board_delay * self.DDR_FREQ_MHZ * 0.512 + 96, 0x3ff)
    def get_fifo_we_slave_ratio(self, n):
        return self.get_gatelvl_init_ratio(n) + 85

    EN_CLK0_PORT: bool = False
    EN_CLK1_PORT: bool = False
    EN_CLK2_PORT: bool = False
    EN_CLK3_PORT: bool = False
    FCLK0_PERIPHERAL_CLKSRC: str = "IO PLL"
    FCLK0_PERIPHERAL_DIVISOR0: int = 1
    FCLK0_PERIPHERAL_DIVISOR1: int = 1
    FCLK1_PERIPHERAL_CLKSRC: str = "IO PLL"
    FCLK1_PERIPHERAL_DIVISOR0: int = 1
    FCLK1_PERIPHERAL_DIVISOR1: int = 1
    FCLK2_PERIPHERAL_CLKSRC: str = "IO PLL"
    FCLK2_PERIPHERAL_DIVISOR0: int = 1
    FCLK2_PERIPHERAL_DIVISOR1: int = 1
    FCLK3_PERIPHERAL_CLKSRC: str = "IO PLL"
    FCLK3_PERIPHERAL_DIVISOR0: int = 1
    FCLK3_PERIPHERAL_DIVISOR1: int = 1
    def get_fclk_srcsel(self, n):
        clksrc = (self.FCLK0_PERIPHERAL_CLKSRC, self.FCLK1_PERIPHERAL_CLKSRC,
                  self.FCLK2_PERIPHERAL_CLKSRC, self.FCLK3_PERIPHERAL_CLKSRC)[n]
        return (2, 3, 0)[pll_index(clksrc)]

    @property
    def FPGA0_PERIPHERAL_FREQMHZ(self):
        return (self.get_freqmhz(self.FCLK0_PERIPHERAL_CLKSRC) /
                (self.FCLK0_PERIPHERAL_DIVISOR0 * self.FCLK0_PERIPHERAL_DIVISOR1))
    @property
    def FPGA1_PERIPHERAL_FREQMHZ(self):
        return (self.get_freqmhz(self.FCLK1_PERIPHERAL_CLKSRC) /
                (self.FCLK1_PERIPHERAL_DIVISOR0 * self.FCLK1_PERIPHERAL_DIVISOR1))
    @property
    def FPGA2_PERIPHERAL_FREQMHZ(self):
        return (self.get_freqmhz(self.FCLK2_PERIPHERAL_CLKSRC) /
                (self.FCLK2_PERIPHERAL_DIVISOR0 * self.FCLK2_PERIPHERAL_DIVISOR1))
    @property
    def FPGA3_PERIPHERAL_FREQMHZ(self):
        return (self.get_freqmhz(self.FCLK3_PERIPHERAL_CLKSRC) /
                (self.FCLK3_PERIPHERAL_DIVISOR0 * self.FCLK3_PERIPHERAL_DIVISOR1))

    BANK0_VOLTAGE: BankIOType = BankIOType.LVCMOS18
    BANK1_VOLTAGE: BankIOType = BankIOType.LVCMOS18
    _MIO_PINS = field(init=False)

    GPIO_MIO_GPIO_ENABLE: bool = False

    def __post_init__(self):
        self._MIO_PINS = [MIOPin(i) for i in range(54)]
        if self.GPIO_MIO_GPIO_ENABLE:
            self.enable_mio_gpio()

    def _get_mio_pin(self, n):
        pin = self._MIO_PINS[n]
        if not pin.used:
            raise ValueError("Cannot set properties on unused MIO pin {n}")
        return pin

    def _release_mio_pin(self, n):
        self._MIO_PINS[n].reset()

    def _get_mio_iotype(self, n):
        return self.BANK0_VOLTAGE if n < 16 else self.BANK1_VOLTAGE

    def set_mio_pullup(self, n, pullup=True):
        pin = self._get_mio_pin(n)
        if n >= 2 and n <= 8 and pullup:
            raise ValueError("Cannot enable pullup on MIO pin [2, 8]")
        pin.pullup = pullup

    def set_mio_slew(self, n, slew):
        self._get_mio_pin(n).slew = slew

    def set_mio_iotype(self, n, iotype):
        bank_type = self._get_mio_iotype(n)
        if iotype != bank_type and (iotype not in _BANK_TYPE_18 or
                                    bank_type not in _BANK_TYPE_18):
            raise ValueError("Incompatible io type")
        self._get_mio_pin(n).iotype = iotype

    def _enable_single_mio_gpio(self, n, pin):
        iotype = self._get_mio_iotype(n)
        direction = IODirection.Out if n in (7, 8) else IODirection.InOut
        # Selector is 0 for all MIO pins for GPIO
        pin.set_use(iotype, direction, True, 0)

    def enable_mio_gpio(self):
        self.GPIO_MIO_GPIO_ENABLE = True
        for n in range(54):
            pin = self._MIO_PINS[n]
            if pin.used:
                continue
            self._enable_single_mio_gpio(n, pin)

    def disable_mio_gpio(self):
        if not self.GPIO_MIO_GPIO_ENABLE:
            return
        self.GPIO_MIO_GPIO_ENABLE = False
        for n in range(54):
            pin = self._MIO_PINS[n]
            if pin.is_gpio:
                pin.reset()

    def _use_mio(self, n, direction, select):
        pin = self._MIO_PINS[n]
        if pin.used and not pin.is_gpio:
            raise ValueError(f"Conflict use of MIO pin {n}")
        iotype = self._get_mio_iotype(n)
        pin.set_use(iotype, direction, False, select)
        if n < 2 or n > 8:
            # Turn pull up on by default to match vivado behavior
            pin.pullup = True

    def _release_mio(self, n):
        pin = self._MIO_PINS[n]
        pin.reset()
        if self.GPIO_MIO_GPIO_ENABLE:
            self._enable_single_mio_gpio(n, pin)

    @property
    def memory_interface_enabled(self):
        return (self.QSPI_PERIPHERAL_ENABLE or self.NOR_PERIPHERAL_ENABLE or
                self.NAND_PERIPHERAL_ENABLE)

    @property
    def QSPI_PERIPHERAL_ENABLE(self):
        return (self.QSPI_GRP_SINGLE_SS_ENABLE or self.QSPI_GRP_SS1_ENABLE or
                self.QSPI_GRP_IO1_ENABLE)

    QSPI_PERIPHERAL_CLKSRC: str = "IO PLL"
    QSPI_PERIPHERAL_DIVISOR0: int = 5
    @property
    def QSPI_PERIPHERAL_FREQMHZ(self):
        return (self.get_freqmhz(self.QSPI_PERIPHERAL_CLKSRC) /
                self.QSPI_PERIPHERAL_DIVISOR0)
    def get_qspi_clksrc(self):
        return (2, 3, 0)[pll_index(self.QSPI_PERIPHERAL_CLKSRC)]

    QSPI_GRP_SINGLE_SS_ENABLE: bool = False
    SINGLE_QSPI_DATA_MODE: str = "x4"
    QSPI_GRP_SS1_ENABLE: bool = False
    DUAL_STACK_QSPI_DATA_MODE: str = "x4"
    QSPI_GRP_IO1_ENABLE: bool = False
    # DUAL_PARALLEL_QSPI_DATA_MODE: = "x8"

    QSPI_GRP_FBCLK_ENABLE: bool = False

    def enable_qspi(self, type, mode):
        if self.memory_interface_enabled and not self.QSPI_PERIPHERAL_ENABLE:
            raise ValueError("Only one memory interface can be enabled")
        self.disable_qspi()
        if type == "SINGLE_SS" or type == "SINGLE":
            if mode == "x1":
                self._use_mio(1, IODirection.Out, 0b000_00_0_1)
                self._use_mio(2, IODirection.Out, 0b000_00_0_1)
                self._use_mio(3, IODirection.In, 0b000_00_0_1)
                self._use_mio(5, IODirection.InOut, 0b000_00_0_1)
                self._use_mio(6, IODirection.Out, 0b000_00_0_1)
            elif mode == "x2":
                self._use_mio(1, IODirection.Out, 0b000_00_0_1)
                self._use_mio(2, IODirection.InOut, 0b000_00_0_1)
                self._use_mio(3, IODirection.InOut, 0b000_00_0_1)
                self._use_mio(5, IODirection.InOut, 0b000_00_0_1)
                self._use_mio(6, IODirection.Out, 0b000_00_0_1)
            elif mode == "x4":
                self._use_mio(1, IODirection.Out, 0b000_00_0_1)
                self._use_mio(2, IODirection.InOut, 0b000_00_0_1)
                self._use_mio(3, IODirection.InOut, 0b000_00_0_1)
                self._use_mio(4, IODirection.InOut, 0b000_00_0_1)
                self._use_mio(5, IODirection.InOut, 0b000_00_0_1)
                self._use_mio(6, IODirection.Out, 0b000_00_0_1)
            else:
                raise ValueError("Invalid data mode for QSPI Single SS")
            self.QSPI_GRP_SINGLE_SS_ENABLE = True
            self.SINGLE_QSPI_DATA_MODE = mode
        elif type == "DUAL_STACK" or type == "SS1":
            if mode == "x1":
                self._use_mio(0, IODirection.Out, 0b000_00_0_1)
                self._use_mio(1, IODirection.Out, 0b000_00_0_1)
                self._use_mio(2, IODirection.Out, 0b000_00_0_1)
                self._use_mio(3, IODirection.In, 0b000_00_0_1)
                self._use_mio(5, IODirection.InOut, 0b000_00_0_1)
                self._use_mio(6, IODirection.Out, 0b000_00_0_1)
            elif mode == "x2":
                self._use_mio(0, IODirection.Out, 0b000_00_0_1)
                self._use_mio(1, IODirection.Out, 0b000_00_0_1)
                self._use_mio(2, IODirection.InOut, 0b000_00_0_1)
                self._use_mio(3, IODirection.InOut, 0b000_00_0_1)
                self._use_mio(5, IODirection.InOut, 0b000_00_0_1)
                self._use_mio(6, IODirection.Out, 0b000_00_0_1)
            elif mode == "x4":
                self._use_mio(0, IODirection.Out, 0b000_00_0_1)
                self._use_mio(1, IODirection.Out, 0b000_00_0_1)
                self._use_mio(2, IODirection.InOut, 0b000_00_0_1)
                self._use_mio(3, IODirection.InOut, 0b000_00_0_1)
                self._use_mio(4, IODirection.InOut, 0b000_00_0_1)
                self._use_mio(5, IODirection.InOut, 0b000_00_0_1)
                self._use_mio(6, IODirection.Out, 0b000_00_0_1)
            else:
                raise ValueError("Invalid data mode for QSPI Dual Stack SS")
            self.QSPI_GRP_SS1_ENABLE = True
            self.DUAL_STACK_QSPI_DATA_MODE = mode
        else type == "DUAL_PARALLEL" or type == "IO1":
            assert mode == "x8"
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
            self.QSPI_GRP_IO1_ENABLE = True
        else:
            raise ValueError(f"Invalid QSPI type {type}")

    def disable_qspi(self):
        if not self.QSPI_PERIPHERAL_ENABLE:
            return
        self.disable_qspi_fbclk()
        if self.QSPI_GRP_SINGLE_SS_ENABLE:
            self.QSPI_GRP_SINGLE_SS_ENABLE = False
            for n in range(1, 4):
                self._release_mio(n)
            if self.SINGLE_QSPI_DATA_MODE == "x4":
                self._release_mio(4)
            for n in range(5, 7):
                self._release_mio(n)
        if self.QSPI_GRP_SS1_ENABLE:
            self.QSPI_GRP_SS1_ENABLE = False
            for n in range(4):
                self._release_mio(n)
            if self.DUAL_STACK_QSPI_DATA_MODE == "x4":
                self._release_mio(4)
            for n in range(5, 7):
                self._release_mio(n)
        if self.QSPI_GRP_IO1_ENABLE:
            self.QSPI_GRP_IO1_ENABLE = False
            for n in range(7):
                self._release_mio(n)
            for n in range(9, 14):
                self._release_mio(n)

    def enable_qspi_fbclk(self):
        if not self.QSPI_PERIPHERAL_ENABLE:
            raise ValueError("QSPI FB Clock enabled without enabling QSPI")
        self.QSPI_GRP_FBCLK_ENABLE = True
        self._use_mio(8, IODirection.Out, 0b000_00_0_1)

    def disable_qspi_fbclk(self):
        if not self.QSPI_GRP_FBCLK_ENABLE:
            return;
        self.QSPI_GRP_FBCLK_ENABLE = False
        self._release_mio(8)

    SMC_PERIPHERAL_CLKSRC: str = "IO PLL"
    SMC_PERIPHERAL_DIVISOR0: int = 1
    @property
    def SMC_PERIPHERAL_FREQMHZ(self):
        return (self.get_freqmhz(self.SMC_PERIPHERAL_CLKSRC) /
                self.SMC_PERIPHERAL_DIVISOR0)
    def get_smc_clksrc(self):
        return (2, 3, 0)[pll_index(self.SMC_PERIPHERAL_CLKSRC)]

    NOR_PERIPHERAL_ENABLE: bool = False
    NOR_GRP_A25_ENABLE: bool = False
    NOR_GRP_CS0_ENABLE: bool = False
    NOR_GRP_CS1_ENABLE: bool = False
    def enable_nor(self, addr25=False, cs0=False, cs1=False):
        if self.memory_interface_enabled and not self.NOR_PERIPHERAL_ENABLE:
            raise ValueError("Only one memory interface can be enabled")
        if addr25:
            if cs1:
                raise ValueError("MIO pin 0 cannot be used for both addr[25] and cs1")
            self._use_mio(1, IODirection.Out, 0b000_01_0_0)
            self.NOR_GRP_A25_ENABLE = True
        elif cs1:
            self._use_mio(1, IODirection.Out, 0b000_10_0_0)
            self.NOR_GRP_CS1_ENABLE = True
        if cs0:
            self._use_mio(0, IODirection.Out, 0b000_10_0_0)
            self.NOR_GRP_CS0_ENABLE = True
        for n in range(3, 7):
            self._use_mio(n, IODirection.InOut, 0b000_01_0_0)
        self._use_mio(7, IODirection.Out, 0b000_01_0_0)
        self._use_mio(8, IODirection.Out, 0b010_00_0_0)
        for n in range(9, 12):
            self._use_mio(n, IODirection.InOut, 0b000_01_0_0)
        self._use_mio(13, IODirection.InOut, 0b000_01_0_0)
        for n in range(15, 40):
            self._use_mio(n, IODirection.Out, 0b000_01_0_0)
        self.NOR_PERIPHERAL_ENABLE = True

    def disable_nor(self):
        if not self.NOR_PERIPHERAL_ENABLE:
            return
        self.NOR_PERIPHERAL_ENABLE = False
        if self.NOR_GRP_CS0_ENABLE:
            self._release_mio(0)
            self.NOR_GRP_CS0_ENABLE = False
        if self.NOR_GRP_CS1_ENABLE or self.NOR_GRP_A25_ENABLE:
            self._release_mio(1)
            self.NOR_GRP_CS1_ENABLE = False
            self.NOR_GRP_A25_ENABLE = False
        for n in range(3, 40):
            if n == 12 or n == 14:
                continue
            self._release_mio(n)

    NAND_PERIPHERAL_ENABLE: bool = False
    NAND_GRP_D8_ENABLE: bool = False
    def enable_nand(self, d8=False):
        if self.memory_interface_enabled and not self.NAND_PERIPHERAL_ENABLE:
            raise ValueError("Only one memory interface can be enabled")
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
        if d8:
            for n in range(16, 24):
                self._use_mio(n, IODirection.InOut, 0b000_10_0_0)
            self.NAND_GRP_D8_ENABLE = True
        self.NAND_PERIPHERAL_ENABLE = True

    def disable_nand(self):
        if not self.NAND_PERIPHERAL_ENABLE:
            return
        self.NAND_PERIPHERAL_ENABLE = False
        for n in range(15):
            if n == 1:
                continue
            self._release_mio(n)
        if self.NAND_GRP_D8_ENABLE:
            for n in range(16, 24):
                self._release_mio(n)

class ArrayWriter:
    def __init__(self, io, name):
        self.io = io
        self.name = name

    def __enter__(self):
        print(f'static const unsigned long {self.name}[] = {{', file=self.io)
        return self

    def __exit__(self, exc_type, esc_val, esc_tb):
        self.exit()
        print(f'}};', file=self.io)

    def exit(self):
        print('    EMIT_EXIT(),', file=self.io)

    def clear(self, addr):
        print(f'    EMIT_CLEAR({addr:#010X}),', file=self.io)

    def write(self, addr, value):
        print(f'    EMIT_WRITE({addr:#010X}, {value:#010X}U),', file=self.io)

    def maskwrite(self, addr, mask, value):
        print(f'    EMIT_MASKWRITE({addr:#010X}, {mask:#010X}U, {value:#010X}U),',
              file=self.io)

    def maskpoll(self, addr, mask):
        print(f'    EMIT_MASKPOLL({addr:#010X}, {mask:#010X}U),', file=self.io)

    def maskdelay(self, addr, mask):
        print(f'    EMIT_MASKDELAY({addr:#010X}, {mask}),', file=self.io)

    def get_pll_settings(self, fdiv):
        if fdiv == 13:
            return 2, 6, 750
        elif fdiv == 14:
            return 2, 6, 700
        elif fdiv == 15:
            return 2, 6, 650
        elif fdiv == 16:
            return 2, 10, 625
        elif fdiv == 16:
            return 2, 10, 625
        elif fdiv == 17:
            return 2, 10, 575
        elif fdiv == 18:
            return 2, 10, 550
        elif fdiv == 19:
            return 2, 10, 525
        elif fdiv == 20:
            return 2, 12, 500
        elif fdiv == 21:
            return 2, 12, 475
        elif fdiv == 22:
            return 2, 12, 450
        elif fdiv == 23:
            return 2, 12, 425
        elif 24 <= fdiv <= 25:
            return 2, 12, 400
        elif fdiv == 26:
            return 2, 12, 375
        elif 27 <= fdiv <= 28:
            return 2, 12, 350
        elif 29 <= fdiv <= 30:
            return 2, 12, 325
        elif 31 <= fdiv <= 33:
            return 2, 2, 300
        elif 34 <= fdiv <= 36:
            return 2, 2, 275
        elif 37 <= fdiv <= 40:
            return 2, 2, 250
        elif 41 <= fdiv <= 47:
            return 3, 12, 250
        elif 48 <= fdiv <= 66:
            return 2, 4, 250
        else:
            raise ValueError(f"Invalid FDIV: {fdiv}")

    def unlock(self):
        self.write(0xF8000008, 0x0000DF0D)

    def lock(self):
        self.write(0xF8000004, 0x0000767B)

    def init_pll(self, pll_idx, pll_fdiv):
        pll_cb, pll_res, lock_cnt = self.get_pll_settings(pll_fdiv)
        ctrl_addr = 0xF8000100 + pll_idx * 4
        cfg_addr = 0xF8000110 + pll_idx * 4
        # Program PLL_CFG[LOCK_CNT, PLL_CP, PLL_RES].
        self.maskwrite(cfg_addr, 0x003FFFF0,
                       (pll_res << 4) | (pll_cb << 8) | (lock_cnt << 12))
        # Program PLL_CTRL[PLL_FDIV].
        self.maskwrite(ctrl_addr, 0x0007F000, pll_fdiv << 12)
        # Force the PLL into bypass mode
        self.maskwrite(ctrl_addr, 0x10, 0x10)
        # Assert and de-assert the PLL reset
        self.maskwrite(ctrl_addr, 0x1, 0x1)
        self.maskwrite(ctrl_addr, 0x1, 0x0)
        # Verify that the PLL is locked by polling
        self.maskpoll(0xF800010C, 1 << pll_idx)
        # Disable the PLL bypass mode
        self.maskwrite(ctrl_addr, 0x10, 0x00)

class DataWriter:
    def __init__(self, io, version, config):
        self.io = io
        self.version = version
        self.suffix = f'_{version}_0'
        self.config = config

    def array_writer(self, name):
        return ArrayWriter(self.io, name + self.suffix)

    def write_all(self):
        self.pll_init()
        self.clock_init()
        self.ddr_init()
        self.mio_init()
        self.peripherals_init()
        self.post_config()
        self.debug()

    def pll_init(self):
        with self.array_writer("ps7_pll_init_data") as w:
            w.unlock()

            # Init ARM PLL
            w.init_pll(0, self.config.ARMPLL_CTRL_FBDIV)
            # ARM_CLK_CTRL
            # [5:4] SRCSEL = CPU_PERIPHERAL_CLKSRC
            # [13:8] DIVISOR = CPU_PERIPHERAL_DIVISOR0
            # [24:24] CPU_6OR4XCLKACT = 0x1
            # [25:25] CPU_3OR2XCLKACT = 0x1
            # [26:26] CPU_2XCLKACT = 0x1
            # [27:27] CPU_1XCLKACT = 0x1
            # [28:28] CPU_PERI_CLKACT = 0x1
            arm_divisor = self.config.CPU_PERIPHERAL_DIVISOR0
            arm_srcsel = (0, 2, 3)[pll_index(self.config.CPU_PERIPHERAL_CLKSRC)]
            w.maskwrite(0xF8000120, 0x1F003F30,
                        0x1F000000 | (arm_divisor << 8) | (arm_srcsel << 4))

            # Init DDR PLL
            w.init_pll(1, self.config.DDRPLL_CTRL_FBDIV)
            # DDR_CLK_CTRL
            # [0:0] DDR_3XCLKACT = 0x1
            # [1:1] DDR_2XCLKACT = 0x1
            div_3x = self.config.DDR_PERIPHERAL_DIVISOR0
            div_2x = div_3x * 3 // 2
            # [25:20] DDR_3XCLK_DIVISOR = DDR_PERIPHERAL_DIVISOR0
            # [31:26] DDR_2XCLK_DIVISOR = DDR_PERIPHERAL_DIVISOR0 * 3 / 2
            w.maskwrite(0xF8000124, 0xFFF00003,
                        0x00000003 | (div_3x << 20) | (div_2x << 26))

            # Init IO PLL
            w.init_pll(2, self.config.IOPLL_CTRL_FBDIV)

            w.lock()

    def clock_init(self):
        with self.array_writer("ps7_clock_init_data") as w:
            w.unlock()

            # DCI_CLK_CTRL
            # [0:0] CLKACT = 0x1
            # [13:8] DIVISOR0 = DCI_PERIPHERAL_DIVISOR0
            # [25:20] DIVISOR1 = DCI_PERIPHERAL_DIVISOR1
            w.maskwrite(0xF8000128, 0x03F03F01,
                        0x00000001 |
                        (self.config.DCI_PERIPHERAL_DIVISOR0 << 8) |
                        (self.config.DCI_PERIPHERAL_DIVISOR1 << 20))
            # GEM0_RCLK_CTRL
            # [0:0] CLKACT = 0x1
            # [4:4] SRCSEL = 0x0
            w.maskwrite(0xF8000138, 0x00000011, 0x00000001)
            # GEM0_CLK_CTRL
            # [0:0] CLKACT = 0x1
            # [6:4] SRCSEL = 0x0
            # [13:8] DIVISOR = 0x8
            # [25:20] DIVISOR1 = 0x5
            w.maskwrite(0xF8000140, 0x03F03F71, 0x00500801)
            if self.config.NOR_PERIPHERAL_ENABLE or self.config.NAND_PERIPHERAL_ENABLE:
                # SMC_CLK_CTRL
                # [0:0] CLKACT = 0x1
                # [5:4] SRCSEL
                # [13:8] DIVISOR = SMC_PERIPHERAL_DIVISOR0
                w.maskwrite(0xF8000148, 0x00003F31,
                            0x00000001 |
                            (self.config.get_smc_clksrc() << 4) |
                            (self.config.SMC_PERIPHERAL_DIVISOR0 << 8))
            if self.config.QSPI_PERIPHERAL_ENABLE:
                # LQSPI_CLK_CTRL
                # [0:0] CLKACT = 0x1
                # [5:4] SRCSEL
                # [13:8] DIVISOR = QSPI_PERIPHERAL_DIVISOR0
                w.maskwrite(0xF800014C, 0x00003F31,
                            0x00000001 |
                            (self.config.get_qspi_clksrc() << 4) |
                            (self.config.QSPI_PERIPHERAL_DIVISOR0 << 8))
            # SDIO_CLK_CTRL
            # [0:0] CLKACT0 = 0x1
            # [1:1] CLKACT1 = 0x0
            # [5:4] SRCSEL = 0x0
            # [13:8] DIVISOR = 0x14
            w.maskwrite(0xF8000150, 0x00003F33, 0x00001401)
            # UART_CLK_CTRL
            # [0:0] CLKACT0 = 0x0
            # [1:1] CLKACT1 = 0x1
            # [5:4] SRCSEL = 0x0
            # [13:8]DIVISOR = 0x14
            w.maskwrite(0xF8000154, 0x00003F33, 0x00001402)
            # CAN_CLK_CTRL
            # [0:0] CLKACT0 = 0x1
            # [1:1] CLKACT1 = 0x0
            # [5:4] SRCSEL = 0x0
            # [13:8] DIVISOR0 = 0x7
            # [25:20] DIVISOR1 = 0x6
            w.maskwrite(0xF800015C, 0x03F03F33, 0x00600701)
            # CAN_MIOCLK_CTRL
            # [5:0] CAN0_MUX = 0x0
            # [6:6] CAN0_REF_SEL = 0x0
            # [21:16] CAN1_MUX = 0x0
            # [22:22] CAN1_REF_SEL = 0x0
            w.maskwrite(0xF8000160, 0x007F007F, 0x00000000)
            # PCAP_CLK_CTRL
            # [0:0] CLKACT = 0x1
            # [5:4] SRCSEL = 0x0
            # [13:8] DIVISOR = 0x5
            w.maskwrite(0xF8000168, 0x00003F31, 0x00000501)
            if self.config.EN_CLK0_PORT:
                # FPGA0_CLK_CTRL
                # [5:4] SRCSEL
                # [13:8] DIVISOR0
                # [25:20] DIVISOR1
                w.maskwrite(0xF8000170, 0x03F03F30,
                            (self.config.get_fclk_srcsel(0) << 4) |
                            (self.config.FCLK0_PERIPHERAL_DIVISOR0 << 8) |
                            (self.config.FCLK0_PERIPHERAL_DIVISOR1 << 20))
            if self.config.EN_CLK1_PORT:
                # FPGA1_CLK_CTRL
                # [5:4] SRCSEL
                # [13:8] DIVISOR0
                # [25:20] DIVISOR1
                w.maskwrite(0xF8000180, 0x03F03F30,
                            (self.config.get_fclk_srcsel(1) << 4) |
                            (self.config.FCLK1_PERIPHERAL_DIVISOR0 << 8) |
                            (self.config.FCLK1_PERIPHERAL_DIVISOR1 << 20))
            if self.config.EN_CLK2_PORT:
                # FPGA2_CLK_CTRL
                # [5:4] SRCSEL
                # [13:8] DIVISOR0
                # [25:20] DIVISOR1
                w.maskwrite(0xF8000190, 0x03F03F30,
                            (self.config.get_fclk_srcsel(2) << 4) |
                            (self.config.FCLK2_PERIPHERAL_DIVISOR0 << 8) |
                            (self.config.FCLK2_PERIPHERAL_DIVISOR1 << 20))
            if self.config.EN_CLK3_PORT:
                # FPGA3_CLK_CTRL
                # [5:4] SRCSEL
                # [13:8] DIVISOR0
                # [25:20] DIVISOR1
                w.maskwrite(0xF80001A0, 0x03F03F30,
                            (self.config.get_fclk_srcsel(3) << 4) |
                            (self.config.FCLK3_PERIPHERAL_DIVISOR0 << 8) |
                            (self.config.FCLK3_PERIPHERAL_DIVISOR1 << 20))
            # CLK_621_TRUE
            # [0:0] CLK_621_TRUE = 0x0/0x1
            if self.config.APU_CLK_RATIO_ENABLE == "6:2:1":
                w.maskwrite(0xF80001C4, 0x00000001, 0x00000001)
            elif self.config.APU_CLK_RATIO_ENABLE == "4:2:1":
                w.maskwrite(0xF80001C4, 0x00000000, 0x00000000)
            else:
                raise ValueError(f"Invalid APU_CLK_RATIO_ENABLE: {self.config.APU_CLK_RATIO_ENABLE}. Should be either 6:2:1 or 4:2:1")
            # [0:0] DMA_CPU_2XCLKACT = 0x1
            # [2:2] USB0_CPU_1XCLKACT = 0x1
            # [3:3] USB1_CPU_1XCLKACT = 0x1
            # [6:6] GEM0_CPU_1XCLKACT = 0x1
            # [7:7] GEM1_CPU_1XCLKACT = 0x0
            # [10:10] SDI0_CPU_1XCLKACT = 0x1
            # [11:11] SDI1_CPU_1XCLKACT = 0x0
            # [14:14] SPI0_CPU_1XCLKACT = 0x0
            # [15:15] SPI1_CPU_1XCLKACT = 0x0
            # [16:16] CAN0_CPU_1XCLKACT = 0x1
            # [17:17] CAN1_CPU_1XCLKACT = 0x0
            # [18:18] I2C0_CPU_1XCLKACT = 0x1
            # [19:19] I2C1_CPU_1XCLKACT = 0x1
            # [20:20] UART0_CPU_1XCLKACT = 0x0
            # [21:21] UART1_CPU_1XCLKACT = 0x1
            # [22:22] GPIO_CPU_1XCLKACT = 0x1
            # [23:23] LQSPI_CPU_1XCLKACT = QSPI_PERIPHERAL_ENABLE
            # [24:24] SMC_CPU_1XCLKACT = 0x1
            w.maskwrite(0xF800012C, 0x01FFCCCD,
                        0x016D044D |
                        (self.config.QSPI_PERIPHERAL_ENABLE << 23))

            w.lock()

    def ddr_init(self):
        with self.array_writer("ps7_ddr_init_data") as w:
            # DDRC_CTRL
            # [0:0] reg_ddrc_soft_rstb = 0
            # [1:1] reg_ddrc_powerdown_en = 0x0
            # [3:2] reg_ddrc_data_bus_width = 0x0
            # [6:4] reg_ddrc_burst8_refresh = 0x0
            # [13:7] reg_ddrc_rdwr_idle_gap = 0x1
            # [14:14] reg_ddrc_dis_rd_bypass = 0x0
            # [15:15] reg_ddrc_dis_act_bypass = 0x0
            # [16:16] reg_ddrc_dis_auto_refresh = 0x0
            w.maskwrite(0xF8006000, 0x0001FFFF, 0x00000080)

            # TWO_RANK_CFG
            # [11:0] reg_ddrc_t_rfc_nom_x32
            # [13:12] reg_ddrc_active_ranks = 0x1 (Version: 1/2)
            # [13:12] reserved_reg_ddrc_active_ranks = 0x1 (Version: 3)
            # [18:14] reg_ddrc_addrmap_cs_bit0 = 0x0
            # [20:19] reg_ddrc_wr_odt_block = 0x1 (Version: 1/2)
            # [21:21] reg_ddrc_diff_rank_rd_2cycle_gap = 0x0 (Version: 1/2)
            # [26:22] reg_ddrc_addrmap_cs_bit1 = 0x0 (Version: 1/2)
            # [27:27] reg_ddrc_addrmap_open_bank = 0x0 (Version: 1/2)
            # [28:28] reg_ddrc_addrmap_4bank_ram = 0x0 (Version: 1/2)
            if self.version >= 3:
                w.maskwrite(0xF8006004, 0x0007FFFF,
                            0x00001000 |
                            self.config.get_ddrc_t_rfc_nom_x32())
            else:
                w.maskwrite(0xF8006004, 0x1FFFFFFF,
                            0x00081000 |
                            self.config.get_ddrc_t_rfc_nom_x32())

            # HPR_REG
            # [10:0] reg_ddrc_hpr_min_non_critical_x32 = 0xf
            # [21:11] reg_ddrc_hpr_max_starve_x32 = DDR_HPR_TO_CRITICAL_PRIORITY_LEVEL
            # [25:22] reg_ddrc_hpr_xact_run_length = 0xf
            w.maskwrite(0xF8006008, 0x03FFFFFF,
                        0x03C0000F |
                        (self.config.DDR_HPR_TO_CRITICAL_PRIORITY_LEVEL << 11))

            # LPR_REG
            # [10:0] reg_ddrc_lpr_min_non_critical_x32 = 0x1
            # [21:11] reg_ddrc_lpr_max_starve_x32 = DDR_LPR_TO_CRITICAL_PRIORITY_LEVEL
            # [25:22] reg_ddrc_lpr_xact_run_length = 0x8
            w.maskwrite(0xF800600C, 0x03FFFFFF,
                        0x02000001 |
                        (self.config.DDR_LPR_TO_CRITICAL_PRIORITY_LEVEL << 11))

            # WR_REG
            # [10:0] reg_ddrc_w_min_non_critical_x32 = 0x1
            # [14:11] reg_ddrc_w_xact_run_length = 0x8
            # [25:15] reg_ddrc_w_max_starve_x32 = DDR_WRITE_TO_CRITICAL_PRIORITY_LEVEL
            w.maskwrite(0xF8006010, 0x03FFFFFF,
                        0x00004001 |
                        (self.config.DDR_WRITE_TO_CRITICAL_PRIORITY_LEVEL << 15))

            # DRAM_PARAM_REG0
            # [5:0] reg_ddrc_t_rc
            # [13:6] reg_ddrc_t_rfc_min
            # [20:14] reg_ddrc_post_selfref_gap_x32 = 0x10
            w.maskwrite(0xF8006014, 0x001FFFFF,
                        0x00040000 |
                        self.config.get_ddrc_t_rc() |
                        (self.config.get_ddrc_t_rfc_min() << 6))

            # DRAM_PARAM_REG1
            # [4:0] reg_ddrc_wr2pre
            # [9:5] reg_ddrc_powerdown_to_x32 = 0x6
            # [15:10] reg_ddrc_t_faw
            # [21:16] reg_ddrc_t_ras_max
            # [26:22] reg_ddrc_t_ras_min
            # [31:28] reg_ddrc_t_cke = 0x4
            w.maskwrite(0xF8006018, 0xF7FFFFFF,
                        0x400000C0 |
                        self.config.get_ddrc_wr2pre() |
                        (self.config.get_ddrc_t_faw() << 10) |
                        (self.config.get_ddrc_t_ras_max() << 16) |
                        (self.config.get_ddrc_t_ras_min() << 22))

            # DRAM_PARAM_REG2
            # [4:0] reg_ddrc_write_latency
            # [9:5] reg_ddrc_rd2wr
            # [14:10] reg_ddrc_wr2rd
            # [19:15] reg_ddrc_t_xp = 0x5
            # [22:20] reg_ddrc_pad_pd = 0x0
            # [27:23] reg_ddrc_rd2pre
            # [31:28] reg_ddrc_t_rcd = DDR_T_RCD
            w.maskwrite(0xF800601C, 0xFFFFFFFF,
                        0x00028000 |
                        self.config.get_ddrc_write_latency() |
                        (self.config.get_ddrc_rd2wr() << 5) |
                        (self.config.get_ddrc_wr2rd() << 10) |
                        (self.config.get_ddrc_rd2pre() << 23)
                        (self.config.DDR_T_RCD << 28))

            # DRAM_PARAM_REG3
            # [4:2] reg_ddrc_t_ccd = 0x4
            # [7:5] reg_ddrc_t_rrd
            # [11:8] reg_ddrc_refresh_margin = 0x2
            # [15:12] reg_ddrc_t_rp = DDR_T_RP
            # [20:16] reg_ddrc_refresh_to_x32 = 0x8
            # [21:21] reg_ddrc_sdram = 0x1 (Version: 1/2)
            # [22:22] reg_ddrc_mobile = 0x0
            # [23:23] reg_ddrc_clock_stop_en = 0x0 (Version: 1/2)
            # [23:23] reg_ddrc_en_dfi_dram_clk_disable = 0x0 (Version: 3)
            # [28:24] reg_ddrc_read_latency = DDR_CL
            # [29:29] reg_phy_mode_ddr1_ddr2 = 0x1
            # [30:30] reg_ddrc_dis_pad_pd = 0x0
            # [31:31] reg_ddrc_loopback = 0x0 (Version: 1/2)
            if self.version >= 3:
                w.maskwrite(0xF8006020, 0x7FDFFFFC,
                            0x200802B0 |
                            (self.config.get_ddrc_t_rrd() << 5) |
                            (self.config.DDR_T_RP << 12) |
                            (self.config.DDR_CL << 24))
            else:
                w.maskwrite(0xF8006020, 0xFFFFFFFC,
                            0x202802B0 |
                            (self.config.get_ddrc_t_rrd() << 5) |
                            (self.config.DDR_T_RP << 12) |
                            (self.config.DDR_CL << 24))

            # DRAM_PARAM_REG4
            # [0:0] reg_ddrc_en_2t_timing_mode = 0x0
            # [1:1] reg_ddrc_prefer_write = 0x0
            # [5:2] reg_ddrc_max_rank_rd = 0xf (Version: 1/2)
            # [6:6] reg_ddrc_mr_wr = 0x0
            # [8:7] reg_ddrc_mr_addr = 0x0
            # [24:9] reg_ddrc_mr_data = 0x0
            # [25:25] ddrc_reg_mr_wr_busy = 0x0
            # [26:26] reg_ddrc_mr_type = 0x0
            # [27:27] reg_ddrc_mr_rdata_valid = 0x0
            if self.version >= 3:
                w.maskwrite(0xF8006024, 0x0FFFFFC3, 0x00000000)
            else:
                w.maskwrite(0xF8006024, 0x0FFFFFFF, 0x0000003C)

            # DRAM_INIT_PARAM
            # [6:0] reg_ddrc_final_wait_x32 = 0x7
            # [10:7] reg_ddrc_pre_ocd_x32 = 0x0
            # [13:11] reg_ddrc_t_mrd = 0x4
            w.maskwrite(0xF8006028, 0x00003FFF, 0x00002007)

            # DRAM_EMR_REG
            # [15:0] reg_ddrc_emr2
            # [31:16] reg_ddrc_emr3 = 0x0
            w.maskwrite(0xF800602C, 0xFFFFFFFF,
                        0x00000000 |
                        self.config.get_ddrc_emr2())

            # DRAM_EMR_MR_REG
            # [15:0] reg_ddrc_mr
            # [31:16] reg_ddrc_emr = 0x4
            w.maskwrite(0xF8006030, 0xFFFFFFFF,
                        0x00040000 |
                        self.config.get_ddrc_mr())

            # DRAM_BURST8_RDWR
            # [3:0] reg_ddrc_burst_rdwr
            # [13:4] reg_ddrc_pre_cke_x1024
            # [25:16] reg_ddrc_post_cke_x1024 = 0x1
            # [28:28] reg_ddrc_burstchop = 0x0
            w.maskwrite(0xF8006034, 0x13FF3FFF,
                        0x00010000 |
                        self.config.get_ddrc_burst_rdwr() |
                        (self.config.get_ddrc_pre_cke_x1024() << 4))

            # DRAM_DISABLE_DQ
            # [0:0] reg_ddrc_force_low_pri_n = 0x0
            # [1:1] reg_ddrc_dis_dq = 0x0
            # [6:6] reg_phy_debug_mode = 0x0 (Version: 1/2)
            # [7:7] reg_phy_wr_level_start = 0x0 (Version: 1/2)
            # [8:8] reg_phy_rd_level_start = 0x0 (Version: 1/2)
            # [12:9] reg_phy_dq0_wait_t = 0x0 (Version: 1/2)
            ddrc_force_low_pri_n = self.config.get_ddrc_force_low_pri_n()
            if self.version >= 3:
                w.maskwrite(0xF8006038, 0x00000003, 0x00000000 | ddrc_force_low_pri_n)
            else:
                w.maskwrite(0xF8006038, 0x00001FC3, 0x00000000 | ddrc_force_low_pri_n)

            # DRAM_ADDR_MAP_BANK
            # [3:0] reg_ddrc_addrmap_bank_b0 = 0x7
            # [7:4] reg_ddrc_addrmap_bank_b1 = 0x7
            # [11:8] reg_ddrc_addrmap_bank_b2 = 0x7
            # [15:12] reg_ddrc_addrmap_col_b5 = 0x0
            # [19:16] reg_ddrc_addrmap_col_b6 = 0x0
            w.maskwrite(0xF800603C, 0x000FFFFF, 0x00000777)

            # DRAM_ADDR_MAP_COL
            # [3:0] reg_ddrc_addrmap_col_b2 = 0x0
            # [7:4] reg_ddrc_addrmap_col_b3 = 0x0
            # [11:8] reg_ddrc_addrmap_col_b4 = 0x0
            # [15:12] reg_ddrc_addrmap_col_b7 = 0x0
            # [19:16] reg_ddrc_addrmap_col_b8 = 0x0
            # [23:20] reg_ddrc_addrmap_col_b9 = 0xf
            # [27:24] reg_ddrc_addrmap_col_b10 = 0xf
            # [31:28] reg_ddrc_addrmap_col_b11 = 0xf
            w.maskwrite(0xF8006040, 0xFFFFFFFF, 0xFFF00000)

            # DRAM_ADDR_MAP_ROW
            # [3:0] reg_ddrc_addrmap_row_b0 = 0x6
            # [7:4] reg_ddrc_addrmap_row_b1 = 0x6
            # [11:8] reg_ddrc_addrmap_row_b2_11 = 0x6
            # [15:12] reg_ddrc_addrmap_row_b12 = 0x6
            # [19:16] reg_ddrc_addrmap_row_b13 = 0x6
            # [23:20] reg_ddrc_addrmap_row_b14 = 0x6
            # [27:24] reg_ddrc_addrmap_row_b15 = 0xf
            w.maskwrite(0xF8006044, 0x0FFFFFFF, 0x0F666666)

            # DRAM_ODT_REG
            # [2:0] reg_ddrc_rank0_rd_odt = 0x0 (Version: 1/2)
            # [2:0] reserved_reg_ddrc_rank0_rd_odt = 0x0 (Version: 3)
            # [5:3] reg_ddrc_rank0_wr_odt = 0x1 (Version: 1/2)
            # [5:3] reserved_reg_ddrc_rank0_wr_odt = 0x1 (Version: 3)
            # [8:6] reg_ddrc_rank1_rd_odt = 0x1 (Version: 1/2)
            # [11:9] reg_ddrc_rank1_wr_odt = 0x1 (Version: 1/2)
            # [13:12] reg_phy_rd_local_odt = 0x0
            # [15:14] reg_phy_wr_local_odt = 0x3
            # [17:16] reg_phy_idle_local_odt = 0x3
            # [20:18] reg_ddrc_rank2_rd_odt = 0x0 (Version: 1/2)
            # [23:21] reg_ddrc_rank2_wr_odt = 0x0 (Version: 1/2)
            # [26:24] reg_ddrc_rank3_rd_odt = 0x0 (Version: 1/2)
            # [29:27] reg_ddrc_rank3_wr_odt = 0x0 (Version: 1/2)
            if self.version >= 3:
                w.maskwrite(0xF8006048, 0x0003F03F, 0x0003C008)
            else:
                w.maskwrite(0xF8006048, 0x3FFFFFFF, 0x0003C248)

            # PHY_CMD_TIMEOUT_RDDATA_CPT
            # [3:0] reg_phy_rd_cmd_to_data = 0x0
            # [7:4] reg_phy_wr_cmd_to_data = 0x0
            # [11:8] reg_phy_rdc_we_to_re_delay = 0x8
            # [15:15] reg_phy_rdc_fifo_rst_disable = 0x0
            # [16:16] reg_phy_use_fixed_re = 0x1
            # [17:17] reg_phy_rdc_fifo_rst_err_cnt_clr = 0x0
            # [18:18] reg_phy_dis_phy_ctrl_rstn = 0x0
            # [19:19] reg_phy_clk_stall_level = 0x0
            # [27:24] reg_phy_gatelvl_num_of_dq0 = 0x7
            # [31:28] reg_phy_wrlvl_num_of_dq0 = 0x7
            w.maskwrite(0xF8006050, 0xFF0F8FFF, 0x77010800)

            # DLL_CALIB
            # [7:0] reg_ddrc_dll_calib_to_min_x1024 = 0x1 (Version: 1/2)
            # [15:8] reg_ddrc_dll_calib_to_max_x1024 = 0x1 (Version: 1/2)
            # [16:16] reg_ddrc_dis_dll_calib = 0x0
            if self.version >= 3:
                w.maskwrite(0xF8006058, 0x00010000, 0x00000000)
            else:
                w.maskwrite(0xF8006058, 0x0001FFFF, 0x00000101)

            # ODT_DELAY_HOLD
            # [3:0] reg_ddrc_rd_odt_delay = 0x3
            # [7:4] reg_ddrc_wr_odt_delay = 0x0
            # [11:8] reg_ddrc_rd_odt_hold = 0x0
            # [15:12] reg_ddrc_wr_odt_hold
            w.maskwrite(0xF800605C, 0x0000FFFF,
                        0x00000003 |
                        (self.config.get_ddrc_wr_odt_hold() << 12))

            # CTRL_REG1
            # [0:0] reg_ddrc_pageclose = 0x0
            # [6:1] reg_ddrc_lpr_num_entries = 0x1f
            # [7:7] reg_ddrc_auto_pre_en = 0x0
            # [8:8] reg_ddrc_refresh_update_level = 0x0
            # [9:9] reg_ddrc_dis_wc = 0x0
            # [10:10] reg_ddrc_dis_collision_page_opt = 0x0
            # [12:12] reg_ddrc_selfref_en = 0x0
            w.maskwrite(0xF8006060, 0x000017FF,
                        0x00000000 |
                        (self.config.get_ddrc_lpr_num_entries() << 1))

            # CTRL_REG2
            # [12:5] reg_ddrc_go2critical_hysteresis = 0x0
            # [17:17] reg_arb_go2critical_en = 0x1
            w.maskwrite(0xF8006064, 0x00021FE0, 0x00020000)

            # CTRL_REG3
            # [7:0] reg_ddrc_wrlvl_ww
            # [15:8] reg_ddrc_rdlvl_rr
            # [25:16] reg_ddrc_dfi_t_wlmrd = 0x28
            w.maskwrite(0xF8006068, 0x03FFFFFF,
                        0x00280000 |
                        self.config.get_ddrc_wrlvl_ww() |
                        (self.config.get_ddrc_rdlvl_rr() << 8))

            # CTRL_REG4
            # [7:0] dfi_t_ctrlupd_interval_min_x1024 = 0x10
            # [15:8] dfi_t_ctrlupd_interval_max_x1024 = 0x16
            w.maskwrite(0xF800606C, 0x0000FFFF, 0x00001610)

            if self.version > 1:
                # CTRL_REG5
                # [3:0] reg_ddrc_dfi_t_ctrl_delay = 0x1
                # [7:4] reg_ddrc_dfi_t_dram_clk_disable = 0x1
                # [11:8] reg_ddrc_dfi_t_dram_clk_enable = 0x1
                # [15:12] reg_ddrc_t_cksre
                # [19:16] reg_ddrc_t_cksrx
                # [25:20] reg_ddrc_t_ckesr = 0x4
                w.maskwrite(0xF8006078, 0x03FFFFFF,
                            0x00400111 |
                            (self.config.get_ddrc_t_cksre() << 12) |
                            (self.config.get_ddrc_t_cksrx() << 16))

                # CTRL_REG6
                # [3:0] reg_ddrc_t_ckpde = 0x2
                # [7:4] reg_ddrc_t_ckpdx = 0x2
                # [11:8] reg_ddrc_t_ckdpde = 0x2
                # [15:12] reg_ddrc_t_ckdpdx = 0x2
                # [19:16] reg_ddrc_t_ckcsx = 0x3
                w.maskwrite(0xF800607C, 0x000FFFFF, 0x00032222)

            if self.version < 3:
                # CHE_REFRESH_TIMER01
                # [11:0] refresh_timer0_start_value_x32 = 0x0
                # [23:12] refresh_timer1_start_value_x32 = 0x8
                w.maskwrite(0xF80060A0, 0x00FFFFFF, 0x00008000)

            # CHE_T_ZQ
            # [0:0] reg_ddrc_dis_auto_zq = 0x0
            # [1:1] reg_ddrc_ddr3 = 0x1
            # [11:2] reg_ddrc_t_mod = 0x200
            # [21:12] reg_ddrc_t_zq_long_nop = 0x200
            # [31:22] reg_ddrc_t_zq_short_nop = 0x40
            w.maskwrite(0xF80060A4, 0xFFFFFFFF, 0x10200802)

            # CHE_T_ZQ_SHORT_INTERVAL_REG
            # [19:0] t_zq_short_interval_x1024
            # [27:20] dram_rstn_x1024
            w.maskwrite(0xF80060A8, 0x0FFFFFFF,
                        self.config.get_t_zq_short_interval_x1024() |
                        (self.config.get_dram_rstn_x1024() << 20))

            # DEEP_PWRDWN_REG
            # [0:0] deeppowerdown_en = 0x0
            # [8:1] deeppowerdown_to_x1024
            w.maskwrite(0xF80060AC, 0x000001FF,
                        0x00000000 |
                        (self.config.get_deeppowerdown_to_x1024() << 1))

            # REG_2C
            # [11:0] dfi_wrlvl_max_x1024 = 0xfff
            # [23:12] dfi_rdlvl_max_x1024 = 0xfff
            # [24:24] ddrc_reg_twrlvl_max_error = 0x0
            # [25:25] ddrc_reg_trdlvl_max_error = 0x0
            # [26:26] reg_ddrc_dfi_wr_level_en = DDR_TRAIN_WRITE_LEVEL
            # [27:27] reg_ddrc_dfi_rd_dqs_gate_level = 0x1
            # [28:28] reg_ddrc_dfi_rd_data_eye_train = 0x1
            w.maskwrite(0xF80060B0, 0x1FFFFFFF, 0x1CFFFFFF)

            # REG_2D
            # [8:0] reg_ddrc_2t_delay = 0x0 (Version: 1/2)
            # [9:9] reg_ddrc_skip_ocd = 0x1
            # [10:10] reg_ddrc_dis_pre_bypass = 0x0 (Version: 1/2)
            if self.version >= 3:
                w.maskwrite(0xF80060B4, 0x00000200, 0x00000200)
            else:
                w.maskwrite(0xF80060B4, 0x000007FF, 0x00000200)

            # DFI_TIMING
            # [4:0] reg_ddrc_dfi_t_rddata_en
            # [14:5] reg_ddrc_dfi_t_ctrlup_min = 0x3
            # [24:15] reg_ddrc_dfi_t_ctrlup_max = 0x40
            w.maskwrite(0xF80060B8, 0x01FFFFFF,
                        0x00200060 |
                        self.config.get_ddrc_dfi_t_rddata_en())

            # CHE_ECC_CONTROL_REG_OFFSET
            # [0:0] Clear_Uncorrectable_DRAM_ECC_error = 0x0
            # [1:1] Clear_Correctable_DRAM_ECC_error = 0x0
            w.maskwrite(0xF80060C4, 0x00000003, 0x00000000)

            # CHE_CORR_ECC_LOG_REG_OFFSET
            # [0:0] CORR_ECC_LOG_VALID = 0x0
            # [7:1] ECC_CORRECTED_BIT_NUM = 0x0
            w.maskwrite(0xF80060C8, 0x000000FF, 0x00000000)

            # CHE_UNCORR_ECC_LOG_REG_OFFSET
            # [0:0] UNCORR_ECC_LOG_VALID = 0x0
            w.maskwrite(0xF80060DC, 0x00000001, 0x00000000)

            # CHE_ECC_STATS_REG_OFFSET
            # [15:8] STAT_NUM_CORR_ERR = 0x0
            # [7:0] STAT_NUM_UNCORR_ERR = 0x0
            w.maskwrite(0xF80060F0, 0x0000FFFF, 0x00000000)

            # ECC_SCRUB
            # [2:0] reg_ddrc_ecc_mode = 0x0
            # [3:3] reg_ddrc_dis_scrub = 0x1
            w.maskwrite(0xF80060F4, 0x0000000F, 0x00000008)

            # PHY_RCVR_ENABLE
            # [3:0] reg_phy_dif_on = 0x0
            # [7:4] reg_phy_dif_off = 0x0
            w.maskwrite(0xF8006114, 0x000000FF, 0x00000000)

            # PHY_CONFIG0
            # [0:0] reg_phy_data_slice_in_use = 0x1
            # [1:1] reg_phy_rdlvl_inc_mode = 0x0
            # [2:2] reg_phy_gatelvl_inc_mode = 0x0
            # [3:3] reg_phy_wrlvl_inc_mode = 0x0
            # [4:4] reg_phy_board_lpbk_tx = 0x0 (Version: 1/2)
            # [5:5] reg_phy_board_lpbk_rx = 0x0 (Version: 1/2)
            # [14:6] reg_phy_bist_shift_dq = 0x0
            # [23:15] reg_phy_bist_err_clr = 0x0
            # [30:24] reg_phy_dq_offset = 0x40
            if self.version >= 3:
                w.maskwrite(0xF8006118, 0x7FFFFFCF, 0x40000001)
            else:
                w.maskwrite(0xF8006118, 0x7FFFFFFF, 0x40000001)

            # PHY_CONFIG1
            # [0:0] reg_phy_data_slice_in_use = 0x1
            # [1:1] reg_phy_rdlvl_inc_mode = 0x0
            # [2:2] reg_phy_gatelvl_inc_mode = 0x0
            # [3:3] reg_phy_wrlvl_inc_mode = 0x0
            # [4:4] reg_phy_board_lpbk_tx = 0x0 (Version: 1/2)
            # [5:5] reg_phy_board_lpbk_rx = 0x0 (Version: 1/2)
            # [14:6] reg_phy_bist_shift_dq = 0x0
            # [23:15] reg_phy_bist_err_clr = 0x0
            # [30:24] reg_phy_dq_offset = 0x40
            if self.version >= 3:
                w.maskwrite(0xF800611C, 0x7FFFFFCF, 0x40000001)
            else:
                w.maskwrite(0xF800611C, 0x7FFFFFFF, 0x40000001)

            # PHY_CONFIG2
            # [0:0] reg_phy_data_slice_in_use = 0x1
            # [1:1] reg_phy_rdlvl_inc_mode = 0x0
            # [2:2] reg_phy_gatelvl_inc_mode = 0x0
            # [3:3] reg_phy_wrlvl_inc_mode = 0x0
            # [4:4] reg_phy_board_lpbk_tx = 0x0 (Version: 1/2)
            # [5:5] reg_phy_board_lpbk_rx = 0x0 (Version: 1/2)
            # [14:6] reg_phy_bist_shift_dq = 0x0
            # [23:15] reg_phy_bist_err_clr = 0x0
            # [30:24] reg_phy_dq_offset = 0x40
            if self.version >= 3:
                w.maskwrite(0xF8006120, 0x7FFFFFCF, 0x40000001)
            else:
                w.maskwrite(0xF8006120, 0x7FFFFFFF, 0x40000001)

            # PHY_CONFIG3
            # [0:0] reg_phy_data_slice_in_use = 0x1
            # [1:1] reg_phy_rdlvl_inc_mode = 0x0
            # [2:2] reg_phy_gatelvl_inc_mode = 0x0
            # [3:3] reg_phy_wrlvl_inc_mode = 0x0
            # [4:4] reg_phy_board_lpbk_tx = 0x0 (Version: 1/2)
            # [5:5] reg_phy_board_lpbk_rx = 0x0 (Version: 1/2)
            # [14:6] reg_phy_bist_shift_dq = 0x0
            # [23:15] reg_phy_bist_err_clr = 0x0
            # [30:24] reg_phy_dq_offset = 0x40
            if self.version >= 3:
                w.maskwrite(0xF8006124, 0x7FFFFFCF, 0x40000001)
            else:
                w.maskwrite(0xF8006124, 0x7FFFFFFF, 0x40000001)

            # PHY_INIT_RATIO0
            # [9:0] reg_phy_wrlvl_init_ratio
            # [19:10] reg_phy_gatelvl_init_ratio
            w.maskwrite(0xF800612C, 0x000FFFFF,
                        self.config.get_wrlvl_init_ratio(0) |
                        (self.config.get_gatelvl_init_ratio(0) << 10))

            # PHY_INIT_RATIO1
            # [9:0] reg_phy_wrlvl_init_ratio
            # [19:10] reg_phy_gatelvl_init_ratio
            w.maskwrite(0xF8006130, 0x000FFFFF,
                        self.config.get_wrlvl_init_ratio(1) |
                        (self.config.get_gatelvl_init_ratio(1) << 10))

            # PHY_INIT_RATIO2
            # [9:0] reg_phy_wrlvl_init_ratio
            # [19:10] reg_phy_gatelvl_init_ratio
            w.maskwrite(0xF8006134, 0x000FFFFF,
                        self.config.get_wrlvl_init_ratio(2) |
                        (self.config.get_gatelvl_init_ratio(2) << 10))

            # PHY_INIT_RATIO3
            # [9:0] reg_phy_wrlvl_init_ratio
            # [19:10] reg_phy_gatelvl_init_ratio
            w.maskwrite(0xF8006138, 0x000FFFFF,
                        self.config.get_wrlvl_init_ratio(3) |
                        (self.config.get_gatelvl_init_ratio(3) << 10))

            # PHY_RD_DQS_CFG0
            # [9:0] reg_phy_rd_dqs_slave_ratio = 0x35
            # [10:10] reg_phy_rd_dqs_slave_force = 0x0
            # [19:11] reg_phy_rd_dqs_slave_delay = 0x0
            w.maskwrite(0xF8006140, 0x000FFFFF, 0x00000035)

            # PHY_RD_DQS_CFG1
            # [9:0] reg_phy_rd_dqs_slave_ratio = 0x35
            # [10:10] reg_phy_rd_dqs_slave_force = 0x0
            # [19:11] reg_phy_rd_dqs_slave_delay = 0x0
            w.maskwrite(0xF8006144, 0x000FFFFF, 0x00000035)

            # PHY_RD_DQS_CFG2
            # [9:0] reg_phy_rd_dqs_slave_ratio = 0x35
            # [10:10] reg_phy_rd_dqs_slave_force = 0x0
            # [19:11] reg_phy_rd_dqs_slave_delay = 0x0
            w.maskwrite(0xF8006148, 0x000FFFFF, 0x00000035)

            # PHY_RD_DQS_CFG3
            # [9:0] reg_phy_rd_dqs_slave_ratio = 0x35
            # [10:10] reg_phy_rd_dqs_slave_force = 0x0
            # [19:11] reg_phy_rd_dqs_slave_delay = 0x0
            w.maskwrite(0xF800614C, 0x000FFFFF, 0x00000035)

            # PHY_WR_DQS_CFG0
            # [9:0] reg_phy_wr_dqs_slave_ratio
            # [10:10] reg_phy_wr_dqs_slave_force = 0x0
            # [19:11] reg_phy_wr_dqs_slave_delay = 0x0
            w.maskwrite(0xF8006154, 0x000FFFFF,
                        0x00000000 |
                        self.config.get_wr_dqs_slave_ratio(0))

            # PHY_WR_DQS_CFG1
            # [9:0] reg_phy_wr_dqs_slave_ratio
            # [10:10] reg_phy_wr_dqs_slave_force = 0x0
            # [19:11] reg_phy_wr_dqs_slave_delay = 0x0
            w.maskwrite(0xF8006158, 0x000FFFFF,
                        0x00000000 |
                        self.config.get_wr_dqs_slave_ratio(1))

            # PHY_WR_DQS_CFG2
            # [9:0] reg_phy_wr_dqs_slave_ratio
            # [10:10] reg_phy_wr_dqs_slave_force = 0x0
            # [19:11] reg_phy_wr_dqs_slave_delay = 0x0
            w.maskwrite(0xF800615C, 0x000FFFFF,
                        0x00000000 |
                        self.config.get_wr_dqs_slave_ratio(2))

            # PHY_WR_DQS_CFG3
            # [9:0] reg_phy_wr_dqs_slave_ratio
            # [10:10] reg_phy_wr_dqs_slave_force = 0x0
            # [19:11] reg_phy_wr_dqs_slave_delay = 0x0
            w.maskwrite(0xF8006160, 0x000FFFFF,
                        0x00000000 |
                        self.config.get_wr_dqs_slave_ratio(3))

            # PHY_WE_DQS_CFG0
            # [10:0] reg_phy_fifo_we_slave_ratio
            # [11:11] reg_phy_fifo_we_in_force = 0x0
            # [20:12] reg_phy_fifo_we_in_delay = 0x0
            w.maskwrite(0xF8006168, 0x001FFFFF,
                        0x00000000 |
                        self.config.get_fifo_we_slave_ratio(0))

            # PHY_WE_DQS_CFG1
            # [10:0] reg_phy_fifo_we_slave_ratio
            # [11:11] reg_phy_fifo_we_in_force = 0x0
            # [20:12] reg_phy_fifo_we_in_delay = 0x0
            w.maskwrite(0xF800616C, 0x001FFFFF,
                        0x00000000 |
                        self.config.get_fifo_we_slave_ratio(1))

            # PHY_WE_DQS_CFG2
            # [10:0] reg_phy_fifo_we_slave_ratio
            # [11:11] reg_phy_fifo_we_in_force = 0x0
            # [20:12] reg_phy_fifo_we_in_delay = 0x0
            w.maskwrite(0xF8006170, 0x001FFFFF,
                        0x00000000 |
                        self.config.get_fifo_we_slave_ratio(2))

            # PHY_WE_DQS_CFG3
            # [10:0] reg_phy_fifo_we_slave_ratio
            # [11:11] reg_phy_fifo_we_in_force = 0x0
            # [20:12] reg_phy_fifo_we_in_delay = 0x0
            w.maskwrite(0xF8006174, 0x001FFFFF,
                        0x00000000 |
                        self.config.get_fifo_we_slave_ratio(3))

            # WR_DATA_SLV0
            # [9:0] reg_phy_wr_data_slave_ratio
            # [10:10] reg_phy_wr_data_slave_force = 0x0
            # [19:11] reg_phy_wr_data_slave_delay = 0x0
            w.maskwrite(0xF800617C, 0x000FFFFF,
                        0x00000000 |
                        self.config.get_wr_data_slave_ratio(0))

            # WR_DATA_SLV1
            # [9:0] reg_phy_wr_data_slave_ratio
            # [10:10] reg_phy_wr_data_slave_force = 0x0
            # [19:11] reg_phy_wr_data_slave_delay = 0x0
            w.maskwrite(0xF8006180, 0x000FFFFF,
                        0x00000000 |
                        self.config.get_wr_data_slave_ratio(1))

            # WR_DATA_SLV2
            # [9:0] reg_phy_wr_data_slave_ratio
            # [10:10] reg_phy_wr_data_slave_force = 0x0
            # [19:11] reg_phy_wr_data_slave_delay = 0x0
            w.maskwrite(0xF8006184, 0x000FFFFF,
                        0x00000000 |
                        self.config.get_wr_data_slave_ratio(2))

            # WR_DATA_SLV3
            # [9:0] reg_phy_wr_data_slave_ratio
            # [10:10] reg_phy_wr_data_slave_force = 0x0
            # [19:11] reg_phy_wr_data_slave_delay = 0x0
            w.maskwrite(0xF8006188, 0x000FFFFF,
                        0x00000000 |
                        self.config.get_wr_data_slave_ratio(3))

            # REG_64
            # [0:0] reg_phy_loopback = 0x0 (Version: 1/2)
            # [1:1] reg_phy_bl2 = 0x0
            # [2:2] reg_phy_at_spd_atpg = 0x0
            # [3:3] reg_phy_bist_enable = 0x0
            # [4:4] reg_phy_bist_force_err = 0x0
            # [6:5] reg_phy_bist_mode = 0x0
            # [7:7] reg_phy_invert_clkout = 0x1
            # [8:8] reg_phy_all_dq_mpr_rd_resp = 0x0 (Version: 1/2)
            # [9:9] reg_phy_sel_logic = 0x0
            # [19:10] reg_phy_ctrl_slave_ratio = 0x100
            # [20:20] reg_phy_ctrl_slave_force = 0x0
            # [27:21] reg_phy_ctrl_slave_delay = 0x0
            # [28:28] reg_phy_use_rank0_delays = 0x1 (Version: 1/2)
            # [29:29] reg_phy_lpddr = 0x0
            # [30:30] reg_phy_cmd_latency = 0x0
            # [31:31] reg_phy_int_lpbk = 0x0 (Version: 1/2)
            if self.version >= 3:
                w.maskwrite(0xF8006190, 0x6FFFFEFE, 0x00040080)
            else:
                w.maskwrite(0xF8006190, 0xFFFFFFFF, 0x10040080)

            # REG_65
            # [4:0] reg_phy_wr_rl_delay
            # [9:5] reg_phy_rd_rl_delay
            # [13:10] reg_phy_dll_lock_diff = 0xf
            # [14:14] reg_phy_use_wr_level = 0x1
            # [15:15] reg_phy_use_rd_dqs_gate_level = 0x1
            # [16:16] reg_phy_use_rd_data_eye_level = 0x1
            # [17:17] reg_phy_dis_calib_rst = 0x0
            # [19:18] reg_phy_ctrl_slave_delay = 0x0
            w.maskwrite(0xF8006194, 0x000FFFFF,
                        0x0001FC00 |
                        self.config.get_phy_wr_rl_delay() |
                        (self.config.get_phy_rd_rl_delay() << 5))

            # PAGE_MASK
            # [31:0] reg_arb_page_addr_mask = 0x0
            w.maskwrite(0xF8006204, 0xFFFFFFFF, 0x00000000)

            # AXI_PRIORITY_WR_PORT0
            # [9:0] reg_arb_pri_wr_portn
            # [16:16] reg_arb_disable_aging_wr_portn = 0x0
            # [17:17] reg_arb_disable_urgent_wr_portn = 0x0
            # [18:18] reg_arb_dis_page_match_wr_portn = 0x0
            # [19:19] reg_arb_dis_rmw_portn = 0x1 (Version: 1/2)
            pri = self.config.get_arb_pri_wr_portn(0)
            if self.version >= 3:
                w.maskwrite(0xF8006208, 0x000703FF, 0x00000000 | pri)
            else:
                w.maskwrite(0xF8006208, 0x000F03FF, 0x00080000 | pri)

            # AXI_PRIORITY_WR_PORT1
            # [9:0] reg_arb_pri_wr_portn
            # [16:16] reg_arb_disable_aging_wr_portn = 0x0
            # [17:17] reg_arb_disable_urgent_wr_portn = 0x0
            # [18:18] reg_arb_dis_page_match_wr_portn = 0x0
            # [19:19] reg_arb_dis_rmw_portn = 0x1 (Version: 1/2)
            pri = self.config.get_arb_pri_wr_portn(1)
            if self.version >= 3:
                w.maskwrite(0xF800620C, 0x000703FF, 0x00000000 | pri)
            else:
                w.maskwrite(0xF800620C, 0x000F03FF, 0x00080000 | pri)

            # AXI_PRIORITY_WR_PORT2
            # [9:0] reg_arb_pri_wr_portn
            # [16:16] reg_arb_disable_aging_wr_portn = 0x0
            # [17:17] reg_arb_disable_urgent_wr_portn = 0x0
            # [18:18] reg_arb_dis_page_match_wr_portn = 0x0
            # [19:19] reg_arb_dis_rmw_portn = 0x1 (Version: 1/2)
            pri = self.config.get_arb_pri_wr_portn(2)
            if self.version >= 3:
                w.maskwrite(0xF8006210, 0x000703FF, 0x00000000 | pri)
            else:
                w.maskwrite(0xF8006210, 0x000F03FF, 0x00080000 | pri)

            # AXI_PRIORITY_WR_PORT3
            # [9:0] reg_arb_pri_wr_portn
            # [16:16] reg_arb_disable_aging_wr_portn = 0x0
            # [17:17] reg_arb_disable_urgent_wr_portn = 0x0
            # [18:18] reg_arb_dis_page_match_wr_portn = 0x0
            # [19:19] reg_arb_dis_rmw_portn = 0x1 (Version: 1/2)
            pri = self.config.get_arb_pri_wr_portn(3)
            if self.version >= 3:
                w.maskwrite(0xF8006214, 0x000703FF, 0x00000000 | pri)
            else:
                w.maskwrite(0xF8006214, 0x000F03FF, 0x00080000 | pri)

            # AXI_PRIORITY_RD_PORT0
            # [9:0] reg_arb_pri_rd_portn
            # [16:16] reg_arb_disable_aging_rd_portn = 0x0
            # [17:17] reg_arb_disable_urgent_rd_portn = 0x0
            # [18:18] reg_arb_dis_page_match_rd_portn = 0x0
            # [19:19] reg_arb_set_hpr_rd_portn = 0x0
            pri = self.config.get_arb_pri_rd_portn(0)
            w.maskwrite(0xF8006218, 0x000F03FF,
                        0x00000000 | pri | (self.config.DDR_PORT0_HPR_ENABLE << 19))

            # AXI_PRIORITY_RD_PORT1
            # [9:0] reg_arb_pri_rd_portn
            # [16:16] reg_arb_disable_aging_rd_portn = 0x0
            # [17:17] reg_arb_disable_urgent_rd_portn = 0x0
            # [18:18] reg_arb_dis_page_match_rd_portn = 0x0
            # [19:19] reg_arb_set_hpr_rd_portn = 0x0
            pri = self.config.get_arb_pri_rd_portn(1)
            w.maskwrite(0xF800621C, 0x000F03FF,
                        0x00000000 | pri | (self.config.DDR_PORT1_HPR_ENABLE << 19))

            # AXI_PRIORITY_RD_PORT2
            # [9:0] reg_arb_pri_rd_portn
            # [16:16] reg_arb_disable_aging_rd_portn = 0x0
            # [17:17] reg_arb_disable_urgent_rd_portn = 0x0
            # [18:18] reg_arb_dis_page_match_rd_portn = 0x0
            # [19:19] reg_arb_set_hpr_rd_portn = 0x0
            pri = self.config.get_arb_pri_rd_portn(2)
            w.maskwrite(0xF8006220, 0x000F03FF,
                        0x00000000 | pri | (self.config.DDR_PORT2_HPR_ENABLE << 19))

            # AXI_PRIORITY_RD_PORT3
            # [9:0] reg_arb_pri_rd_portn
            # [16:16] reg_arb_disable_aging_rd_portn = 0x0
            # [17:17] reg_arb_disable_urgent_rd_portn = 0x0
            # [18:18] reg_arb_dis_page_match_rd_portn = 0x0
            # [19:19] reg_arb_set_hpr_rd_portn = 0x0
            pri = self.config.get_arb_pri_rd_portn(3)
            w.maskwrite(0xF8006224, 0x000F03FF,
                        0x00000000 | pri | (self.config.DDR_PORT3_HPR_ENABLE << 19))

            # LPDDR_CTRL0
            # [0:0] reg_ddrc_lpddr2 = 0x0
            # [1:1] reg_ddrc_per_bank_refresh = 0x0 (Version: 1/2)
            # [2:2] reg_ddrc_derate_enable = 0x0
            # [11:4] reg_ddrc_mr4_margin = 0x0
            if self.version >= 3:
                w.maskwrite(0xF80062A8, 0x00000FF5, 0x00000000)
            else:
                w.maskwrite(0xF80062A8, 0x00000FF7, 0x00000000)

            # LPDDR_CTRL1
            # [31:0] reg_ddrc_mr4_read_interval = 0x0
            w.maskwrite(0xF80062AC, 0xFFFFFFFF, 0x00000000)

            # LPDDR_CTRL2
            # [3:0] reg_ddrc_min_stable_clock_x1 = 0x5
            # [11:4] reg_ddrc_idle_after_reset_x32
            # [21:12] reg_ddrc_t_mrw = 0x5
            w.maskwrite(0xF80062B0, 0x003FFFFF,
                        0x00005005 |
                        (self.config.get_ddrc_idle_after_reset_x32() << 4))

            # LPDDR_CTRL3
            # [7:0] reg_ddrc_max_auto_init_x1024
            # [17:8] reg_ddrc_dev_zqinit_x32
            w.maskwrite(0xF80062B4, 0x0003FFFF,
                        self.config.get_ddrc_max_auto_init_x1024() |
                        (self.config.get_ddrc_dev_zqinit_x32() << 8))

            # DDRIOB_DCI_STATUS
            # [13:13] DONE = 1
            w.maskpoll(0xF8000B74, 0x00002000)

            # DDRC_CTRL
            # [0:0] reg_ddrc_soft_rstb = 0x1
            # [1:1] reg_ddrc_powerdown_en = 0x0
            # [3:2] reg_ddrc_data_bus_width = 0x0
            # [6:4] reg_ddrc_burst8_refresh = 0x0
            # [13:7] reg_ddrc_rdwr_idle_gap = 1
            # [14:14] reg_ddrc_dis_rd_bypass = 0x0
            # [15:15] reg_ddrc_dis_act_bypass = 0x0
            # [16:16] reg_ddrc_dis_auto_refresh = 0x0
            w.maskwrite(0xF8006000, 0x0001FFFF, 0x00000081)

            # MODE_STS_REG
            # [2:0] ddrc_reg_operating_mode = 1
            w.maskpoll(0xF8006054, 0x00000007)

    def mio_init(self):
        with self.array_writer("ps7_mio_init_data") as w:
            w.unlock()
            # START: OCM REMAPPING
            # [0:0] VREF_EN = 0x1
            # [1:1] VREF_PULLUP_EN = 0x0 (Version: 1/2)
            # [6:4] VREF_SEL = 0x0 (Version: 3)
            # [8:8] CLK_PULLUP_EN = 0x0 (Version: 1/2)
            # [9:9] SRSTN_PULLUP_EN = 0x0 (Version: 1/2)
            if self.version >= 3:
                w.maskwrite(0xF8000B00, 0x00000071, 0x00000001)
            else:
                w.maskwrite(0xF8000B00, 0x00000303, 0x00000001)
            # FINISH: OCM REMAPPING
            # START: DDRIOB SETTINGS
            # [0:0] INP_POWER = 0x0 (Version: 1/2)
            # [0:0] reserved_INP_POWER = 0x0 (Version: 3)
            # [2:1] INP_TYPE = 0x0
            # [3:3] DCI_UPDATE_B = 0x0
            # [4:4] TERM_EN = 0x0
            # [6:5] DCI_TYPE = 0x0
            # [7:7] IBUF_DISABLE_MODE = 0x0
            # [8:8] TERM_DISABLE_MODE = 0x0
            # [10:9] OUTPUT_EN = 0x3
            # [11:11] PULLUP_EN = 0x0
            w.maskwrite(0xF8000B40, 0x00000FFF, 0x00000600)
            # [0:0] INP_POWER = 0x0 (Version: 1/2)
            # [0:0] reserved_INP_POWER = 0x0 (Version: 3)
            # [2:1] INP_TYPE = 0x0
            # [3:3] DCI_UPDATE_B = 0x0
            # [4:4] TERM_EN = 0x0
            # [6:5] DCI_TYPE = 0x0
            # [7:7] IBUF_DISABLE_MODE = 0x0
            # [8:8] TERM_DISABLE_MODE = 0x0
            # [10:9] OUTPUT_EN = 0x3
            # [11:11] PULLUP_EN = 0x0
            w.maskwrite(0xF8000B44, 0x00000FFF, 0x00000600)
            # [0:0] INP_POWER = 0x0 (Version: 1/2)
            # [0:0] reserved_INP_POWER = 0x0 (Version: 3)
            # [2:1] INP_TYPE = 0x1
            # [3:3] DCI_UPDATE_B = 0x0
            # [4:4] TERM_EN = 0x1
            # [6:5] DCI_TYPE = 0x3
            # [7:7] IBUF_DISABLE_MODE = 0
            # [8:8] TERM_DISABLE_MODE = 0
            # [10:9] OUTPUT_EN = 0x3
            # [11:11] PULLUP_EN = 0x0
            w.maskwrite(0xF8000B48, 0x00000FFF, 0x00000672)
            # [0:0] INP_POWER = 0x0 (Version: 1/2)
            # [0:0] reserved_INP_POWER = 0x0 (Version: 3)
            # [2:1] INP_TYPE = 0x1
            # [3:3] DCI_UPDATE_B = 0x0
            # [4:4] TERM_EN = 0x1
            # [6:5] DCI_TYPE = 0x3
            # [7:7] IBUF_DISABLE_MODE = 0
            # [8:8] TERM_DISABLE_MODE = 0
            # [10:9] OUTPUT_EN = 0x3
            # [11:11] PULLUP_EN = 0x0
            w.maskwrite(0xF8000B4C, 0x00000FFF, 0x00000672)
            # [0:0] INP_POWER = 0x0 (Version: 1/2)
            # [0:0] reserved_INP_POWER = 0x0 (Version: 3)
            # [2:1] INP_TYPE = 0x2
            # [3:3] DCI_UPDATE_B = 0x0
            # [4:4] TERM_EN = 0x1
            # [6:5] DCI_TYPE = 0x3
            # [7:7] IBUF_DISABLE_MODE = 0
            # [8:8] TERM_DISABLE_MODE = 0
            # [10:9] OUTPUT_EN = 0x3
            # [11:11] PULLUP_EN = 0x0
            w.maskwrite(0xF8000B50, 0x00000FFF, 0x00000674)
            # [0:0] INP_POWER = 0x0 (Version: 1/2)
            # [0:0] reserved_INP_POWER = 0x0 (Version: 3)
            # [2:1] INP_TYPE = 0x2
            # [3:3] DCI_UPDATE_B = 0x0
            # [4:4] TERM_EN = 0x1
            # [6:5] DCI_TYPE = 0x3
            # [7:7] IBUF_DISABLE_MODE = 0
            # [8:8] TERM_DISABLE_MODE = 0
            # [10:9] OUTPUT_EN = 0x3
            # [11:11] PULLUP_EN = 0x0
            w.maskwrite(0xF8000B54, 0x00000FFF, 0x00000674)
            # [0:0] INP_POWER = 0x0 (Version: 1/2)
            # [0:0] reserved_INP_POWER = 0x0 (Version: 3)
            # [2:1] INP_TYPE = 0x0
            # [3:3] DCI_UPDATE_B = 0x0
            # [4:4] TERM_EN = 0x0
            # [6:5] DCI_TYPE = 0x0
            # [7:7] IBUF_DISABLE_MODE = 0x0
            # [8:8] TERM_DISABLE_MODE = 0x0
            # [10:9] OUTPUT_EN = 0x3
            # [11:11] PULLUP_EN = 0x0
            w.maskwrite(0xF8000B58, 0x00000FFF, 0x00000600)
            # [6:0] DRIVE_P = 0x1c (Version: 1/2)
            # [6:0] reserved_DRIVE_P = 0x1c (Version: 3)
            # [13:7] DRIVE_N = 0xc (Version: 1/2)
            # [13:7] reserved_DRIVE_N = 0xc (Version: 3)
            # [18:14] SLEW_P = 0x3 (Version: 1/2)
            # [18:14] reserved_SLEW_P = 0x3 (Version: 3)
            # [23:19] SLEW_N = 0x3 (Version: 1/2)
            # [23:19] reserved_SLEW_N = 0x3 (Version: 3)
            # [26:24] GTL = 0x0 (Version: 1/2)
            # [26:24] reserved_GTL = 0x0 (Version: 3)
            # [31:27] RTERM = 0x0 (Version: 1/2)
            # [31:27] reserved_RTERM = 0x0 (Version: 3)
            w.maskwrite(0xF8000B5C, 0xFFFFFFFF, 0x0018C61C)
            # [6:0] DRIVE_P = 0x1c (Version: 1/2)
            # [6:0] reserved_DRIVE_P = 0x1c (Version: 3)
            # [13:7] DRIVE_N = 0xc (Version: 1/2)
            # [13:7] reserved_DRIVE_N = 0xc (Version: 3)
            # [18:14] SLEW_P = 0x6 (Version: 1/2)
            # [18:14] reserved_SLEW_P = 0x6 (Version: 3)
            # [23:19] SLEW_N = 0x1f (Version: 1/2)
            # [23:19] reserved_SLEW_N = 0x1f (Version: 3)
            # [26:24] GTL = 0x0 (Version: 1/2)
            # [26:24] reserved_GTL = 0x0 (Version: 3)
            # [31:27] RTERM = 0x0 (Version: 1/2)
            # [31:27] reserved_RTERM = 0x0 (Version: 3)
            w.maskwrite(0xF8000B60, 0xFFFFFFFF, 0x00F9861C)
            # [6:0] DRIVE_P = 0x1c (Version: 1/2)
            # [6:0] reserved_DRIVE_P = 0x1c (Version: 3)
            # [13:7] DRIVE_N = 0xc (Version: 1/2)
            # [13:7] reserved_DRIVE_N = 0xc (Version: 3)
            # [18:14] SLEW_P = 0x6 (Version: 1/2)
            # [18:14] reserved_SLEW_P = 0x6 (Version: 3)
            # [23:19] SLEW_N = 0x1f (Version: 1/2)
            # [23:19] reserved_SLEW_N = 0x1f (Version: 3)
            # [26:24] GTL = 0x0 (Version: 1/2)
            # [26:24] reserved_GTL = 0x0 (Version: 3)
            # [31:27] RTERM = 0x0 (Version: 1/2)
            # [31:27] reserved_RTERM = 0x0 (Version: 3)
            w.maskwrite(0xF8000B64, 0xFFFFFFFF, 0x00F9861C)
            # [6:0] DRIVE_P = 0x1c (Version: 1/2)
            # [6:0] reserved_DRIVE_P = 0x1c (Version: 3)
            # [13:7] DRIVE_N = 0xc (Version: 1/2)
            # [13:7] reserved_DRIVE_N = 0xc (Version: 3)
            # [18:14] SLEW_P = 0x6 (Version: 1/2)
            # [18:14] reserved_SLEW_P = 0x6 (Version: 3)
            # [23:19] SLEW_N = 0x1f (Version: 1/2)
            # [23:19] reserved_SLEW_N = 0x1f (Version: 3)
            # [26:24] GTL = 0x0 (Version: 1/2)
            # [26:24] reserved_GTL = 0x0 (Version: 3)
            # [31:27] RTERM = 0x0 (Version: 1/2)
            # [31:27] reserved_RTERM = 0x0 (Version: 3)
            w.maskwrite(0xF8000B68, 0xFFFFFFFF, 0x00F9861C)
            # [0:0] VREF_INT_EN = 0x1
            # [4:1] VREF_SEL = 0x4
            # [6:5] VREF_EXT_EN = 0x0
            # [8:7] VREF_PULLUP_EN = 0x0 (Version: 1/2)
            # [8:7] reserved_VREF_PULLUP_EN = 0x0 (Version: 3)
            # [9:9] REFIO_EN = 0x1
            # REFIO_TEST = 0x0 (Version: 2)
            # [11:10] reserved_REFIO_TEST = 0x0 (Version: 3)
            # [12:12] REFIO_PULLUP_EN = 0x0 (Version: 1/2)
            # [12:12] reserved_REFIO_PULLUP_EN = 0x0 (Version: 3)
            # [13:13] DRST_B_PULLUP_EN = 0x0 (Version: 1/2)
            # [13:13] reserved_DRST_B_PULLUP_EN = 0x0 (Version: 3)
            # [14:14] CKE_PULLUP_EN = 0x0 (Version: 1/2)
            # [14:14] reserved_CKE_PULLUP_EN = 0x0 (Version: 3)
            if self.version == 1:
                w.maskwrite(0xF8000B6C, 0x000073FF, 0x00000209)
            else:
                w.maskwrite(0xF8000B6C, 0x00007FFF, 0x00000209)
            # .. START: ASSERT RESET
            # [0:0] RESET = 1
            # [5:5] VRN_OUT = 0x1 (Version: 1/2)
            if self.version >= 3:
                w.maskwrite(0xF8000B70, 0x00000001, 0x00000001)
            else:
                w.maskwrite(0xF8000B70, 0x00000021, 0x00000021)
            # .. FINISH: ASSERT RESET
            # .. START: DEASSERT RESET
            # [0:0] RESET = 0
            # [5:5] VRN_OUT = 0x1 (Version: 1/2)
            # [5:5] reserved_VRN_OUT = 0x1 (Version: 3)
            w.maskwrite(0xF8000B70, 0x00000021, 0x00000020)
            # .. FINISH: DEASSERT RESET
            # [0:0] RESET = 0x1
            # [1:1] ENABLE = 0x1
            # [2:2] VRP_TRI = 0x0 (Version: 1/2)
            # [2:2] reserved_VRP_TRI = 0x0 (Version: 3)
            # [3:3] VRN_TRI = 0x0 (Version: 1/2)
            # [3:3] reserved_VRN_TRI = 0x0 (Version: 3)
            # [4:4] VRP_OUT = 0x0 (Version: 1/2)
            # [4:4] reserved_VRP_OUT = 0x0 (Version: 3)
            # [5:5] VRN_OUT = 0x1 (Version: 1/2)
            # [5:5] reserved_VRN_OUT = 0x1 (Version: 3)
            # [7:6] NREF_OPT1 = 0x0
            # [10:8] NREF_OPT2 = 0x0
            # [13:11] NREF_OPT4 = 0x1
            # [16:14] PREF_OPT1 = 0x0 (Version: 1/2)
            # [15:14] PREF_OPT1 = 0x0 (Version: 3)
            # [19:17] PREF_OPT2 = 0x0
            # [20:20] UPDATE_CONTROL = 0x0
            # [21:21] INIT_COMPLETE = 0x0 (Version: 1/2)
            # [21:21] reserved_INIT_COMPLETE = 0x0 (Version: 3)
            # [22:22] TST_CLK = 0x0 (Version: 1/2)
            # [22:22] reserved_TST_CLK = 0x0 (Version: 3)
            # [23:23] TST_HLN = 0x0 (Version: 1/2)
            # [23:23] reserved_TST_HLN = 0x0 (Version: 3)
            # [24:24] TST_HLP = 0x0 (Version: 1/2)
            # [24:24] reserved_TST_HLP = 0x0 (Version: 3)
            # [25:25] TST_RST = 0x0 (Version: 1/2)
            # [25:25] reserved_TST_RST = 0x0 (Version: 3)
            # [26:26] INT_DCI_EN = 0x0 (Version: 1/2)
            # [26:26] reserved_INT_DCI_EN = 0x0 (Version: 3)
            if self.version >= 3:
                w.maskwrite(0xF8000B70, 0x07FEFFFF, 0x00000823)
            else:
                w.maskwrite(0xF8000B70, 0x07FFFFFF, 0x00000823)
            # FINISH: DDRIOB SETTINGS
            # START: MIO PROGRAMMING
            for n in range(54):
                pin = self.config._MIO_PINS[n]
                if not pin.used:
                    continue
                w.maskwrite(0xF8000700 | (n * 4), 0x00003FFF, pin.get_reg())
            # [5:0] SDIO0_WP_SEL = 15
            # [21:16] SDIO0_CD_SEL = 0
            w.maskwrite(0xF8000830, 0x003F003F, 0x0000000F)
            # FINISH: MIO PROGRAMMING
            w.lock()

    def peripherals_init(self):
        with self.array_writer("ps7_peripherals_init_data") as w:
            w.unlock()
            # START: DDR TERM/IBUF_DISABLE_MODE SETTINGS
            # [7:7] IBUF_DISABLE_MODE = 0x1
            # [8:8] TERM_DISABLE_MODE = 0x1
            w.maskwrite(0xF8000B48, 0x00000180, 0x00000180)
            # [7:7] IBUF_DISABLE_MODE = 0x1
            # [8:8] TERM_DISABLE_MODE = 0x1
            w.maskwrite(0xF8000B4C, 0x00000180, 0x00000180)
            # [7:7] IBUF_DISABLE_MODE = 0x1
            # [8:8] TERM_DISABLE_MODE = 0x1
            w.maskwrite(0xF8000B50, 0x00000180, 0x00000180)
            # [7:7] IBUF_DISABLE_MODE = 0x1
            # [8:8] TERM_DISABLE_MODE = 0x1
            w.maskwrite(0xF8000B54, 0x00000180, 0x00000180)
            # FINISH: DDR TERM/IBUF_DISABLE_MODE SETTINGS
            w.lock()
            # START: SRAM/NOR SET OPMODE
            if self.config.NOR_PERIPHERAL_ENABLE:
                # XNANDPS_SET_OPMODE_OFFSET
                # [12:12] set_bls = 1
                w.maskwrite(0XE000E018, 0x00001000, 0x00001000)
            # FINISH: SRAM/NOR SET OPMODE
            # START: UART REGISTERS
            # [7:0] BDIV = 0x6
            w.maskwrite(0xE0001034, 0x000000FF, 0x00000006)
            # [15:0] CD = 0x3e
            w.maskwrite(0xE0001018, 0x0000FFFF, 0x0000003E)
            # [8:8] STPBRK = 0x0
            # [7:7] STTBRK = 0x0
            # [6:6] RSTTO = 0x0
            # [5:5] TXDIS = 0x0
            # [4:4] TXEN = 0x1
            # [3:3] RXDIS = 0x0
            # [2:2] RXEN = 0x1
            # [1:1] TXRES = 0x1
            # [0:0] RXRES = 0x1
            w.maskwrite(0xE0001000, 0x000001FF, 0x00000017)
            # [11:11] IRMODE = 0x0 (Version: 1/2)
            # [10:10] UCLKEN = 0x0 (Version: 1/2)
            # [9:8] CHMODE = 0x0
            # [7:6] NBSTOP = 0x0
            # [5:3] PAR = 0x4
            # [2:1] CHRL = 0x0
            # [0:0] CLKS = 0x0
            if self.version >= 3:
                w.maskwrite(0xE0001004, 0x000003FF, 0x00000020)
            else:
                w.maskwrite(0xE0001004, 0x00000FFF, 0x00000020)
            # FINISH: UART REGISTERS
            # START: QSPI REGISTERS
            # [19:19] Holdb_dr = 1
            w.maskwrite(0xE000D000, 0x00080000, 0x00080000)
            # FINISH: QSPI REGISTERS
            # START: PL POWER ON RESET REGISTERS
            # [29:29] PCFG_POR_CNT_4K = 0
            w.maskwrite(0xF8007000, 0x20000000, 0x00000000)
            # FINISH: PL POWER ON RESET REGISTERS
            # START: SMC TIMING CALCULATION REGISTER UPDATE
            if self.config.NAND_PERIPHERAL_ENABLE:
                # .. START: NAND SET CYCLE
                # XNANDPS_SET_CYCLES_OFFSET
                # [3:0] Set_t0 = 0x2
                # [7:4] Set_t1 = 0x2
                # [10:8] Set_t2 = 0x1
                # [13:11] Set_t3 = 0x1
                # [16:14] Set_t4 = 0x1
                # [19:17] Set_t5 = 0x1
                # [23:20] Set_t6 = 0x1
                w.write(0xE000E014, 0x00124922)
                # .. FINISH: NAND SET CYCLE
                # .. START: OPMODE
                # XNANDPS_SET_OPMODE_OFFSET
                # [1:0] set_mw = NAND_GRP_D8_ENABLE
                w.maskwrite(0xE000E018, 0x00000003,
                            self.config.NAND_GRP_D8_ENABLE)
                # .. FINISH: OPMODE
                # .. START: DIRECT COMMAND
                # XNANDPS_DIRECT_CMD_OFFSET
                # [25:23] chip_select = 0x4
                # [22:21] cmd_type = 0x2
                w.write(0xE000E010, 0x02400000)
                # .. FINISH: DIRECT COMMAND
            if self.config.NOR_PERIPHERAL_ENABLE and self.config.NOR_GRP_CS0_ENABLE:
                # .. START: SRAM/NOR CS0 SET CYCLE
                # XNANDPS_SET_CYCLES_OFFSET
                # [3:0] Set_t0 = 0x2
                # [7:4] Set_t1 = 0x2
                # [10:8] Set_t2 = 0x1
                # [13:11] Set_t3 = 0x1
                # [16:14] Set_t4 = 0x1
                # [19:17] Set_t5 = 0x1
                # [23:20] Set_t6 = 0x0
                w.write(0XE000E014, 0x00024922)
                # .. FINISH: SRAM/NOR CS0 SET CYCLE
                # .. START: DIRECT COMMAND
                # XNANDPS_DIRECT_CMD_OFFSET
                # [25:23] chip_select = 0x0
                # [22:21] cmd_type = 0x0
                # [19:0] addr = 0xf0
                w.write(0XE000E010, 0x000000F0)
                # .. FINISH: DIRECT COMMAND
                # .. START: NOR CS0 BASE ADDRESS
                # [15:0] NOR CS0 DATA = 0xf0
                w.maskwrite(0XE2000000, 0x0000FFFF, 0x000000F0)
                # .. FINISH: NOR CS0 BASE ADDRESS
            if self.config.NOR_PERIPHERAL_ENABLE and self.config.NOR_GRP_CS1_ENABLE:
                # .. START: SRAM/NOR CS1 SET CYCLE
                # XNANDPS_SET_CYCLES_OFFSET
                # [3:0] Set_t0 = 0x2
                # [7:4] Set_t1 = 0x2
                # [10:8] Set_t2 = 0x1
                # [13:11] Set_t3 = 0x1
                # [16:14] Set_t4 = 0x1
                # [19:17] Set_t5 = 0x1
                # [23:20] Set_t6 = 0x0
                w.write(0XE000E014, 0x00024922)
                # .. FINISH: SRAM/NOR CS1 SET CYCLE
                # .. START: DIRECT COMMAND
                # [25:23] chip_select = 0x0
                # [22:21] cmd_type = 0x0
                # [19:0] addr = 0xf0
                w.write(0XE000E010, 0x000000F0)
                # .. FINISH: DIRECT COMMAND
                # .. START: NOR CS1 BASE ADDRESS
                # [15:0] NOR CS1 DATA = 0xf0
                w.maskwrite(0XE4000000, 0x0000FFFF, 0x000000F0)
                # .. FINISH: NOR CS1 BASE ADDRESS
            # .. START: USB RESET
            # .. .. START: USB0 RESET
            # .. .. .. START: DIR MODE BANK 0
            # [31:0] DIRECTION_0 = 0x2880
            # .. .. ..
            w.maskwrite(0xE000A204, 0xFFFFFFFF, 0x00002880)
            # .. .. FINISH: DIR MODE BANK 0
            # .. .. START: DIR MODE BANK 1
            # .. .. FINISH: DIR MODE BANK 1
            # .. .. START: MASK_DATA_0_LSW HIGH BANK [15:0]
            # [31:16] MASK_0_LSW = 0xff7f
            # [15:0] DATA_0_LSW = 0x80
            # .. ..
            w.maskwrite(0xE000A000, 0xFFFFFFFF, 0xFF7F0080)
            # .. .. FINISH: MASK_DATA_0_LSW HIGH BANK [15:0]
            # .. .. START: MASK_DATA_0_MSW HIGH BANK [31:16]
            # .. .. FINISH: MASK_DATA_0_MSW HIGH BANK [31:16]
            # .. .. START: MASK_DATA_1_LSW HIGH BANK [47:32]
            # .. .. FINISH: MASK_DATA_1_LSW HIGH BANK [47:32]
            # .. .. START: MASK_DATA_1_MSW HIGH BANK [53:48]
            # .. .. FINISH: MASK_DATA_1_MSW HIGH BANK [53:48]
            # .. .. START: OUTPUT ENABLE BANK 0
            # [31:0] OP_ENABLE_0 = 0x2880
            # .. ..
            w.maskwrite(0xE000A208, 0xFFFFFFFF, 0x00002880)
            # .. .. FINISH: OUTPUT ENABLE BANK 0
            # .. .. START: OUTPUT ENABLE BANK 1
            # .. .. FINISH: OUTPUT ENABLE BANK 1
            # .. .. START: MASK_DATA_0_LSW LOW BANK [15:0]
            # [31:16] MASK_0_LSW = 0xff7f
            # [15:0] DATA_0_LSW = 0x0
            # .. ..
            w.maskwrite(0xE000A000, 0xFFFFFFFF, 0xFF7F0000)
            # .. .. .. FINISH: MASK_DATA_0_LSW LOW BANK [15:0]
            # .. .. .. START: MASK_DATA_0_MSW LOW BANK [31:16]
            # .. .. .. FINISH: MASK_DATA_0_MSW LOW BANK [31:16]
            # .. .. .. START: MASK_DATA_1_LSW LOW BANK [47:32]
            # .. .. .. FINISH: MASK_DATA_1_LSW LOW BANK [47:32]
            # .. .. .. START: MASK_DATA_1_MSW LOW BANK [53:48]
            # .. .. .. FINISH: MASK_DATA_1_MSW LOW BANK [53:48]
            # .. .. .. START: ADD 1 MS DELAY
            # .. .. ..
            w.maskdelay(0xF8F00200, 1)
            # .. .. .. FINISH: ADD 1 MS DELAY
            # .. .. .. START: MASK_DATA_0_LSW HIGH BANK [15:0]
            # [31:16] MASK_0_LSW = 0xff7f
            # [15:0] DATA_0_LSW = 0x80
            # .. .. ..
            w.maskwrite(0xE000A000, 0xFFFFFFFF, 0xFF7F0080)
            # .. .. .. FINISH: MASK_DATA_0_LSW HIGH BANK [15:0]
            # .. .. .. START: MASK_DATA_0_MSW HIGH BANK [31:16]
            # .. .. .. FINISH: MASK_DATA_0_MSW HIGH BANK [31:16]
            # .. .. .. START: MASK_DATA_1_LSW HIGH BANK [47:32]
            # .. .. .. FINISH: MASK_DATA_1_LSW HIGH BANK [47:32]
            # .. .. .. START: MASK_DATA_1_MSW HIGH BANK [53:48]
            # .. .. .. FINISH: MASK_DATA_1_MSW HIGH BANK [53:48]
            # .. .. FINISH: USB0 RESET
            # .. FINISH: USB RESET
            # .. START: ENET RESET
            # .. .. START: ENET0 RESET
            # .. .. .. START: DIR MODE BANK 0
            # [31:0] DIRECTION_0 = 0x2880
            # .. .. ..
            w.maskwrite(0xE000A204, 0xFFFFFFFF, 0x00002880)
            # .. .. FINISH: DIR MODE BANK 0
            # .. .. START: DIR MODE BANK 1
            # .. .. FINISH: DIR MODE BANK 1
            # .. .. START: MASK_DATA_0_LSW HIGH BANK [15:0]
            # [31:16] MASK_0_LSW = 0xf7ff
            # [15:0] DATA_0_LSW = 0x800
            # .. ..
            w.maskwrite(0xE000A000, 0xFFFFFFFF, 0xF7FF0800)
            # .. .. FINISH: MASK_DATA_0_LSW HIGH BANK [15:0]
            # .. .. START: MASK_DATA_0_MSW HIGH BANK [31:16]
            # .. .. FINISH: MASK_DATA_0_MSW HIGH BANK [31:16]
            # .. .. START: MASK_DATA_1_LSW HIGH BANK [47:32]
            # .. .. FINISH: MASK_DATA_1_LSW HIGH BANK [47:32]
            # .. .. START: MASK_DATA_1_MSW HIGH BANK [53:48]
            # .. .. FINISH: MASK_DATA_1_MSW HIGH BANK [53:48]
            # .. .. START: OUTPUT ENABLE BANK 0
            # [31:0] OP_ENABLE_0 = 0x2880
            # .. ..
            w.maskwrite(0xE000A208, 0xFFFFFFFF, 0x00002880)
            # .. .. FINISH: OUTPUT ENABLE BANK 0
            # .. .. START: OUTPUT ENABLE BANK 1
            # .. .. FINISH: OUTPUT ENABLE BANK 1
            # .. .. START: MASK_DATA_0_LSW LOW BANK [15:0]
            # [31:16] MASK_0_LSW = 0xf7ff
            # [15:0] DATA_0_LSW = 0x0
            # .. ..
            w.maskwrite(0xE000A000, 0xFFFFFFFF, 0xF7FF0000)
            # .. .. .. FINISH: MASK_DATA_0_LSW LOW BANK [15:0]
            # .. .. .. START: MASK_DATA_0_MSW LOW BANK [31:16]
            # .. .. .. FINISH: MASK_DATA_0_MSW LOW BANK [31:16]
            # .. .. .. START: MASK_DATA_1_LSW LOW BANK [47:32]
            # .. .. .. FINISH: MASK_DATA_1_LSW LOW BANK [47:32]
            # .. .. .. START: MASK_DATA_1_MSW LOW BANK [53:48]
            # .. .. .. FINISH: MASK_DATA_1_MSW LOW BANK [53:48]
            # .. .. .. START: ADD 1 MS DELAY
            # .. .. ..
            w.maskdelay(0xF8F00200, 1)
            # .. .. .. FINISH: ADD 1 MS DELAY
            # .. .. .. START: MASK_DATA_0_LSW HIGH BANK [15:0]
            # [31:16] MASK_0_LSW = 0xf7ff
            # [15:0] DATA_0_LSW = 0x800
            # .. .. ..
            w.maskwrite(0xE000A000, 0xFFFFFFFF, 0xF7FF0800)
            # .. .. .. FINISH: MASK_DATA_0_LSW HIGH BANK [15:0]
            # .. .. .. START: MASK_DATA_0_MSW HIGH BANK [31:16]
            # .. .. .. FINISH: MASK_DATA_0_MSW HIGH BANK [31:16]
            # .. .. .. START: MASK_DATA_1_LSW HIGH BANK [47:32]
            # .. .. .. FINISH: MASK_DATA_1_LSW HIGH BANK [47:32]
            # .. .. .. START: MASK_DATA_1_MSW HIGH BANK [53:48]
            # .. .. .. FINISH: MASK_DATA_1_MSW HIGH BANK [53:48]
            # .. .. FINISH: ENET0 RESET
            # .. FINISH: ENET RESET
            # .. START: I2C RESET
            # .. .. START: I2C0 RESET
            # .. .. .. START: DIR MODE GPIO BANK0
            # [31:0] DIRECTION_0 = 0x2880
            w.maskwrite(0xE000A204, 0xFFFFFFFF, 0x00002880)
            # .. .. .. FINISH: DIR MODE GPIO BANK0
            # .. .. .. START: DIR MODE GPIO BANK1
            # .. .. .. FINISH: DIR MODE GPIO BANK1
            # .. .. .. START: MASK_DATA_0_LSW HIGH BANK [15:0]
            # [31:16] MASK_0_LSW = 0xdfff
            # [15:0] DATA_0_LSW = 0x2000
            w.maskwrite(0xE000A000, 0xFFFFFFFF, 0xDFFF2000)
            # .. .. .. FINISH: MASK_DATA_0_LSW HIGH BANK [15:0]
            # .. .. .. START: MASK_DATA_0_MSW HIGH BANK [31:16]
            # .. .. .. FINISH: MASK_DATA_0_MSW HIGH BANK [31:16]
            # .. .. .. START: MASK_DATA_1_LSW HIGH BANK [47:32]
            # .. .. .. FINISH: MASK_DATA_1_LSW HIGH BANK [47:32]
            # .. .. .. START: MASK_DATA_1_MSW HIGH BANK [53:48]
            # .. .. .. FINISH: MASK_DATA_1_MSW HIGH BANK [53:48]
            # .. .. .. START: OUTPUT ENABLE
            # [31:0] OP_ENABLE_0 = 0x2880
            w.maskwrite(0xE000A208, 0xFFFFFFFF, 0x00002880)
            # .. .. .. FINISH: OUTPUT ENABLE
            # .. .. .. START: OUTPUT ENABLE
            # .. .. .. FINISH: OUTPUT ENABLE
            # .. .. .. START: MASK_DATA_0_LSW LOW BANK [15:0]
            # [31:16] MASK_0_LSW = 0xdfff
            # [15:0] DATA_0_LSW = 0x0
            w.maskwrite(0xE000A000, 0xFFFFFFFF, 0xDFFF0000)
            # .. .. .. FINISH: MASK_DATA_0_LSW LOW BANK [15:0]
            # .. .. .. START: MASK_DATA_0_MSW LOW BANK [31:16]
            # .. .. .. FINISH: MASK_DATA_0_MSW LOW BANK [31:16]
            # .. .. .. START: MASK_DATA_1_LSW LOW BANK [47:32]
            # .. .. .. FINISH: MASK_DATA_1_LSW LOW BANK [47:32]
            # .. .. .. START: MASK_DATA_1_MSW LOW BANK [53:48]
            # .. .. .. FINISH: MASK_DATA_1_MSW LOW BANK [53:48]
            # .. .. .. START: ADD 1 MS DELAY
            w.maskdelay(0xF8F00200, 1)
            # .. .. .. FINISH: ADD 1 MS DELAY
            # .. .. .. START: MASK_DATA_0_LSW HIGH BANK [15:0]
            # [31:16] MASK_0_LSW = 0xdfff
            # [15:0] DATA_0_LSW = 0x2000
            w.maskwrite(0xE000A000, 0xFFFFFFFF, 0xDFFF2000)
            # .. .. .. FINISH: MASK_DATA_0_LSW LOW BANK [15:0]
            # .. .. .. START: MASK_DATA_0_MSW LOW BANK [31:16]
            # .. .. .. FINISH: MASK_DATA_0_MSW LOW BANK [31:16]
            # .. .. .. START: MASK_DATA_1_LSW LOW BANK [47:32]
            # .. .. .. FINISH: MASK_DATA_1_LSW LOW BANK [47:32]
            # .. .. .. START: MASK_DATA_1_MSW LOW BANK [53:48]
            # .. .. .. FINISH: MASK_DATA_1_MSW LOW BANK [53:48]
            # .. .. FINISH: I2C0 RESET
            # .. FINISH: I2C RESET
            if self.config.NOR_PERIPHERAL_ENABLE and self.config.NOR_GRP_A25_ENABLE:
                # .. START: NOR CHIP SELECT
                # .. .. START: DIR MODE BANK 0
                # [31:0] DIRECTION_0 = 0x1
                w.maskwrite(0XE000A204, 0xFFFFFFFF, 0x00000001)
                # .. .. FINISH: DIR MODE BANK 0
                # .. .. START: MASK_DATA_0_LSW HIGH BANK [15:0]
                # [31:16] MASK_0_LSW = 0xfffe
                # [15:0] DATA_0_LSW = 0x0
                w.maskwrite(0XE000A000, 0xFFFFFFFF, 0xFFFE0000)
                # .. .. FINISH: MASK_DATA_0_LSW HIGH BANK [15:0]
                # .. .. START: OUTPUT ENABLE BANK 0
                # .. .. [31:0] OP_ENABLE_0 = 0x1
                w.maskwrite(0XE000A208, 0xFFFFFFFF, 0x00000001)
                # .. .. FINISH: OUTPUT ENABLE BANK 0
                # .. FINISH: NOR CHIP SELECT
            # FINISH: SMC TIMING CALCULATION REGISTER UPDATE

    def post_config(self):
        with self.array_writer("ps7_post_config") as w:
            w.unlock()
            # START: ENABLING LEVEL SHIFTER
            # [1:0] USER_INP_ICT_EN_0 = 3 (Version: 1/2)
            # [3:3] USER_LVL_INP_EN_0 = 1 (Version: 3)
            # [2:2] USER_LVL_OUT_EN_0 = 1 (Version: 3)
            # [3:2] USER_INP_ICT_EN_1 = 3 (Version: 1/2)
            # [1:1] USER_LVL_INP_EN_1 = 1 (Version: 3)
            # [0:0] USER_LVL_OUT_EN_1 = 1 (Version: 3)
            w.maskwrite(0xF8000900, 0x0000000F, 0x0000000F)
            # FINISH: ENABLING LEVEL SHIFTER
            # START: FPGA RESETS TO 0
            # [31:25] reserved_3 = 0
            # [24:24] FPGA_ACP_RST = 0 (Version: 1/2)
            # [24:24] reserved_FPGA_ACP_RST = 0 (Version: 3)
            # [23:23] FPGA_AXDS3_RST = 0 (Version: 1/2)
            # [23:23] reserved_FPGA_AXDS3_RST = 0 (Version: 3)
            # [22:22] FPGA_AXDS2_RST = 0 (Version: 1/2)
            # [22:22] reserved_FPGA_AXDS2_RST = 0 (Version: 3)
            # [21:21] FPGA_AXDS1_RST = 0 (Version: 1/2)
            # [21:21] reserved_FPGA_AXDS1_RST = 0 (Version: 3)
            # [20:20] FPGA_AXDS0_RST = 0 (Version: 1/2)
            # [20:20] reserved_FPGA_AXDS0_RST = 0 (Version: 3)
            # [19:18] reserved_2 = 0
            # [17:17] FSSW1_FPGA_RST = 0 (Version: 1/2)
            # [17:17] reserved_FSSW1_FPGA_RST = 0 (Version: 3)
            # [16:16] FSSW0_FPGA_RST = 0 (Version: 1/2)
            # [16:16] reserved_FSSW0_FPGA_RST = 0 (Version: 3)
            # [15:14] reserved_1 = 0
            # [13:13] FPGA_FMSW1_RST = 0 (Version: 1/2)
            # [13:13] reserved_FPGA_FMSW1_RST = 0 (Version: 3)
            # [12:12] FPGA_FMSW0_RST = 0 (Version: 1/2)
            # [12:12] reserved_FPGA_FMSW0_RST = 0 (Version: 3)
            # [11:11] FPGA_DMA3_RST = 0 (Version: 1/2)
            # [11:11] reserved_FPGA_DMA3_RST = 0 (Version: 3)
            # [10:10] FPGA_DMA2_RST = 0 (Version: 1/2)
            # [10:10] reserved_FPGA_DMA2_RST = 0 (Version: 3)
            # [9:9] FPGA_DMA1_RST = 0 (Version: 1/2)
            # [9:9] reserved_FPGA_DMA1_RST = 0 (Version: 3)
            # [8:8] FPGA_DMA0_RST = 0 (Version: 1/2)
            # [8:8] reserved_FPGA_DMA0_RST = 0 (Version: 3)
            # [7:4] reserved = 0
            # [3:3] FPGA3_OUT_RST = 0
            # [2:2] FPGA2_OUT_RST = 0
            # [1:1] FPGA1_OUT_RST = 0
            # [0:0] FPGA0_OUT_RST = 0
            w.maskwrite(0xF8000240, 0xFFFFFFFF, 0x00000000)
            # FINISH: FPGA RESETS TO 0
            w.lock()

    def debug(self):
        with self.array_writer("ps7_debug") as w:
            # DEBUG_CPU_CTI0
            w.write(0xF8898FB0, 0xC5ACCE55)
            # DEBUG_CPU_CTI1
            w.write(0xF8899FB0, 0xC5ACCE55)
            # DEBUG_CTI_FTM
            w.write(0xF8809FB0, 0xC5ACCE55)
