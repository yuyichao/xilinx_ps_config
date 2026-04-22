#!/usr/bin/env python

from .zynq_config import APUClkRatio, QSPIMode
from .utils import find_divisors

from math import floor, ceil
from pathlib import Path
import shutil

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

def _get_io_clksrc(clksrc):
    return (2, 3, 0)[clksrc.value]

def _get_can_mioclk(clk_io):
    if clk_io < 0:
        return 0
    return clk_io | (1 << 6)

class DataWriter:
    def __init__(self, io, version, config):
        self.io = io
        self.version = version
        self.suffix = f'_{version}_0'
        self.config = config

    def get_ddrc_force_low_pri_n(self):
        config = self.config
        return (config.DDR_PORT_HPR_ENABLE[0] or config.DDR_PORT_HPR_ENABLE[1] or
                config.DDR_PORT_HPR_ENABLE[2] or config.DDR_PORT_HPR_ENABLE[3])

    # 0xF8006004:0
    def get_ddrc_t_rfc_nom_x32(self):
        # 64ms / 8192 rows
        return clamp_floor(64000 / 8192 * self.config.DDR_FREQMHZ / 32, 0xfff)
    # 0xF8006014:0
    def get_ddrc_t_rc(self):
        return clamp_ceil(self.config.DDR_FREQMHZ * self.config.DDR_T_RC / 1000, 0x3f)
    # 0xF8006014:6
    def get_ddrc_t_rfc_min(self):
        # Base on vivado behavior
        return clamp_ceil(0.16 * self.config.DDR_FREQMHZ, 0xff)
    # 0xF8006018:0
    def get_ddrc_wr2pre(self):
        wr2pre = self.config.DDR_CWL + self.config.DDR_BL//2 + self.config.DDR_T_WR
        if False: # LPDDR2
            return clamp_val(wr2pre + 1, 0x1f)
        return clamp_val(wr2pre, 0x1f)
    # 0xF8006018:10
    def get_ddrc_t_faw(self):
        return clamp_ceil(self.config.DDR_FREQMHZ * self.config.DDR_T_FAW / 1000, 0x3f)
    # 0xF8006018:16
    def get_ddrc_t_ras_max(self):
        # 70 us, 1024 cycle unit
        return clamp_floor(70 * self.config.DDR_FREQMHZ / 1024, 0x3f)
    # 0xF8006018:22
    def get_ddrc_t_ras_min(self):
        return clamp_ceil(self.config.DDR_FREQMHZ * self.config.DDR_T_RAS_MIN / 1000, 0x1f)
    # 0xF800601C:0
    def get_ddrc_write_latency(self):
        if False: # LPDDR2
            return self.config.DDR_CWL
        return clamp_val(self.config.DDR_CWL - 1, 0x1f)
    # 0xF800601C:5
    def get_ddrc_rd2wr(self):
        val = self.config.DDR_RL + self.config.DDR_BL//2 - self.config.DDR_CWL
        if False: # LPDDR2
            raise NotImplementedError
        return clamp_val(val + 2, 0x1f)
    # 0xF800601C:10
    def get_ddrc_wr2rd(self):
        wr2rd = self.config.DDR_CWL + self.config.DDR_T_WTR + self.config.DDR_BL//2
        if False: # LPDDR2
            return clamp_val(wr2rd + 1, 0x1f)
        return clamp_val(wr2rd, 0x1f)
    # 0xF800601C:23
    def get_ddrc_rd2pre(self):
        if False: # LPDDR2 or DDR2
            # DDR2: AL + BL/2 + max(tRTP, 2) - 2
            # LPDDR2: BL/2 + tRTP - 1
            raise NotImplementedError
        return clamp_ceil(max(0.0075 * self.config.DDR_FREQMHZ, 4) + self.config.DDR_AL,
                              0x1f)
    # 0xF8006020:5
    def get_ddrc_t_rrd(self):
        return max(ceil(0.0075 * self.config.DDR_FREQMHZ), 4)
    # 0xF800602C:0
    def get_ddrc_emr2(self):
        return max(self.config.DDR_CWL - 5, 0) << 3
    # 0xF8006030:0
    def get_ddrc_mr(self):
        if False: # LPDDR2 or DDR2
            raise NotImplementedError
        # MR0 for DDR3
        bl = 0 if self.config.DDR_BL == 8 else 2
        cl2 = self.config.DDR_CL > 13
        cl46 = (self.config.DDR_CL - 5) & 0x7
        dll = 1
        wr = self.config.DDR_T_WR - 4
        return bl | (cl2 << 2) | (cl46 << 4) | (dll << 8) | (wr << 9)
    # 0xF8006034:0
    def get_ddrc_burst_rdwr(self):
        return self.config.DDR_BL // 2
    # 0xF8006034:4
    def get_ddrc_pre_cke_x1024(self):
        # 700 us based on vivado output
        return clamp_ceil(700 * self.config.DDR_FREQMHZ / 1024, 0x3ff)
    # 0xF800605C:12
    def get_ddrc_wr_odt_hold(self):
        return self.config.DDR_BL // 2 + 1
    # 0xF8006068:0
    def get_ddrc_wrlvl_ww(self):
        return clamp_val(self.config.DDR_CL + 58, 0xff)
    # 0xF8006068:8
    def get_ddrc_rdlvl_rr(self):
        return clamp_val(self.config.DDR_CL + 58, 0xff)
    # 0xF8006078:12
    def get_ddrc_t_cksre(self):
        return max(ceil(0.0075 * self.config.DDR_FREQMHZ), 4) + 1
    # 0xF8006078:16
    def get_ddrc_t_cksrx(self):
        return max(ceil(0.0075 * self.config.DDR_FREQMHZ), 4) + 1
    # 0xF80060A8:0
    def get_t_zq_short_interval_x1024(self):
        # 100 ms based on vivado output
        return clamp_floor(100000 * self.config.DDR_FREQMHZ / 1024, 0xfffff)
    # 0xF80060A8:20
    def get_dram_rstn_x1024(self):
        # 200 us based on vivado output
        return clamp_ceil(200 * self.config.DDR_FREQMHZ / 1024, 0xff)
    # 0xF80060AC:1
    def get_deeppowerdown_to_x1024(self):
        # 500 us based on vivado output
        return clamp_ceil(500 * self.config.DDR_FREQMHZ / 1024, 0xff)
    # 0xF80060B8:0
    def get_ddrc_dfi_t_rddata_en(self):
        if False: # LPDDR2
            return self.config.DDR_CL
        return clamp_val(self.config.DDR_CL - 1, 0x1f)
    # 0xF8006194:0
    def get_phy_wr_rl_delay(self):
        return max(self.config.DDR_CWL - 4, 1)
    # 0xF8006194:5
    def get_phy_rd_rl_delay(self):
        return max(self.config.DDR_CL - 3, 1)
    # 0xF80062B0:4
    def get_ddrc_idle_after_reset_x32(self):
        # 1.08 us based on vivado output
        return clamp_ceil(1.08 * self.config.DDR_FREQMHZ / 32, 0xff)
    # 0xF80062B4:0
    def get_ddrc_max_auto_init_x1024(self):
        # 322.5 us based on vivado output
        return clamp_ceil(322.5 * self.config.DDR_FREQMHZ / 1024, 0xff)
    # 0xF80062B4:8
    def get_ddrc_dev_zqinit_x32(self):
        # 1.08 us based on vivado output
        return clamp_ceil(1.08 * self.config.DDR_FREQMHZ / 32, 0x3ff)

    def get_wrlvl_init_ratio(self, n):
        dqs_to_clk_delay = self.config.DDR_DQS_TO_CLK_DELAY[n]
        return clamp_floor(dqs_to_clk_delay * self.config.DDR_FREQMHZ * 0.256, 0x3ff)
    def get_wr_dqs_slave_ratio(self, n):
        return self.get_wrlvl_init_ratio(n) + 128
    def get_wr_data_slave_ratio(self, n):
        return self.get_wrlvl_init_ratio(n) + 192

    def get_gatelvl_init_ratio(self, n):
        board_delay = self.config.DDR_BOARD_DELAY[n]
        return clamp_floor(board_delay * self.config.DDR_FREQMHZ * 0.512 + 96, 0x3ff)
    def get_fifo_we_slave_ratio(self, n):
        return self.get_gatelvl_init_ratio(n) + 85

    def get_uart_bdiv_cd(self, baud):
        bdiv, cd, _ = find_divisors(self.config.UART_FREQMHZ * 1000_000, baud,
                                    (4, 255), (1, 0xffff))
        return bdiv, cd

    def array_writer(self, name):
        return ArrayWriter(self.io, name + self.suffix)

    def delay(self, w, t):
        w.maskdelay(0xF8F00200, 1)

    def set_mio(self, w, bit, val):
        idx = bit // 16
        subbit = bit % 16
        addr = idx * 4 + 0xE000A000
        mask = 0xffff if idx < 3 else 0x3f
        mask = mask ^ (1 << subbit)
        data = (1 << subbit) if val else 0
        w.write(addr, data | (mask << 16))

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
            w.init_pll(0, self.config.ARM_FBDIV)
            # ARM_CLK_CTRL
            # [5:4] SRCSEL = CPU_CLKSRC
            # [13:8] DIVISOR = CPU_DIVISOR0
            # [24:24] CPU_6OR4XCLKACT = 0x1
            # [25:25] CPU_3OR2XCLKACT = 0x1
            # [26:26] CPU_2XCLKACT = 0x1
            # [27:27] CPU_1XCLKACT = 0x1
            # [28:28] CPU_PERI_CLKACT = 0x1
            arm_divisor = self.config.CPU_DIVISOR0
            arm_srcsel = (0, 2, 3)[self.config.CPU_CLKSRC.value]
            w.maskwrite(0xF8000120, 0x1F003F30,
                        0x1F000000 | (arm_divisor << 8) | (arm_srcsel << 4))

            # Init DDR PLL
            w.init_pll(1, self.config.DDR_FBDIV)
            # DDR_CLK_CTRL
            # [0:0] DDR_3XCLKACT = 0x1
            # [1:1] DDR_2XCLKACT = 0x1
            div_3x = self.config.DDR_DIVISOR0
            div_2x = div_3x * 3 // 2
            # [25:20] DDR_3XCLK_DIVISOR = DDR_DIVISOR0
            # [31:26] DDR_2XCLK_DIVISOR = DDR_DIVISOR0 * 3 / 2
            w.maskwrite(0xF8000124, 0xFFF00003,
                        0x00000003 | (div_3x << 20) | (div_2x << 26))

            # Init IO PLL
            w.init_pll(2, self.config.IO_FBDIV)

            w.lock()

    def clock_init(self):
        with self.array_writer("ps7_clock_init_data") as w:
            w.unlock()

            # DCI_CLK_CTRL
            # [0:0] CLKACT = 0x1
            # [13:8] DIVISOR0 = DCI_DIVISOR0
            # [25:20] DIVISOR1 = DCI_DIVISOR1
            w.maskwrite(0xF8000128, 0x03F03F01,
                        0x00000001 |
                        (self.config.DCI_DIVISOR0 << 8) |
                        (self.config.DCI_DIVISOR1 << 20))
            if self.config.ENET0_ENABLE:
                gem0_clk = self.config.ENET0_CLKSRC.value
                # GEM0_RCLK_CTRL
                # [0:0] CLKACT = 0x1
                # [4:4] SRCSEL
                w.maskwrite(0xF8000138, 0x00000011,
                            0x00000001 |
                            ((0, 0, 0, 1)[gem0_clk] << 4))
                # GEM0_CLK_CTRL
                # [0:0] CLKACT = 0x1
                # [6:4] SRCSEL
                # [13:8] DIVISOR
                # [25:20] DIVISOR1
                w.maskwrite(0xF8000140, 0x03F03F71,
                            0x00000001 |
                            ((2, 3, 0, 4)[gem0_clk] << 4) |
                            (self.config.ENET0_DIVISOR0 << 8) |
                            (self.config.ENET0_DIVISOR1 << 20))
            if self.config.ENET1_ENABLE:
                gem1_clk = self.config.ENET1_CLKSRC.value
                # GEM1_RCLK_CTRL
                # [0:0] CLKACT = 0x1
                # [4:4] SRCSEL
                w.maskwrite(0xF800013C, 0x00000011,
                            0x00000001 |
                            ((0, 0, 0, 1)[gem1_clk] << 4))
                # GEM1_CLK_CTRL
                # [0:0] CLKACT = 0x1
                # [6:4] SRCSEL
                # [13:8] DIVISOR
                # [25:20] DIVISOR1
                w.maskwrite(0xF8000144, 0x03F03F71,
                            0x00000001 |
                            ((2, 3, 0, 4)[gem1_clk] << 4) |
                            (self.config.ENET1_DIVISOR0 << 8) |
                            (self.config.ENET1_DIVISOR1 << 20))
            if self.config.NOR_ENABLE or self.config.NAND_ENABLE:
                # SMC_CLK_CTRL
                # [0:0] CLKACT = 0x1
                # [5:4] SRCSEL
                # [13:8] DIVISOR = SMC_DIVISOR0
                w.maskwrite(0xF8000148, 0x00003F31,
                            0x00000001 |
                            (_get_io_clksrc(self.config.SMC_CLKSRC) << 4) |
                            (self.config.SMC_DIVISOR0 << 8))
            if self.config.QSPI_ENABLE:
                # LQSPI_CLK_CTRL
                # [0:0] CLKACT = 0x1
                # [5:4] SRCSEL
                # [13:8] DIVISOR = QSPI_DIVISOR0
                w.maskwrite(0xF800014C, 0x00003F31,
                            0x00000001 |
                            (_get_io_clksrc(self.config.QSPI_CLKSRC) << 4) |
                            (self.config.QSPI_DIVISOR0 << 8))
            if self.config.SD0_ENABLE or self.config.SD1_ENABLE:
                # SDIO_CLK_CTRL
                # [0:0] CLKACT0 = SD0_ENABLE
                # [1:1] CLKACT1 = SD1_ENABLE
                # [5:4] SRCSEL = SDIO_CLKSRC
                # [13:8] DIVISOR = SDIO_DIVISOR0
                w.maskwrite(0xF8000150, 0x00003F33,
                            self.config.SD0_ENABLE |
                            (self.config.SD1_ENABLE << 1) |
                            (_get_io_clksrc(self.config.SDIO_CLKSRC) << 4) |
                            (self.config.SDIO_DIVISOR0 << 8))
            if self.config.UART0_ENABLE or self.config.UART1_ENABLE:
                # UART_CLK_CTRL
                # [0:0] CLKACT0 = UART0_ENABLE
                # [1:1] CLKACT1 = UART1_ENABLE
                # [5:4] SRCSEL = UART_CLKSRC
                # [13:8] DIVISOR = UART_DIVISOR0
                w.maskwrite(0xF8000154, 0x00003F33,
                            self.config.UART0_ENABLE |
                            (self.config.UART1_ENABLE << 1) |
                            (_get_io_clksrc(self.config.UART_CLKSRC) << 4) |
                            (self.config.UART_DIVISOR0 << 8))
            if self.config.SPI0_ENABLE or self.config.SPI1_ENABLE:
                # SPI_CLK_CTRL
                # [0:0] CLKACT0 = SPI0_ENABLE
                # [1:1] CLKACT1 = SPI1_ENABLE
                # [5:4] SRCSEL = SPI_CLKSRC
                # [13:8] DIVISOR = SPI_DIVISOR0
                w.maskwrite(0xF8000158, 0x00003F33,
                            self.config.SPI0_ENABLE |
                            (self.config.SPI1_ENABLE << 1) |
                            (_get_io_clksrc(self.config.SPI_CLKSRC) << 4) |
                            (self.config.SPI_DIVISOR0 << 8))
            if self.config.CAN0_ENABLE or self.config.CAN1_ENABLE:
                # CAN_CLK_CTRL
                # [0:0] CLKACT0 = CAN0_ENABLE
                # [1:1] CLKACT1 = CAN1_ENABLE
                # [5:4] SRCSEL = CAN_CLKSRC
                # [13:8] DIVISOR0 = CAN_DIVISOR0
                # [25:20] DIVISOR1 = CAN_DIVISOR1
                w.maskwrite(0xF800015C, 0x03F03F33,
                            self.config.CAN0_ENABLE |
                            (self.config.CAN1_ENABLE << 1) |
                            (_get_io_clksrc(self.config.CAN_CLKSRC) << 4) |
                            (self.config.CAN_DIVISOR0 << 8) |
                            (self.config.CAN_DIVISOR1 << 20))
                # CAN_MIOCLK_CTRL
                # [5:0] CAN0_MUX = CAN0_CLK_IO
                # [6:6] CAN0_REF_SEL = CAN0_CLK_ENABLE
                # [21:16] CAN1_MUX = CAN1_CLK_IO
                # [22:22] CAN1_REF_SEL = CAN1_CLK_ENABLE
                w.maskwrite(0xF8000160, 0x007F007F,
                            _get_can_mioclk(self.config.CAN0_CLK_IO) |
                            (_get_can_mioclk(self.config.CAN1_CLK_IO) << 16))
            # PCAP_CLK_CTRL
            # [0:0] CLKACT = 0x1
            # [5:4] SRCSEL = PCAP_CLKSRC
            # [13:8] DIVISOR = PCAP_DIVISOR0
            w.maskwrite(0xF8000168, 0x00003F31,
                        0x00000001 |
                        (_get_io_clksrc(self.config.PCAP_CLKSRC) << 4) |
                        (self.config.PCAP_DIVISOR0 << 8))
            for clk_id in range(4):
                # FPGA<n>_CLK_CTRL
                # [5:4] SRCSEL
                # [13:8] DIVISOR0
                # [25:20] DIVISOR1
                clk = self.config.FCLK[clk_id]
                if clk.ENABLE:
                    srcsel = _get_io_clksrc(clk.CLKSRC)
                    w.maskwrite(0xF8000170 + 0x10 * clk_id, 0x03F03F30,
                                (srcsel << 4) |
                                (clk.DIVISOR0 << 8) |
                                (clk.DIVISOR1 << 20))
            # CLK_621_TRUE
            # [0:0] CLK_621_TRUE = 0x0/0x1
            if self.config.APU_CLK_RATIO == APUClkRatio.RATIO_621:
                w.maskwrite(0xF80001C4, 0x00000001, 0x00000001)
            elif self.config.APU_CLK_RATIO == APUClkRatio.RATIO_421:
                w.maskwrite(0xF80001C4, 0x00000000, 0x00000000)
            else:
                raise ValueError(f"Invalid APU_CLK_RATIO: {self.config.APU_CLK_RATIO}.")
            # [0:0] DMA_CPU_2XCLKACT = 0x1
            # [2:2] USB0_CPU_1XCLKACT = 0x1
            # [3:3] USB1_CPU_1XCLKACT = 0x1
            # [6:6] GEM0_CPU_1XCLKACT = ENET0_ENABLE
            # [7:7] GEM1_CPU_1XCLKACT = ENET1_ENABLE
            # [10:10] SDI0_CPU_1XCLKACT = SD0_ENABLE
            # [11:11] SDI1_CPU_1XCLKACT = SD1_ENABLE
            # [14:14] SPI0_CPU_1XCLKACT = SPI0_ENABLE
            # [15:15] SPI1_CPU_1XCLKACT = SPI1_ENABLE
            # [16:16] CAN0_CPU_1XCLKACT = CAN0_ENABLE
            # [17:17] CAN1_CPU_1XCLKACT = CAN1_ENABLE
            # [18:18] I2C0_CPU_1XCLKACT = 0x1
            # [19:19] I2C1_CPU_1XCLKACT = 0x1
            # [20:20] UART0_CPU_1XCLKACT = UART0_ENABLE
            # [21:21] UART1_CPU_1XCLKACT = UART1_ENABLE
            # [22:22] GPIO_CPU_1XCLKACT = 0x1
            # [23:23] LQSPI_CPU_1XCLKACT = QSPI_ENABLE
            # [24:24] SMC_CPU_1XCLKACT = 0x1
            w.maskwrite(0xF800012C, 0x01FFCCCD,
                        0x014C000D |
                        (self.config.ENET0_ENABLE << 6) |
                        (self.config.ENET1_ENABLE << 7) |
                        (self.config.SD0_ENABLE << 10) |
                        (self.config.SD1_ENABLE << 11) |
                        (self.config.SPI0_ENABLE << 14) |
                        (self.config.SPI1_ENABLE << 15) |
                        (self.config.CAN0_ENABLE << 16) |
                        (self.config.CAN1_ENABLE << 17) |
                        (self.config.UART0_ENABLE << 20) |
                        (self.config.UART1_ENABLE << 21) |
                        (self.config.QSPI_ENABLE << 23))

            if self.config.WDT_ENABLE:
                # WDT_CLK_SEL
                # [0:0] SEL = WDT_CLK_EXTERNAL
                w.maskwrite(0XF8000304, 0x00000001, self.config.WDT_CLK_EXTERNAL)

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
                            self.get_ddrc_t_rfc_nom_x32())
            else:
                w.maskwrite(0xF8006004, 0x1FFFFFFF,
                            0x00081000 |
                            self.get_ddrc_t_rfc_nom_x32())

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
                        self.get_ddrc_t_rc() |
                        (self.get_ddrc_t_rfc_min() << 6))

            # DRAM_PARAM_REG1
            # [4:0] reg_ddrc_wr2pre
            # [9:5] reg_ddrc_powerdown_to_x32 = 0x6
            # [15:10] reg_ddrc_t_faw
            # [21:16] reg_ddrc_t_ras_max
            # [26:22] reg_ddrc_t_ras_min
            # [31:28] reg_ddrc_t_cke = 0x4
            w.maskwrite(0xF8006018, 0xF7FFFFFF,
                        0x400000C0 |
                        self.get_ddrc_wr2pre() |
                        (self.get_ddrc_t_faw() << 10) |
                        (self.get_ddrc_t_ras_max() << 16) |
                        (self.get_ddrc_t_ras_min() << 22))

            # DRAM_PARAM_REG2
            # [4:0] reg_ddrc_write_latency
            # [9:5] reg_ddrc_rd2wr
            # [14:10] reg_ddrc_wr2rd
            # [19:15] reg_ddrc_t_xp = 0x5
            # [22:20] reg_ddrc_pad_pd = 0x0
            # [27:23] reg_ddrc_rd2pre
            # [31:28] reg_ddrc_t_rcd = DDR_T_RCD
            w.write(0xF800601C,
                    0x00028000 |
                    self.get_ddrc_write_latency() |
                    (self.get_ddrc_rd2wr() << 5) |
                    (self.get_ddrc_wr2rd() << 10) |
                    (self.get_ddrc_rd2pre() << 23) |
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
                            (self.get_ddrc_t_rrd() << 5) |
                            (self.config.DDR_T_RP << 12) |
                            (self.config.DDR_CL << 24))
            else:
                w.maskwrite(0xF8006020, 0xFFFFFFFC,
                            0x202802B0 |
                            (self.get_ddrc_t_rrd() << 5) |
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
            w.write(0xF800602C,
                    0x00000000 |
                    self.get_ddrc_emr2())

            # DRAM_EMR_MR_REG
            # [15:0] reg_ddrc_mr
            # [31:16] reg_ddrc_emr = 0x4
            w.write(0xF8006030,
                    0x00040000 |
                    self.get_ddrc_mr())

            # DRAM_BURST8_RDWR
            # [3:0] reg_ddrc_burst_rdwr
            # [13:4] reg_ddrc_pre_cke_x1024
            # [25:16] reg_ddrc_post_cke_x1024 = 0x1
            # [28:28] reg_ddrc_burstchop = 0x0
            w.maskwrite(0xF8006034, 0x13FF3FFF,
                        0x00010000 |
                        self.get_ddrc_burst_rdwr() |
                        (self.get_ddrc_pre_cke_x1024() << 4))

            # DRAM_DISABLE_DQ
            # [0:0] reg_ddrc_force_low_pri_n = 0x0
            # [1:1] reg_ddrc_dis_dq = 0x0
            # [6:6] reg_phy_debug_mode = 0x0 (Version: 1/2)
            # [7:7] reg_phy_wr_level_start = 0x0 (Version: 1/2)
            # [8:8] reg_phy_rd_level_start = 0x0 (Version: 1/2)
            # [12:9] reg_phy_dq0_wait_t = 0x0 (Version: 1/2)
            if self.version >= 3:
                w.maskwrite(0xF8006038, 0x00000003,
                            0x00000000 | self.get_ddrc_force_low_pri_n())
            else:
                w.maskwrite(0xF8006038, 0x00001FC3,
                            0x00000000 | self.get_ddrc_force_low_pri_n())

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
            w.write(0xF8006040, 0xFFF00000)

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
                        (self.get_ddrc_wr_odt_hold() << 12))

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
                        (self.config.DDR_HPRLPR_QUEUE_PARTITION.value << 1))

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
                        self.get_ddrc_wrlvl_ww() |
                        (self.get_ddrc_rdlvl_rr() << 8))

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
                            (self.get_ddrc_t_cksre() << 12) |
                            (self.get_ddrc_t_cksrx() << 16))

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
            w.write(0xF80060A4, 0x10200802)

            # CHE_T_ZQ_SHORT_INTERVAL_REG
            # [19:0] t_zq_short_interval_x1024
            # [27:20] dram_rstn_x1024
            w.maskwrite(0xF80060A8, 0x0FFFFFFF,
                        self.get_t_zq_short_interval_x1024() |
                        (self.get_dram_rstn_x1024() << 20))

            # DEEP_PWRDWN_REG
            # [0:0] deeppowerdown_en = 0x0
            # [8:1] deeppowerdown_to_x1024
            w.maskwrite(0xF80060AC, 0x000001FF,
                        0x00000000 |
                        (self.get_deeppowerdown_to_x1024() << 1))

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
                        self.get_ddrc_dfi_t_rddata_en())

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
                        self.get_wrlvl_init_ratio(0) |
                        (self.get_gatelvl_init_ratio(0) << 10))

            # PHY_INIT_RATIO1
            # [9:0] reg_phy_wrlvl_init_ratio
            # [19:10] reg_phy_gatelvl_init_ratio
            w.maskwrite(0xF8006130, 0x000FFFFF,
                        self.get_wrlvl_init_ratio(1) |
                        (self.get_gatelvl_init_ratio(1) << 10))

            # PHY_INIT_RATIO2
            # [9:0] reg_phy_wrlvl_init_ratio
            # [19:10] reg_phy_gatelvl_init_ratio
            w.maskwrite(0xF8006134, 0x000FFFFF,
                        self.get_wrlvl_init_ratio(2) |
                        (self.get_gatelvl_init_ratio(2) << 10))

            # PHY_INIT_RATIO3
            # [9:0] reg_phy_wrlvl_init_ratio
            # [19:10] reg_phy_gatelvl_init_ratio
            w.maskwrite(0xF8006138, 0x000FFFFF,
                        self.get_wrlvl_init_ratio(3) |
                        (self.get_gatelvl_init_ratio(3) << 10))

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
                        self.get_wr_dqs_slave_ratio(0))

            # PHY_WR_DQS_CFG1
            # [9:0] reg_phy_wr_dqs_slave_ratio
            # [10:10] reg_phy_wr_dqs_slave_force = 0x0
            # [19:11] reg_phy_wr_dqs_slave_delay = 0x0
            w.maskwrite(0xF8006158, 0x000FFFFF,
                        0x00000000 |
                        self.get_wr_dqs_slave_ratio(1))

            # PHY_WR_DQS_CFG2
            # [9:0] reg_phy_wr_dqs_slave_ratio
            # [10:10] reg_phy_wr_dqs_slave_force = 0x0
            # [19:11] reg_phy_wr_dqs_slave_delay = 0x0
            w.maskwrite(0xF800615C, 0x000FFFFF,
                        0x00000000 |
                        self.get_wr_dqs_slave_ratio(2))

            # PHY_WR_DQS_CFG3
            # [9:0] reg_phy_wr_dqs_slave_ratio
            # [10:10] reg_phy_wr_dqs_slave_force = 0x0
            # [19:11] reg_phy_wr_dqs_slave_delay = 0x0
            w.maskwrite(0xF8006160, 0x000FFFFF,
                        0x00000000 |
                        self.get_wr_dqs_slave_ratio(3))

            # PHY_WE_DQS_CFG0
            # [10:0] reg_phy_fifo_we_slave_ratio
            # [11:11] reg_phy_fifo_we_in_force = 0x0
            # [20:12] reg_phy_fifo_we_in_delay = 0x0
            w.maskwrite(0xF8006168, 0x001FFFFF,
                        0x00000000 |
                        self.get_fifo_we_slave_ratio(0))

            # PHY_WE_DQS_CFG1
            # [10:0] reg_phy_fifo_we_slave_ratio
            # [11:11] reg_phy_fifo_we_in_force = 0x0
            # [20:12] reg_phy_fifo_we_in_delay = 0x0
            w.maskwrite(0xF800616C, 0x001FFFFF,
                        0x00000000 |
                        self.get_fifo_we_slave_ratio(1))

            # PHY_WE_DQS_CFG2
            # [10:0] reg_phy_fifo_we_slave_ratio
            # [11:11] reg_phy_fifo_we_in_force = 0x0
            # [20:12] reg_phy_fifo_we_in_delay = 0x0
            w.maskwrite(0xF8006170, 0x001FFFFF,
                        0x00000000 |
                        self.get_fifo_we_slave_ratio(2))

            # PHY_WE_DQS_CFG3
            # [10:0] reg_phy_fifo_we_slave_ratio
            # [11:11] reg_phy_fifo_we_in_force = 0x0
            # [20:12] reg_phy_fifo_we_in_delay = 0x0
            w.maskwrite(0xF8006174, 0x001FFFFF,
                        0x00000000 |
                        self.get_fifo_we_slave_ratio(3))

            # WR_DATA_SLV0
            # [9:0] reg_phy_wr_data_slave_ratio
            # [10:10] reg_phy_wr_data_slave_force = 0x0
            # [19:11] reg_phy_wr_data_slave_delay = 0x0
            w.maskwrite(0xF800617C, 0x000FFFFF,
                        0x00000000 |
                        self.get_wr_data_slave_ratio(0))

            # WR_DATA_SLV1
            # [9:0] reg_phy_wr_data_slave_ratio
            # [10:10] reg_phy_wr_data_slave_force = 0x0
            # [19:11] reg_phy_wr_data_slave_delay = 0x0
            w.maskwrite(0xF8006180, 0x000FFFFF,
                        0x00000000 |
                        self.get_wr_data_slave_ratio(1))

            # WR_DATA_SLV2
            # [9:0] reg_phy_wr_data_slave_ratio
            # [10:10] reg_phy_wr_data_slave_force = 0x0
            # [19:11] reg_phy_wr_data_slave_delay = 0x0
            w.maskwrite(0xF8006184, 0x000FFFFF,
                        0x00000000 |
                        self.get_wr_data_slave_ratio(2))

            # WR_DATA_SLV3
            # [9:0] reg_phy_wr_data_slave_ratio
            # [10:10] reg_phy_wr_data_slave_force = 0x0
            # [19:11] reg_phy_wr_data_slave_delay = 0x0
            w.maskwrite(0xF8006188, 0x000FFFFF,
                        0x00000000 |
                        self.get_wr_data_slave_ratio(3))

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
                w.write(0xF8006190, 0x10040080)

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
                        self.get_phy_wr_rl_delay() |
                        (self.get_phy_rd_rl_delay() << 5))

            # PAGE_MASK
            # [31:0] reg_arb_page_addr_mask = 0x0
            w.write(0xF8006204, 0x00000000)

            # AXI_PRIORITY_WR_PORT0
            # [9:0] reg_arb_pri_wr_portn
            # [16:16] reg_arb_disable_aging_wr_portn = 0x0
            # [17:17] reg_arb_disable_urgent_wr_portn = 0x0
            # [18:18] reg_arb_dis_page_match_wr_portn = 0x0
            # [19:19] reg_arb_dis_rmw_portn = 0x1 (Version: 1/2)
            pri = self.config.DDR_PRIORITY_WRITEPORT[0].value
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
            pri = self.config.DDR_PRIORITY_WRITEPORT[1].value
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
            pri = self.config.DDR_PRIORITY_WRITEPORT[2].value
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
            pri = self.config.DDR_PRIORITY_WRITEPORT[3].value
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
            pri = self.config.DDR_PRIORITY_READPORT[0].value
            w.maskwrite(0xF8006218, 0x000F03FF,
                        0x00000000 | pri | (self.config.DDR_PORT_HPR_ENABLE[0] << 19))

            # AXI_PRIORITY_RD_PORT1
            # [9:0] reg_arb_pri_rd_portn
            # [16:16] reg_arb_disable_aging_rd_portn = 0x0
            # [17:17] reg_arb_disable_urgent_rd_portn = 0x0
            # [18:18] reg_arb_dis_page_match_rd_portn = 0x0
            # [19:19] reg_arb_set_hpr_rd_portn = 0x0
            pri = self.config.DDR_PRIORITY_READPORT[1].value
            w.maskwrite(0xF800621C, 0x000F03FF,
                        0x00000000 | pri | (self.config.DDR_PORT_HPR_ENABLE[1] << 19))

            # AXI_PRIORITY_RD_PORT2
            # [9:0] reg_arb_pri_rd_portn
            # [16:16] reg_arb_disable_aging_rd_portn = 0x0
            # [17:17] reg_arb_disable_urgent_rd_portn = 0x0
            # [18:18] reg_arb_dis_page_match_rd_portn = 0x0
            # [19:19] reg_arb_set_hpr_rd_portn = 0x0
            pri = self.config.DDR_PRIORITY_READPORT[2].value
            w.maskwrite(0xF8006220, 0x000F03FF,
                        0x00000000 | pri | (self.config.DDR_PORT_HPR_ENABLE[2] << 19))

            # AXI_PRIORITY_RD_PORT3
            # [9:0] reg_arb_pri_rd_portn
            # [16:16] reg_arb_disable_aging_rd_portn = 0x0
            # [17:17] reg_arb_disable_urgent_rd_portn = 0x0
            # [18:18] reg_arb_dis_page_match_rd_portn = 0x0
            # [19:19] reg_arb_set_hpr_rd_portn = 0x0
            pri = self.config.DDR_PRIORITY_READPORT[3].value
            w.maskwrite(0xF8006224, 0x000F03FF,
                        0x00000000 | pri | (self.config.DDR_PORT_HPR_ENABLE[3] << 19))

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
            w.write(0xF80062AC, 0x00000000)

            # LPDDR_CTRL2
            # [3:0] reg_ddrc_min_stable_clock_x1 = 0x5
            # [11:4] reg_ddrc_idle_after_reset_x32
            # [21:12] reg_ddrc_t_mrw = 0x5
            w.maskwrite(0xF80062B0, 0x003FFFFF,
                        0x00005005 |
                        (self.get_ddrc_idle_after_reset_x32() << 4))

            # LPDDR_CTRL3
            # [7:0] reg_ddrc_max_auto_init_x1024
            # [17:8] reg_ddrc_dev_zqinit_x32
            w.maskwrite(0xF80062B4, 0x0003FFFF,
                        self.get_ddrc_max_auto_init_x1024() |
                        (self.get_ddrc_dev_zqinit_x32() << 8))

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
            w.write(0xF8000B5C, 0x0018C61C)
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
            w.write(0xF8000B60, 0x00F9861C)
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
            w.write(0xF8000B64, 0x00F9861C)
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
            w.write(0xF8000B68, 0x00F9861C)
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
                pin = self.config.MIO_PINS[n]
                if not pin.used:
                    continue
                w.maskwrite(0xF8000700 | (n * 4), 0x00003FFF, pin.get_reg())
            if self.config.SD0_ENABLE:
                # [5:0] SDIO0_WP_SEL = SD0_WP_IO
                # [21:16] SDIO0_CD_SEL = SD0_CD_IO
                w.maskwrite(0xF8000830, 0x003F003F,
                            self.config.SD0_WP_IO | (self.config.SD0_CD_IO << 16))
            if self.config.SD1_ENABLE:
                # [5:0] SDIO1_WP_SEL = SD1_WP_IO
                # [21:16] SDIO1_CD_SEL = SD1_CD_IO
                w.maskwrite(0xF8000830, 0x003F003F,
                            self.config.SD1_WP_IO | (self.config.SD1_CD_IO << 16))
            # FINISH: MIO PROGRAMMING
            w.lock()

    def peripherals_init(self):
        with self.array_writer("ps7_peripherals_init_data") as w:
            mio_enable_mask = 0
            # Set the GPIO reset masks up front to match vivado behavior
            for io in self.config.GPIO_RESETS:
                mio_enable_mask |= 1 << io

            def set_output_dir(io):
                nonlocal mio_enable_mask
                mio_enable_mask |= 1 << io
                if io < 32:
                    w.write(0xE000A204, mio_enable_mask & 0xFFFFFFFF)
                else:
                    w.write(0xE000A244, (mio_enable_mask >> 32) & 0xFFFFFFFF)
            def set_enable_output(io):
                assert mio_enable_mask & (1 << io)
                if io < 32:
                    w.write(0xE000A208, mio_enable_mask & 0xFFFFFFFF)
                else:
                    w.write(0xE000A248, (mio_enable_mask >> 32) & 0xFFFFFFFF)
            def init_reset(io):
                set_output_dir(io)
                self.set_mio(w, io, True)
                set_enable_output(io)
                self.set_mio(w, io, False)
                self.delay(w, 1)
                self.set_mio(w, io, True)

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
            if self.config.NOR_ENABLE:
                # XNANDPS_SET_OPMODE_OFFSET
                # [12:12] set_bls = 1
                w.maskwrite(0XE000E018, 0x00001000, 0x00001000)
            # FINISH: SRAM/NOR SET OPMODE
            # START: UART REGISTERS
            if self.config.UART0_ENABLE:
                bdiv, cd = self.get_uart_bdiv_cd(self.config.UART0_BAUD_RATE)
                # [7:0] BDIV
                w.maskwrite(0xE0000034, 0x000000FF, bdiv)
                # [15:0] CD
                w.maskwrite(0xE0000018, 0x0000FFFF, cd)
                # [8:8] STPBRK = 0x0
                # [7:7] STTBRK = 0x0
                # [6:6] RSTTO = 0x0
                # [5:5] TXDIS = 0x0
                # [4:4] TXEN = 0x1
                # [3:3] RXDIS = 0x0
                # [2:2] RXEN = 0x1
                # [1:1] TXRES = 0x1
                # [0:0] RXRES = 0x1
                w.maskwrite(0xE0000000, 0x000001FF, 0x00000017)
                # [11:11] IRMODE = 0x0 (Version: 1/2)
                # [10:10] UCLKEN = 0x0 (Version: 1/2)
                # [9:8] CHMODE = 0x0
                # [7:6] NBSTOP = 0x0
                # [5:3] PAR = 0x4
                # [2:1] CHRL = 0x0
                # [0:0] CLKS = 0x0
                if self.version >= 3:
                    w.maskwrite(0xE0000004, 0x000003FF, 0x00000020)
                else:
                    w.maskwrite(0xE0000004, 0x00000FFF, 0x00000020)
            if self.config.UART1_ENABLE:
                bdiv, cd = self.get_uart_bdiv_cd(self.config.UART1_BAUD_RATE)
                # [7:0] BDIV
                w.maskwrite(0xE0001034, 0x000000FF, bdiv)
                # [15:0] CD
                w.maskwrite(0xE0001018, 0x0000FFFF, cd)
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
            if self.config.NAND_ENABLE:
                # .. START: NAND SET CYCLE
                # XNANDPS_SET_CYCLES_OFFSET
                w.write(0xE000E014, self.config.NAND_CYCLES.get_reg())
                # .. FINISH: NAND SET CYCLE
                # .. START: OPMODE
                # XNANDPS_SET_OPMODE_OFFSET
                # [1:0] set_mw = NAND_D8_ENABLE
                w.maskwrite(0xE000E018, 0x00000003,
                            self.config.NAND_D8_ENABLE)
                # .. FINISH: OPMODE
                # .. START: DIRECT COMMAND
                # XNANDPS_DIRECT_CMD_OFFSET
                # [25:23] chip_select = 0x4
                # [22:21] cmd_type = 0x2
                w.write(0xE000E010, 0x02400000)
                # .. FINISH: DIRECT COMMAND
            if self.config.NOR_ENABLE and self.config.NOR_CS0_ENABLE:
                # .. START: SRAM/NOR CS0 SET CYCLE
                # XNANDPS_SET_CYCLES_OFFSET
                w.write(0xE000E014, self.config.NOR_CS0_CYCLES.get_reg())
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
            if self.config.NOR_ENABLE and self.config.NOR_CS1_ENABLE:
                # .. START: SRAM/NOR CS1 SET CYCLE
                # XNANDPS_SET_CYCLES_OFFSET
                w.write(0xE000E014, self.config.NOR_CS1_CYCLES.get_reg())
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
            for io in self.config.GPIO_RESETS:
                init_reset(io)
            if self.config.NOR_ENABLE and self.config.NOR_A25_ENABLE:
                # .. START: NOR CHIP SELECT
                set_output_dir(0)
                self.set_mio(w, 0, False)
                set_enable_output(0)
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
            w.write(0xF8000240, 0x00000000)
            # FINISH: FPGA RESETS TO 0
            if self.config.GP0_AXI_NONSECURE:
                # security_gp0_axi
                # gp0_axi = 1
                w.write(0XF890001C, 0x00000001)
            if self.config.GP1_AXI_NONSECURE:
                # security_gp1_axi
                # gp1_axi = 1
                w.write(0XF8900020, 0x00000001)
            w.lock()

    def debug(self):
        with self.array_writer("ps7_debug") as w:
            # DEBUG_CPU_CTI0
            w.write(0xF8898FB0, 0xC5ACCE55)
            # DEBUG_CPU_CTI1
            w.write(0xF8899FB0, 0xC5ACCE55)
            # DEBUG_CTI_FTM
            w.write(0xF8809FB0, 0xC5ACCE55)

def write_ps_init_gen_h(io, config):
    def write_freq(name, freqmhz):
        print(f'#define {name}_FREQ {round(freqmhz * 1e6)}', file=io)
    write_freq('APU', config.CPU_FREQMHZ)
    write_freq('DDR', config.DDR_FREQMHZ)
    write_freq('DCI', config.DCI_FREQMHZ)
    write_freq('QSPI', config.QSPI_FREQMHZ)
    write_freq('SMC', config.SMC_FREQMHZ)
    write_freq('SDIO', config.SDIO_FREQMHZ)
    write_freq('UART', config.UART_FREQMHZ)
    write_freq('SPI', config.SPI_FREQMHZ)
    write_freq('CAN', config.CAN_FREQMHZ)
    write_freq('PCAP', config.PCAP_FREQMHZ)
    for i in range(4):
        write_freq(f'FPGA{i}', config.FCLK[i].FREQMHZ)

class XParametersWriter:
    def __init__(self, io, config):
        self.io = io
        self.config = config

    def write_def(self, name, val):
        print(f'#define {name} {val}', file=self.io)

    def write_dev_id(self, prefix, id):
        self.write_def(f'{prefix}_DEVICE_ID', id)

    def write_freq_hz(self, prefix, freqmhz):
        self.write_def(f'{prefix}_CLK_FREQ_HZ', round(freqmhz * 1e6))

    def write_addr_range(self, prefix, base, diff=0xfff):
        self.write_def(f'{prefix}_BASEADDR', f'0x{base:08X}')
        self.write_def(f'{prefix}_HIGHADDR', f'0x{base + diff:08X}')

    def write_all(self):
        print("""
#ifndef XPARAMETERS_H   /* prevent circular inclusions */
#define XPARAMETERS_H   /* by using protection macros */

#ifdef __cplusplus
extern "C" {
#endif

/* Definition for CPU ID */
#define XPAR_CPU_ID 0U
""", file=self.io)

        self.write_freq_hz('XPAR_PS7_CORTEXA9_0_CPU', self.config.CPU_FREQMHZ)
        self.write_freq_hz('XPAR_CPU_CORTEXA9_0_CPU', self.config.CPU_FREQMHZ)

        print("""
#include "xparameters_ps.h"

#define STDIN_BASEADDRESS 0xE0001000
#define STDOUT_BASEADDRESS 0xE0001000

/* Platform specific definitions */
#define PLATFORM_ZYNQ

/* Definitions for sleep timer configuration */
#define XSLEEP_TIMER_IS_DEFAULT_TIMER
""", file=self.io)

        self.write_can()

        print("""
/* Definitions for peripheral PS7_DDR_0 */
#define XPAR_PS7_DDR_0_S_AXI_BASEADDR 0x00100000
#define XPAR_PS7_DDR_0_S_AXI_HIGHADDR 0x3FFFFFFF

/* Definitions for driver DEVCFG */
#define XPAR_XDCFG_NUM_INSTANCES 1U

/* Definitions for peripheral PS7_DEV_CFG_0 */
#define XPAR_PS7_DEV_CFG_0_DEVICE_ID 0U
#define XPAR_PS7_DEV_CFG_0_BASEADDR 0xF8007000U
#define XPAR_PS7_DEV_CFG_0_HIGHADDR 0xF80070FFU

/* Canonical definitions for peripheral PS7_DEV_CFG_0 */
#define XPAR_XDCFG_0_DEVICE_ID XPAR_PS7_DEV_CFG_0_DEVICE_ID
#define XPAR_XDCFG_0_BASEADDR 0xF8007000U
#define XPAR_XDCFG_0_HIGHADDR 0xF80070FFU

/* Definitions for driver DMAPS */
#define XPAR_XDMAPS_NUM_INSTANCES 2

/* Definitions for peripheral PS7_DMA_NS */
#define XPAR_PS7_DMA_NS_DEVICE_ID 0
#define XPAR_PS7_DMA_NS_BASEADDR 0xF8004000
#define XPAR_PS7_DMA_NS_HIGHADDR 0xF8004FFF


/* Definitions for peripheral PS7_DMA_S */
#define XPAR_PS7_DMA_S_DEVICE_ID 1
#define XPAR_PS7_DMA_S_BASEADDR 0xF8003000
#define XPAR_PS7_DMA_S_HIGHADDR 0xF8003FFF

/* Canonical definitions for peripheral PS7_DMA_NS */
#define XPAR_XDMAPS_0_DEVICE_ID XPAR_PS7_DMA_NS_DEVICE_ID
#define XPAR_XDMAPS_0_BASEADDR 0xF8004000
#define XPAR_XDMAPS_0_HIGHADDR 0xF8004FFF

/* Canonical definitions for peripheral PS7_DMA_S */
#define XPAR_XDMAPS_1_DEVICE_ID XPAR_PS7_DMA_S_DEVICE_ID
#define XPAR_XDMAPS_1_BASEADDR 0xF8003000
#define XPAR_XDMAPS_1_HIGHADDR 0xF8003FFF
""", file=self.io)

        self.write_enet()

        print("""
/* Definitions for peripheral PS7_AFI_0 */
#define XPAR_PS7_AFI_0_S_AXI_BASEADDR 0xF8008000
#define XPAR_PS7_AFI_0_S_AXI_HIGHADDR 0xF8008FFF


/* Definitions for peripheral PS7_AFI_1 */
#define XPAR_PS7_AFI_1_S_AXI_BASEADDR 0xF8009000
#define XPAR_PS7_AFI_1_S_AXI_HIGHADDR 0xF8009FFF


/* Definitions for peripheral PS7_AFI_2 */
#define XPAR_PS7_AFI_2_S_AXI_BASEADDR 0xF800A000
#define XPAR_PS7_AFI_2_S_AXI_HIGHADDR 0xF800AFFF


/* Definitions for peripheral PS7_AFI_3 */
#define XPAR_PS7_AFI_3_S_AXI_BASEADDR 0xF800B000
#define XPAR_PS7_AFI_3_S_AXI_HIGHADDR 0xF800BFFF


/* Definitions for peripheral PS7_DDRC_0 */
#define XPAR_PS7_DDRC_0_S_AXI_BASEADDR 0xF8006000
#define XPAR_PS7_DDRC_0_S_AXI_HIGHADDR 0xF8006FFF


/* Definitions for peripheral PS7_GLOBALTIMER_0 */
#define XPAR_PS7_GLOBALTIMER_0_S_AXI_BASEADDR 0xF8F00200
#define XPAR_PS7_GLOBALTIMER_0_S_AXI_HIGHADDR 0xF8F002FF


/* Definitions for peripheral PS7_GPV_0 */
#define XPAR_PS7_GPV_0_S_AXI_BASEADDR 0xF8900000
#define XPAR_PS7_GPV_0_S_AXI_HIGHADDR 0xF89FFFFF


/* Definitions for peripheral PS7_INTC_DIST_0 */
#define XPAR_PS7_INTC_DIST_0_S_AXI_BASEADDR 0xF8F01000
#define XPAR_PS7_INTC_DIST_0_S_AXI_HIGHADDR 0xF8F01FFF


/* Definitions for peripheral PS7_IOP_BUS_CONFIG_0 */
#define XPAR_PS7_IOP_BUS_CONFIG_0_S_AXI_BASEADDR 0xE0200000
#define XPAR_PS7_IOP_BUS_CONFIG_0_S_AXI_HIGHADDR 0xE0200FFF


/* Definitions for peripheral PS7_L2CACHEC_0 */
#define XPAR_PS7_L2CACHEC_0_S_AXI_BASEADDR 0xF8F02000
#define XPAR_PS7_L2CACHEC_0_S_AXI_HIGHADDR 0xF8F02FFF


/* Definitions for peripheral PS7_OCMC_0 */
#define XPAR_PS7_OCMC_0_S_AXI_BASEADDR 0xF800C000
#define XPAR_PS7_OCMC_0_S_AXI_HIGHADDR 0xF800CFFF


/* Definitions for peripheral PS7_PL310_0 */
#define XPAR_PS7_PL310_0_S_AXI_BASEADDR 0xF8F02000
#define XPAR_PS7_PL310_0_S_AXI_HIGHADDR 0xF8F02FFF


/* Definitions for peripheral PS7_PMU_0 */
#define XPAR_PS7_PMU_0_S_AXI_BASEADDR 0xF8891000
#define XPAR_PS7_PMU_0_S_AXI_HIGHADDR 0xF8891FFF
#define XPAR_PS7_PMU_0_PMU1_S_AXI_BASEADDR 0xF8893000
#define XPAR_PS7_PMU_0_PMU1_S_AXI_HIGHADDR 0xF8893FFF


/* Definitions for peripheral PS7_QSPI_LINEAR_0 */
#define XPAR_PS7_QSPI_LINEAR_0_S_AXI_BASEADDR 0xFC000000
#define XPAR_PS7_QSPI_LINEAR_0_S_AXI_HIGHADDR 0xFCFFFFFF


/* Definitions for peripheral PS7_RAM_0 */
#define XPAR_PS7_RAM_0_S_AXI_BASEADDR 0x00000000
#define XPAR_PS7_RAM_0_S_AXI_HIGHADDR 0x0003FFFF


/* Definitions for peripheral PS7_RAM_1 */
#define XPAR_PS7_RAM_1_S_AXI_BASEADDR 0xFFFC0000
#define XPAR_PS7_RAM_1_S_AXI_HIGHADDR 0xFFFFFFFF


/* Definitions for peripheral PS7_SCUC_0 */
#define XPAR_PS7_SCUC_0_S_AXI_BASEADDR 0xF8F00000
#define XPAR_PS7_SCUC_0_S_AXI_HIGHADDR 0xF8F000FC


/* Definitions for peripheral PS7_SLCR_0 */
#define XPAR_PS7_SLCR_0_S_AXI_BASEADDR 0xF8000000
#define XPAR_PS7_SLCR_0_S_AXI_HIGHADDR 0xF8000FFF

/* Definitions for driver GPIOPS */
#define XPAR_XGPIOPS_NUM_INSTANCES 1

/* Definitions for peripheral PS7_GPIO_0 */
#define XPAR_PS7_GPIO_0_DEVICE_ID 0
#define XPAR_PS7_GPIO_0_BASEADDR 0xE000A000
#define XPAR_PS7_GPIO_0_HIGHADDR 0xE000AFFF


/******************************************************************/

/* Canonical definitions for peripheral PS7_GPIO_0 */
#define XPAR_XGPIOPS_0_DEVICE_ID XPAR_PS7_GPIO_0_DEVICE_ID
#define XPAR_XGPIOPS_0_BASEADDR 0xE000A000
#define XPAR_XGPIOPS_0_HIGHADDR 0xE000AFFF
""", file=self.io)

        self.write_i2c()
        self.write_qspi()

        print("""
/* Definitions for driver SCUGIC */
#define XPAR_XSCUGIC_NUM_INSTANCES 1U

/* Definitions for peripheral PS7_SCUGIC_0 */
#define XPAR_PS7_SCUGIC_0_DEVICE_ID 0U
#define XPAR_PS7_SCUGIC_0_BASEADDR 0xF8F00100U
#define XPAR_PS7_SCUGIC_0_HIGHADDR 0xF8F001FFU
#define XPAR_PS7_SCUGIC_0_DIST_BASEADDR 0xF8F01000U

/* Canonical definitions for peripheral PS7_SCUGIC_0 */
#define XPAR_SCUGIC_0_DEVICE_ID 0U
#define XPAR_SCUGIC_0_CPU_BASEADDR 0xF8F00100U
#define XPAR_SCUGIC_0_CPU_HIGHADDR 0xF8F001FFU
#define XPAR_SCUGIC_0_DIST_BASEADDR 0xF8F01000U

/* Definitions for driver SCUTIMER */
#define XPAR_XSCUTIMER_NUM_INSTANCES 1

/* Definitions for peripheral PS7_SCUTIMER_0 */
#define XPAR_PS7_SCUTIMER_0_DEVICE_ID 0
#define XPAR_PS7_SCUTIMER_0_BASEADDR 0xF8F00600
#define XPAR_PS7_SCUTIMER_0_HIGHADDR 0xF8F0061F

/* Canonical definitions for peripheral PS7_SCUTIMER_0 */
#define XPAR_XSCUTIMER_0_DEVICE_ID XPAR_PS7_SCUTIMER_0_DEVICE_ID
#define XPAR_XSCUTIMER_0_BASEADDR 0xF8F00600
#define XPAR_XSCUTIMER_0_HIGHADDR 0xF8F0061F

/* Definitions for driver SCUWDT */
#define XPAR_XSCUWDT_NUM_INSTANCES 1

/* Definitions for peripheral PS7_SCUWDT_0 */
#define XPAR_PS7_SCUWDT_0_DEVICE_ID 0
#define XPAR_PS7_SCUWDT_0_BASEADDR 0xF8F00620
#define XPAR_PS7_SCUWDT_0_HIGHADDR 0xF8F006FF

/* Canonical definitions for peripheral PS7_SCUWDT_0 */
#define XPAR_SCUWDT_0_DEVICE_ID XPAR_PS7_SCUWDT_0_DEVICE_ID
#define XPAR_SCUWDT_0_BASEADDR 0xF8F00620
#define XPAR_SCUWDT_0_HIGHADDR 0xF8F006FF
""", file=self.io)

        self.write_sd()

        print("""
/* Definitions for driver TTCPS */
#define XPAR_XTTCPS_NUM_INSTANCES 3U

/* Definitions for peripheral PS7_TTC_0 */
#define XPAR_PS7_TTC_0_DEVICE_ID 0U
#define XPAR_PS7_TTC_0_BASEADDR 0XF8001000U
#define XPAR_PS7_TTC_0_TTC_CLK_FREQ_HZ 111111115U
#define XPAR_PS7_TTC_0_TTC_CLK_CLKSRC 0U
#define XPAR_PS7_TTC_1_DEVICE_ID 1U
#define XPAR_PS7_TTC_1_BASEADDR 0XF8001004U
#define XPAR_PS7_TTC_1_TTC_CLK_FREQ_HZ 111111115U
#define XPAR_PS7_TTC_1_TTC_CLK_CLKSRC 0U
#define XPAR_PS7_TTC_2_DEVICE_ID 2U
#define XPAR_PS7_TTC_2_BASEADDR 0XF8001008U
#define XPAR_PS7_TTC_2_TTC_CLK_FREQ_HZ 111111115U
#define XPAR_PS7_TTC_2_TTC_CLK_CLKSRC 0U

/* Canonical definitions for peripheral PS7_TTC_0 */
#define XPAR_XTTCPS_0_DEVICE_ID XPAR_PS7_TTC_0_DEVICE_ID
#define XPAR_XTTCPS_0_BASEADDR 0xF8001000U
#define XPAR_XTTCPS_0_TTC_CLK_FREQ_HZ 111111115U
#define XPAR_XTTCPS_0_TTC_CLK_CLKSRC 0U

#define XPAR_XTTCPS_1_DEVICE_ID XPAR_PS7_TTC_1_DEVICE_ID
#define XPAR_XTTCPS_1_BASEADDR 0xF8001004U
#define XPAR_XTTCPS_1_TTC_CLK_FREQ_HZ 111111115U
#define XPAR_XTTCPS_1_TTC_CLK_CLKSRC 0U

#define XPAR_XTTCPS_2_DEVICE_ID XPAR_PS7_TTC_2_DEVICE_ID
#define XPAR_XTTCPS_2_BASEADDR 0xF8001008U
#define XPAR_XTTCPS_2_TTC_CLK_FREQ_HZ 111111115U
#define XPAR_XTTCPS_2_TTC_CLK_CLKSRC 0U
""", file=self.io)

        self.write_uart()
        self.write_usb()

        print("""
/* Canonical definitions for peripheral PS7_USB_0 */
#define XPAR_XUSBPS_0_DEVICE_ID XPAR_PS7_USB_0_DEVICE_ID
#define XPAR_XUSBPS_0_BASEADDR 0xE0002000
#define XPAR_XUSBPS_0_HIGHADDR 0xE0002FFF

/* Definitions for driver XADCPS */
#define XPAR_XADCPS_NUM_INSTANCES 1

/* Definitions for peripheral PS7_XADC_0 */
#define XPAR_PS7_XADC_0_DEVICE_ID 0
#define XPAR_PS7_XADC_0_BASEADDR 0xF8007100
#define XPAR_PS7_XADC_0_HIGHADDR 0xF8007120

/* Canonical definitions for peripheral PS7_XADC_0 */
#define XPAR_XADCPS_0_DEVICE_ID XPAR_PS7_XADC_0_DEVICE_ID
#define XPAR_XADCPS_0_BASEADDR 0xF8007100
#define XPAR_XADCPS_0_HIGHADDR 0xF8007120

/* Xilinx FAT File System Library (XilFFs) User Settings */
#define FILE_SYSTEM_INTERFACE_SD
#define FILE_SYSTEM_USE_MKFS
#define FILE_SYSTEM_NUM_LOGIC_VOL 2
#define FILE_SYSTEM_USE_STRFUNC 0
#define FILE_SYSTEM_SET_FS_RPATH 0
#define FILE_SYSTEM_WORD_ACCESS

#ifdef __cplusplus
}
#endif

#endif  /* end of protection macro */
""", file=self.io)

    def _write_can_prefix(self, prefix, idx, base):
        self.write_dev_id(f'{prefix}_{idx}', idx)
        self.write_addr_range(f'{prefix}_{idx}', base)
        self.write_freq_hz(f'{prefix}_{idx}_CAN', self.config.CAN_FREQMHZ)

    def _write_can(self, idx, base):
        self._write_can_prefix('XPAR_PS7_CAN', idx, base)
        self._write_can_prefix('XPAR_XCANPS', idx, base)

    def write_can(self):
        num_instances = self.config.CAN0_ENABLE + self.config.CAN1_ENABLE
        if num_instances == 0:
            return
        self.write_def('XPAR_XCANPS_NUM_INSTANCES', num_instances)
        idx = 0
        if self.config.CAN0_ENABLE:
            self._write_can(idx, 0xE0008000)
            idx += 1
        if self.config.CAN1_ENABLE:
            self._write_can(idx, 0xE0009000)

    def _write_enet_prefix(self, prefix, idx, base):
        self.write_dev_id(f'{prefix}_{idx}', idx)
        self.write_addr_range(f'{prefix}_{idx}', base)
        # Not 100% how these are computed yet,
        # especially if the clock is using external source
        print(f"""
#define {prefix}_{idx}_ENET_CLK_FREQ_HZ 25000000
#define {prefix}_{idx}_ENET_SLCR_1000MBPS_DIV0 8
#define {prefix}_{idx}_ENET_SLCR_1000MBPS_DIV1 1
#define {prefix}_{idx}_ENET_SLCR_100MBPS_DIV0 8
#define {prefix}_{idx}_ENET_SLCR_100MBPS_DIV1 5
#define {prefix}_{idx}_ENET_SLCR_10MBPS_DIV0 8
#define {prefix}_{idx}_ENET_SLCR_10MBPS_DIV1 50
#define {prefix}_{idx}_ENET_TSU_CLK_FREQ_HZ 0
#define {prefix}_{idx}_IS_CACHE_COHERENT 0
""", file=self.io)

    def _write_enet(self, idx, base):
        self.write_dev_id(f'XPAR_PS7_ETHERNET_{idx}', idx)
        self.write_addr_range(f'XPAR_PS7_ETHERNET_{idx}', base)
        # Not 100% how these are computed yet,
        # especially if the clock is using external source
        print(f"""
#define XPAR_PS7_ETHERNET_{idx}_ENET_CLK_FREQ_HZ 25000000
#define XPAR_PS7_ETHERNET_{idx}_ENET_SLCR_1000MBPS_DIV0 8
#define XPAR_PS7_ETHERNET_{idx}_ENET_SLCR_1000MBPS_DIV1 1
#define XPAR_PS7_ETHERNET_{idx}_ENET_SLCR_100MBPS_DIV0 8
#define XPAR_PS7_ETHERNET_{idx}_ENET_SLCR_100MBPS_DIV1 5
#define XPAR_PS7_ETHERNET_{idx}_ENET_SLCR_10MBPS_DIV0 8
#define XPAR_PS7_ETHERNET_{idx}_ENET_SLCR_10MBPS_DIV1 50
#define XPAR_PS7_ETHERNET_{idx}_ENET_TSU_CLK_FREQ_HZ 0
#define XPAR_PS7_ETHERNET_{idx}_IS_CACHE_COHERENT 0
""", file=self.io)

        self.write_dev_id(f'XPAR_XEMACPS_{idx}', idx)
        self.write_addr_range(f'XPAR_XEMACPS_{idx}', base)
        # Not 100% how these are computed yet,
        # especially if the clock is using external source
        print(f"""
#define XPAR_XEMACPS_{idx}_ENET_CLK_FREQ_HZ 25000000
#define XPAR_XEMACPS_{idx}_ENET_SLCR_1000Mbps_DIV0 8
#define XPAR_XEMACPS_{idx}_ENET_SLCR_1000Mbps_DIV1 1
#define XPAR_XEMACPS_{idx}_ENET_SLCR_100Mbps_DIV0 8
#define XPAR_XEMACPS_{idx}_ENET_SLCR_100Mbps_DIV1 5
#define XPAR_XEMACPS_{idx}_ENET_SLCR_10Mbps_DIV0 8
#define XPAR_XEMACPS_{idx}_ENET_SLCR_10Mbps_DIV1 50
#define XPAR_XEMACPS_{idx}_ENET_TSU_CLK_FREQ_HZ 0
#define XPAR_XEMACPS_{idx}_IS_CACHE_COHERENT 0
""", file=self.io)

    def write_enet(self):
        num_instances = self.config.ENET0_ENABLE + self.config.ENET1_ENABLE
        if num_instances == 0:
            return
        self.write_def('XPAR_XEMACPS_NUM_INSTANCES', num_instances)
        idx = 0
        if self.config.ENET0_ENABLE:
            self._write_enet(idx, 0xE000B000)
            idx += 1
        if self.config.ENET1_ENABLE:
            self._write_enet(idx, 0xE000C000)

    def _write_i2c_prefix(self, prefix, idx, base):
        self.write_dev_id(f'{prefix}_{idx}', idx)
        self.write_addr_range(f'{prefix}_{idx}', base)
        # Hard code for now
        self.write_freq_hz(f'{prefix}_{idx}_I2C', 111.111111)

    def _write_i2c(self, idx, base):
        self._write_i2c_prefix('XPAR_PS7_I2C', idx, base)
        self._write_i2c_prefix('XPAR_XIICPS', idx, base)

    def write_i2c(self):
        num_instances = self.config.I2C0_ENABLE + self.config.I2C1_ENABLE
        if num_instances == 0:
            return
        self.write_def('XPAR_XIICPS_NUM_INSTANCES', num_instances)
        idx = 0
        if self.config.I2C0_ENABLE:
            self._write_i2c(idx, 0xE0004000)
            idx += 1
        if self.config.I2C1_ENABLE:
            self._write_i2c(idx, 0xE0005000)

    def _write_qspi_prefix(self, prefix, idx, base):
        self.write_dev_id(f'{prefix}_{idx}', idx)
        self.write_addr_range(f'{prefix}_{idx}', base)
        self.write_freq_hz(f'{prefix}_{idx}_QSPI', self.config.QSPI_FREQMHZ)
        qspi_mode = self.config.QSPI_MODE
        if qspi_mode in (QSPIMode.Single_x1, QSPIMode.Single_x2, QSPIMode.Single_x4):
            mode = 0
        elif qspi_mode in (QSPIMode.Dual_x1, QSPIMode.Dual_x2, QSPIMode.Dual_x4):
            mode = 1
        else:
            mode = 2
        self.write_def(f'{prefix}_{idx}_QSPI_MODE', mode)

        if qspi_mode in (QSPIMode.Single_x1, QSPIMode.Dual_x1):
            width = 0
        if qspi_mode in (QSPIMode.Single_x2, QSPIMode.Dual_x2):
            width = 1
        if qspi_mode in (QSPIMode.Single_x4, QSPIMode.Dual_x4):
            width = 2
        else:
            width = 3
        self.write_def(f'{prefix}_{idx}_QSPI_BUS_WIDTH', width)

    def _write_qspi(self, idx, base):
        self._write_qspi_prefix('XPAR_PS7_QSPI', idx, base)
        self._write_qspi_prefix('XPAR_XQSPIPS', idx, base)

    def write_qspi(self):
        if not self.config.QSPI_ENABLE:
            return
        self.write_def('XPAR_XQSPIPS_NUM_INSTANCES', 1)
        self._write_qspi(0, 0xE000D000)

    def _write_sd_prefix(self, prefix, idx, base):
        self.write_dev_id(f'{prefix}_{idx}', idx)
        self.write_addr_range(f'{prefix}_{idx}', base)
        self.write_freq_hz(f'{prefix}_{idx}_SDIO', self.config.SDIO_FREQMHZ)
        print(f"""
#define {prefix}_{idx}_HAS_CD 1
#define {prefix}_{idx}_HAS_WP 1
#define {prefix}_{idx}_BUS_WIDTH 0
""", file=self.io)
        if getattr(self.config, f'SD{idx}_IO').value > 0:
            print(f"""
#define {prefix}_{idx}_MIO_BANK 0
#define {prefix}_{idx}_HAS_EMIO 0
""", file=self.io)
        else:
            print(f"""
#define {prefix}_{idx}_MIO_BANK 2
#define {prefix}_{idx}_HAS_EMIO 1
""", file=self.io)
        print(f"""
#define {prefix}_{idx}_SLOT_TYPE 0
#define {prefix}_{idx}_CLK_50_SDR_ITAP_DLY 0
#define {prefix}_{idx}_CLK_50_SDR_OTAP_DLY 0
#define {prefix}_{idx}_CLK_50_DDR_ITAP_DLY 0
#define {prefix}_{idx}_CLK_50_DDR_OTAP_DLY 0
#define {prefix}_{idx}_CLK_100_SDR_OTAP_DLY 0
#define {prefix}_{idx}_CLK_200_SDR_OTAP_DLY 0
#define {prefix}_{idx}_CLK_200_DDR_OTAP_DLY 0
#define {prefix}_{idx}_IS_CACHE_COHERENT 0
""", file=self.io)

    def _write_sd(self, idx, base):
        self._write_sd_prefix('XPAR_PS7_SD', idx, base)
        self._write_sd_prefix('XPAR_XSDPS', idx, base)

    def write_sd(self):
        num_instances = self.config.SD0_ENABLE + self.config.SD1_ENABLE
        if num_instances == 0:
            return
        self.write_def('XPAR_XSDPS_NUM_INSTANCES', num_instances)
        idx = 0
        if self.config.SD0_ENABLE:
            self._write_sd(idx, 0xE0100000)
            idx += 1
        if self.config.SD1_ENABLE:
            self._write_sd(idx, 0xE0101000)

    def _write_uart_prefix(self, prefix, idx, base):
        self.write_dev_id(f'{prefix}_{idx}', idx)
        self.write_addr_range(f'{prefix}_{idx}', base)
        self.write_freq_hz(f'{prefix}_{idx}_UART', self.config.UART_FREQMHZ)
        self.write_def(f'{prefix}_{idx}_HAS_MODEM', 0)

    def _write_uart(self, idx, base):
        self._write_uart_prefix('XPAR_PS7_UART', idx, base)
        self._write_uart_prefix('XPAR_XUARTPS', idx, base)

    def write_uart(self):
        num_instances = self.config.UART0_ENABLE + self.config.UART1_ENABLE
        if num_instances == 0:
            return
        self.write_def('XPAR_XUARTPS_NUM_INSTANCES', num_instances)
        idx = 0
        if self.config.UART0_ENABLE:
            self._write_uart(idx, 0xE0000000)
            idx += 1
        if self.config.UART1_ENABLE:
            self._write_uart(idx, 0xE0001000)

    def _write_usb_prefix(self, prefix, idx, base):
        self.write_dev_id(f'{prefix}_{idx}', idx)
        self.write_addr_range(f'{prefix}_{idx}', base)

    def _write_usb(self, idx, base):
        self._write_usb_prefix('XPAR_PS7_USB', idx, base)

    def write_usb(self):
        num_instances = self.config.USB0_ENABLE + self.config.USB1_ENABLE
        if num_instances == 0:
            return
        self.write_def('XPAR_XUSBPS_NUM_INSTANCES', num_instances)
        idx = 0
        if self.config.USB0_ENABLE:
            self._write_usb(idx, 0xE0002000)
            idx += 1
        if self.config.USB1_ENABLE:
            self._write_usb(idx, 0xE0003000)

def gen_board_files(outputdir, config):
    outputdir = Path(outputdir)
    outputdir.mkdir(parents=True, exist_ok=True)

    data_path = Path(__file__).resolve().parent / "data" / "zynq_fsbl"
    for f in data_path.iterdir():
        shutil.copy2(f, outputdir)

    with open(outputdir / "ps7_init_gen.h", "w") as io:
        write_ps_init_gen_h(io, config)

    with open(outputdir / "xparameters.h", "w") as io:
        XParametersWriter(io, config).write_all()

    with open(outputdir / "ps7_init_gen.c", "w") as io:
        DataWriter(io, 1, config).write_all()
        DataWriter(io, 2, config).write_all()
        DataWriter(io, 3, config).write_all()
