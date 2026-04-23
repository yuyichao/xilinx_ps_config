/******************************************************************************
 *
 * Copyright (C) 2018 Xilinx, Inc.  All rights reserved.
 *
 *  This program is free software; you can redistribute it and/or modify
 *  it under the terms of the GNU General Public License as published by
 *  the Free Software Foundation; either version 2 of the License, or
 *  (at your option) any later version.
 *
 *  This program is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *  GNU General Public License for more details.
 *
 *  You should have received a copy of the GNU General Public License along
 *  with this program; if not, see <http://www.gnu.org/licenses/>
 *
 *
 ******************************************************************************/
/****************************************************************************/
/**
 *
 * @file ps7_init.h
 *
 * This file can be included in FSBL code
 * to get prototype of ps7_init() function
 * and error codes
 *
 *****************************************************************************/

#ifdef __cplusplus
extern "C" {
#endif

/* Returns codes  of PS7_Init */
#define PS7_INIT_SUCCESS   (0)    // 0 is success in good old C
#define PS7_INIT_CORRUPT   (1)    // 1 the data is corrupted, and slcr reg are in corrupted state now
#define PS7_INIT_TIMEOUT   (2)    // 2 when a poll operation timed out
#define PS7_POLL_FAILED_DDR_INIT (3)    // 3 when a poll operation timed out for ddr init
#define PS7_POLL_FAILED_DMA      (4)    // 4 when a poll operation timed out for dma done bit
#define PS7_POLL_FAILED_PLL      (5)    // 5 when a poll operation timed out for pll sequence init
#define NEW_PS7_ERR_CODE 1

/* Silicon Versions */
#define PCW_SILICON_VERSION_1 0
#define PCW_SILICON_VERSION_2 1
#define PCW_SILICON_VERSION_3 2

/* This flag to be used by FSBL to check whether ps7_post_config() proc exixts */
#define PS7_POST_CONFIG

#include "ps7_init_gen.h"

/* For delay calculation using global registers*/
#define SCU_GLOBAL_TIMER_COUNT_L32	0xF8F00200
#define SCU_GLOBAL_TIMER_COUNT_U32	0xF8F00204
#define SCU_GLOBAL_TIMER_CONTROL	0xF8F00208
#define SCU_GLOBAL_TIMER_AUTO_INC	0xF8F00218

int ps7_init();
int ps7_post_config();
int ps7_debug();
char* getPS7MessageInfo(unsigned key);

void perf_start_clock(void);
void perf_disable_clock(void);
void perf_reset_clock(void);
void perf_reset_and_start_timer();
int get_number_of_cycles_for_delay(unsigned int delay);
#ifdef __cplusplus
}
#endif
