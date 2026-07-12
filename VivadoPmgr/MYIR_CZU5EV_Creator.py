# -*- coding: utf-8 -*-
"""Create a non-RF lolenc FDM project for the MYD-CZU5EV-V2."""

import argparse
import logging
import os

from VivadoPmgr.Verilog_Creator import TVM, set_global_namespace
from VivadoPmgr.ZCU104_Creator import (
    ZCU104Maker,
    _as_bool,
    create_zcu104_maker,
)


MYIR_PART_NAME = "xczu5ev-sfvc784-2-i"

# MYIR's V2 SOM uses a 33.333333 MHz PS reference clock and four
# MT40A512M16 DDR4 components.  These high-level settings are the subset
# required by the non-RF FDM profile; Vivado derives version-specific clock
# and MIO tree properties from them.  An official MYIR preset Tcl can be
# supplied with ``ps_preset_tcl`` to replace this built-in profile.
MYIR_FDM_PS_CONFIG = {
    "PSU__PSS_REF_CLK__FREQMHZ": "33.33333333",
    "PSU__USE__DDR_INTF_REQUESTED": "0",
    "PSU__EN_AXI_STATUS_PORTS": "0",
    "PSU_BANK_0_IO_STANDARD": "LVCMOS18",
    "PSU_BANK_1_IO_STANDARD": "LVCMOS18",
    "PSU_BANK_2_IO_STANDARD": "LVCMOS18",
    "PSU_BANK_3_IO_STANDARD": "LVCMOS18",
    # Boot and management peripherals present on MYD-CZU5EV-V2.
    "PSU__QSPI__PERIPHERAL__ENABLE": "1",
    "PSU__QSPI__PERIPHERAL__IO": "MIO 0 .. 12",
    "PSU__QSPI__PERIPHERAL__MODE": "Dual Parallel",
    "PSU__QSPI__PERIPHERAL__DATA_MODE": "x4",
    "PSU__QSPI__GRP_FBCLK__ENABLE": "0",
    "PSU__SD0__PERIPHERAL__ENABLE": "1",
    "PSU__SD0__PERIPHERAL__IO": "MIO 13 .. 22",
    "PSU__SD0__GRP_POW__ENABLE": "1",
    "PSU__SD0__GRP_POW__IO": "MIO 23",
    "PSU__SD0__SLOT_TYPE": "eMMC",
    "PSU__SD0__RESET__ENABLE": "1",
    "PSU__SD0__DATA_TRANSFER_MODE": "8Bit",
    "PSU_SD0_INTERNAL_BUS_WIDTH": "8",
    "PSU__I2C1__PERIPHERAL__ENABLE": "1",
    "PSU__I2C1__PERIPHERAL__IO": "MIO 24 .. 25",
    "PSU__UART0__PERIPHERAL__ENABLE": "1",
    "PSU__UART0__PERIPHERAL__IO": "MIO 34 .. 35",
    "PSU__UART0__BAUD_RATE": "115200",
    "PSU__UART0__MODEM__ENABLE": "0",
    "PSU__SD1__PERIPHERAL__ENABLE": "1",
    "PSU__SD1__PERIPHERAL__IO": "MIO 46 .. 51",
    "PSU__SD1__GRP_CD__ENABLE": "1",
    "PSU__SD1__GRP_CD__IO": "MIO 45",
    "PSU__SD1__GRP_POW__ENABLE": "0",
    "PSU__SD1__GRP_WP__ENABLE": "1",
    "PSU__SD1__GRP_WP__IO": "MIO 44",
    "PSU__SD1__SLOT_TYPE": "SD 2.0",
    "PSU__SD1__DATA_TRANSFER_MODE": "4Bit",
    "PSU_SD1_INTERNAL_BUS_WIDTH": "4",
    "PSU__USB0__PERIPHERAL__ENABLE": "1",
    "PSU__USB0__PERIPHERAL__IO": "MIO 52 .. 63",
    "PSU__USB__RESET__MODE": "Boot Pin",
    "PSU__USB__RESET__POLARITY": "Active Low",
    "PSU__USB3_0__PERIPHERAL__ENABLE": "1",
    "PSU__USB3_0__PERIPHERAL__IO": "GT Lane2",
    "PSU__USB0__REF_CLK_SEL": "Ref Clk2",
    "PSU__USB0__REF_CLK_FREQ": "52",
    "PSU__ENET3__PERIPHERAL__ENABLE": "1",
    "PSU__ENET3__FIFO__ENABLE": "0",
    "PSU__ENET3__PTP__ENABLE": "0",
    "PSU__ENET3__PERIPHERAL__IO": "MIO 64 .. 75",
    "PSU__ENET3__GRP_MDIO__ENABLE": "1",
    "PSU__ENET3__GRP_MDIO__IO": "MIO 76 .. 77",
    # 4 GiB, 64-bit DDR4-2400 (four 8-Gbit x16 components).
    "PSU__ACT_DDR_FREQ_MHZ": "1200.000000",
    "PSU_DYNAMIC_DDR_CONFIG_EN": "0",
    "PSU__DDRC__AL": "0",
    "PSU__DDRC__BANK_ADDR_COUNT": "2",
    "PSU__DDRC__BUS_WIDTH": "64 Bit",
    "PSU__DDRC__CL": "16",
    "PSU__DDRC__CLOCK_STOP_EN": "0",
    "PSU__DDRC__COL_ADDR_COUNT": "10",
    "PSU__DDRC__RANK_ADDR_COUNT": "0",
    "PSU__DDRC__CWL": "12",
    "PSU__DDRC__BG_ADDR_COUNT": "1",
    "PSU__DDRC__DEVICE_CAPACITY": "8192 MBits",
    "PSU__DDRC__DRAM_WIDTH": "16 Bits",
    "PSU__DDRC__ECC": "Disabled",
    "PSU__DDRC__ENABLE": "1",
    "PSU__DDRC__MEMORY_TYPE": "DDR 4",
    "PSU__DDRC__ROW_ADDR_COUNT": "16",
    "PSU__DDRC__SPEED_BIN": "DDR4_2400R",
    "PSU__DDRC__T_FAW": "30.0",
    "PSU__DDRC__T_RAS_MIN": "32.0",
    "PSU__DDRC__T_RC": "45.32",
    "PSU__DDRC__T_RCD": "16",
    "PSU__DDRC__T_RP": "16",
    "PSU__DDRC__TRAIN_DATA_EYE": "1",
    "PSU__DDRC__TRAIN_READ_GATE": "1",
    "PSU__DDRC__TRAIN_WRITE_LEVEL": "1",
    "PSU__DDRC__VREF": "1",
    "PSU__DDRC__BRC_MAPPING": "ROW_BANK_COL",
    "PSU__DDRC__DDR4_T_REF_RANGE": "Normal (0-85)",
    "PSU__DDRC__PHY_DBI_MODE": "0",
    "PSU__DDRC__DM_DBI": "DM_NO_DBI",
    "PSU__DDRC__COMPONENTS": "Components",
    "PSU__DDRC__FGRM": "1X",
    "PSU__DDRC__VENDOR_PART": "OTHERS",
    "PSU__DDRC__SB_TARGET": "16-16-16",
    "PSU__DDRC__DDR4_ADDR_MAPPING": "1",
    "PSU__DDRC__ADDR_MIRROR": "0",
    "PSU__DDRC__EN_2ND_CLK": "0",
    "PSU__DDRC__ENABLE_2T_TIMING": "0",
    "PSU__DDRC__DQMAP_0_3": "0",
    "PSU__DDRC__DQMAP_4_7": "0",
    "PSU__DDRC__DQMAP_8_11": "0",
    "PSU__DDRC__DQMAP_12_15": "0",
    "PSU__DDRC__DQMAP_16_19": "0",
    "PSU__DDRC__DQMAP_20_23": "0",
    "PSU__DDRC__DQMAP_24_27": "0",
    "PSU__DDRC__DQMAP_28_31": "0",
    "PSU__DDRC__DQMAP_32_35": "0",
    "PSU__DDRC__DQMAP_36_39": "0",
    "PSU__DDRC__DQMAP_40_43": "0",
    "PSU__DDRC__DQMAP_44_47": "0",
    "PSU__DDRC__DQMAP_48_51": "0",
    "PSU__DDRC__DQMAP_52_55": "0",
    "PSU__DDRC__DQMAP_56_59": "0",
    "PSU__DDRC__DQMAP_60_63": "0",
    "PSU__DDRC__DQMAP_64_67": "0",
    "PSU__DDRC__DQMAP_68_71": "0",
    "PSU__HIGH_ADDRESS__ENABLE": "1",
    "PSU__DDR_HIGH_ADDRESS_GUI_ENABLE": "1",
    "PSU_DDR_RAM_HIGHADDR": "0xFFFFFFFF",
    "PSU_DDR_RAM_HIGHADDR_OFFSET": "0x800000000",
    "PSU_DDR_RAM_LOWADDR_OFFSET": "0x80000000",
}


class MYDCZU5EVMaker(ZCU104Maker):
    """MYD-CZU5EV-V2 implementation of the non-RF FDM profile."""

    platform_name = "MYD-CZU5EV-V2"

    def __init__(self, **kwargs):
        board_preset = kwargs.get("board_preset", True)
        ps_preset_tcl = kwargs.get("ps_preset_tcl")
        if board_preset:
            raise RuntimeError(
                "MYD-CZU5EV-V2 uses a PS preset, not Vivado board automation; "
                "set board_preset to false"
            )
        if TVM.part_name != MYIR_PART_NAME:
            raise RuntimeError(
                "MYD-CZU5EV-V2 requires part "
                f"{MYIR_PART_NAME}, got {TVM.part_name}"
            )
        if TVM.board_name is not None:
            raise RuntimeError(
                "MYD-CZU5EV-V2 has no installed Vivado board part; "
                "set board_name to null"
            )
        if ps_preset_tcl:
            preset_path = os.path.abspath(os.path.expanduser(ps_preset_tcl))
            if not os.path.isfile(preset_path):
                raise RuntimeError(
                    f"MYIR PS preset Tcl does not exist: {preset_path}"
                )

        # RFSoCMaker recreates its output directory, so all user/configuration
        # errors above must be rejected before entering the base constructor.
        super().__init__(**kwargs)
        self.ps_preset_tcl = ps_preset_tcl

    def _apply_processing_system_preset(self, cpu_cell) -> None:
        """Apply the MYIR PS configuration, then restore FDM overrides."""
        if self.ps_preset_tcl:
            preset_path = os.path.abspath(os.path.expanduser(self.ps_preset_tcl))
            if not os.path.isfile(preset_path):
                raise RuntimeError(
                    f"MYIR PS preset Tcl does not exist: {preset_path}"
                )
            preset_path = preset_path.replace("\\", "/")
            TVM.tcl_code += (
                f"source {{{preset_path}}}\n"
                "if {[llength [info procs apply_preset]] == 0} {\n"
                '  error "MYIR PS preset does not define apply_preset"\n'
                "}\n"
                "set myir_ps_preset [apply_preset 0]\n"
                f"set_property -dict $myir_ps_preset "
                f"[get_bd_cells {self.CPU}]\n"
            )
        else:
            self._emit_cpu_config(MYIR_FDM_PS_CONFIG)

        # The FDM AXI ports, interrupts, and PL clocks must win over the
        # vendor/built-in board preset.
        self._emit_cpu_config(cpu_cell.config)
        TVM.tcl_code += (
            "set myir_ps [get_bd_cells " + self.CPU + "]\n"
            "foreach {property expected} {\n"
            "  CONFIG.PSU__DDRC__BUS_WIDTH {64 Bit}\n"
            "  CONFIG.PSU__DDRC__MEMORY_TYPE {DDR 4}\n"
            "  CONFIG.PSU__DDRC__DEVICE_CAPACITY {8192 MBits}\n"
            "  CONFIG.PSU__USE__M_AXI_GP0 {1}\n"
            "  CONFIG.PSU__USE__S_AXI_GP2 {1}\n"
            "  CONFIG.PSU__FPGA_PL0_ENABLE {1}\n"
            "  CONFIG.PSU__FPGA_PL1_ENABLE {1}\n"
            "} {\n"
            "  set actual [get_property $property $myir_ps]\n"
            "  if {$actual ne $expected} {\n"
            '    error "MYIR PS property $property is $actual, expected '
            '$expected"\n'
            "  }\n"
            "}\n"
            "foreach pin {pl_clk0 pl_clk1 pl_ps_irq0} {\n"
            f"  if {{[llength [get_bd_pins -quiet {self.CPU}/$pin]] != 1}} {{\n"
            '    error "MYIR PS pin is unavailable: $pin"\n'
            "  }\n"
            "}\n"
            "foreach intf {M_AXI_HPM0_FPD S_AXI_HP0_FPD} {\n"
            f"  if {{[llength [get_bd_intf_pins -quiet {self.CPU}/$intf]] "
            "!= 1} {\n"
            '    error "MYIR PS interface is unavailable: $intf"\n'
            "  }\n"
            "}\n"
        )


def create_myd_czu5ev_maker(json_file: str) -> MYDCZU5EVMaker:
    """Build the MYD-CZU5EV-V2 maker from a lolenc SoC JSON file."""
    return create_zcu104_maker(json_file, maker_class=MYDCZU5EVMaker)


def main() -> None:
    """Command-line entry point for MYD-CZU5EV-V2 project generation."""
    parser = argparse.ArgumentParser(
        description="Create a non-RF lolenc FDM project for MYD-CZU5EV-V2"
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-c", "--config", help="Configuration JSON")
    parser.add_argument("-f", "--soc_json", help="MYD-CZU5EV-V2 SoC JSON")
    parser.add_argument(
        "-i", "--implementation", type=int, default=0,
        help="Vivado implementation job count; zero creates the project only",
    )
    parser.add_argument("-g", "--gui", type=_as_bool, default=True)
    parser.add_argument("-a", "--auto_connection", type=_as_bool, default=True)
    parser.add_argument(
        "-e", "--event_controller_option", type=_as_bool, default=True,
        help="Enable the FDM/Event Controller data paths",
    )
    args = parser.parse_args()

    if not args.auto_connection:
        parser.error("the MYD-CZU5EV-V2 FDM profile requires -a true")
    if not args.event_controller_option:
        parser.error("the MYD-CZU5EV-V2 FDM profile requires -e true")

    configuration = args.config or "configuration_MYD_CZU5EV_V2.json"
    soc_json = args.soc_json or "MYD_CZU5EV_FDM_Test.json"

    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)
    logging.warning("GUI Option: %s", args.gui)
    logging.warning("Auto Connection Option: %s", args.auto_connection)
    logging.warning("Event Controller Option: %s", args.event_controller_option)

    set_global_namespace(configuration)
    maker = create_myd_czu5ev_maker(soc_json)
    maker.implementation = args.implementation
    maker.gui = args.gui
    maker.auto_connection = args.auto_connection
    maker.event_controller_option = args.event_controller_option
    maker.make_tcl()


if __name__ == "__main__":
    main()
