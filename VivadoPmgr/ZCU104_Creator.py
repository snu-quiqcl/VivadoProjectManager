# -*- coding: utf-8 -*-
"""Create a ZCU104 project for the non-RF lolenc control path."""

import argparse
import json
import logging
from typing import Type

from VivadoPmgr.RFSoC_Creator import RFSoCMaker
from VivadoPmgr.Verilog_Creator import (
    BDCellMaker,
    TVM,
    delete_dump,
    run_vivado_tcl,
    set_global_namespace,
)


RTIO_TARGET_VLNVS = {
    "xilinx.com:user:TTLx8_Controller",
    "xilinx.com:user:DDS_Controller",
    "xilinx.com:user:InputController",
    "xilinx.com:user:TTL_Controller",
    "xilinx.com:user:SwitchController",
    "xilinx.com:user:WaveCacheController",
}

INTERRUPT_STATUS_PORTS = (
    "almost_empty",
    "almost_full",
    "timestamp_error",
    "busy_error",
    "overflow_error",
)


def _as_bool(value):
    """Parse a command-line boolean value."""
    return str(value).lower() == "true"


def _reset_tvm_state() -> None:
    """Reset class-level generation state before creating a new project."""
    TVM.tcl_code = ""
    TVM.connection_code = ""
    TVM.address_code = ""
    TVM.axi_number = 0
    TVM.user_bdcell_w_axi = []
    TVM.interrupt_controller_bdcell_w_axi = None


class ZCU104Maker(RFSoCMaker):
    """RFSoC project maker profile with RF-specific blocks removed."""

    platform_name = "ZCU104"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.board_preset = getattr(self, "board_preset", True)
        if "event_dram_segment" not in kwargs:
            self.event_dram_segment = "HP0_DDR_LOW"
        self.constant_zero = getattr(self, "constant_zero", "")
        self.constant_one = getattr(self, "constant_one", "")
        # ZCU104 has no RF data converter. PL0 supplies the 125 MHz RTIO clock.
        self.rfdc = ""

    def _rtio_cells(self):
        return [cell for cell in self.bd_cell if cell.vlnv in RTIO_TARGET_VLNVS]

    def add_constraints(self) -> None:
        """Load board pins and clock-domain constraints for implementation."""
        super().add_constraints()
        if TVM.constraints:
            TVM.tcl_code += (
                "set_property USED_IN_SYNTHESIS false "
                f"[get_files {{{TVM.constraints}}}]\n"
            )

    @staticmethod
    def _append_net(net_name, pins) -> None:
        pins = [pin for pin in pins if pin]
        if len(pins) < 2:
            return
        TVM.tcl_code += (
            f"connect_bd_net -net {net_name} "
            + " ".join(f"[get_bd_pins {pin}]" for pin in pins)
            + "\n"
        )

    def _emit_cpu_config(self, config) -> None:
        """Apply a property dictionary to the processing-system cell."""
        if not config:
            return
        properties = " ".join(
            f"CONFIG.{key} {{{value}}}" for key, value in config.items()
        )
        TVM.tcl_code += (
            f"set_property -dict [list {properties}] "
            f"[get_bd_cells {self.CPU}]\n"
        )

    def _apply_processing_system_preset(self, cpu_cell) -> None:
        """Apply the ZCU104 board preset, then restore JSON overrides."""
        if not self.board_preset:
            return
        TVM.tcl_code += (
            "apply_bd_automation -rule xilinx.com:bd_rule:zynq_ultra_ps_e "
            '-config {apply_board_preset "1"} '
            f"[get_bd_cells {self.CPU}]\n"
        )
        self._emit_cpu_config(cpu_cell.config)

    def connect_rtio_interface(self) -> None:
        """Connect non-RF RTIO targets and the FDM status/control paths."""
        rtio_cells = self._rtio_cells()
        if not self.timecontroller:
            raise RuntimeError(
                f"{self.platform_name} FDM design requires a TimeController"
            )

        self._append_net(
            f"{self.timecontroller}_auto_start",
            [f"{self.timecontroller}/auto_start"]
            + (
                [f"{self.interruptcontroller}/auto_start"]
                if self.interruptcontroller else []
            )
            + [f"{cell.module_name}/auto_start" for cell in rtio_cells],
        )
        self._append_net(
            f"{self.timecontroller}_counter",
            [f"{self.timecontroller}/counter"]
            + [f"{cell.module_name}/counter" for cell in rtio_cells],
        )

        # PL0 is the RFDC-free replacement for the 125 MHz RTIO clock.
        self._append_net(
            f"{self.CPU}_s_axi_aclk",
            [f"{self.CPU}/pl_clk0", f"{self.timecontroller}/rtio_clk"]
            + [f"{cell.module_name}/rtio_clk" for cell in rtio_cells]
            + [f"{cell.module_name}/s_axi_aclk" for cell in rtio_cells]
            + [
                f"{self.axi_interconnect}/M{str(index).zfill(2)}_ACLK"
                for index in TVM.user_bdcell_w_axi
            ],
        )
        self._append_net(
            f"{self.timecontroller}_rtio_resetn",
            [f"{self.timecontroller}/rtio_resetn"]
            + [f"{cell.module_name}/s_axi_aresetn" for cell in rtio_cells]
            + [
                f"{self.axi_interconnect}/M{str(index).zfill(2)}_ARESETN"
                for index in TVM.user_bdcell_w_axi
            ],
        )

        if self.interruptcontroller:
            for cell in rtio_cells:
                channel = str(cell.channel).zfill(2)
                for port in INTERRUPT_STATUS_PORTS:
                    self._append_net(
                        f"{self.interruptcontroller}_{port}_{channel}",
                        [
                            f"{self.interruptcontroller}/{port}_{channel}",
                            f"{cell.module_name}/{port}",
                        ],
                    )
            self._append_net(
                f"{self.interruptcontroller}_PL_irq",
                [
                    f"{self.interruptcontroller}/PL_irq",
                    f"{self.CPU}/pl_ps_irq0",
                ],
            )

        if self.constant_zero:
            used_channels = {cell.channel for cell in rtio_cells}
            zero_pins = [
                f"{self.constant_zero}/dout",
                f"{self.timecontroller}/external_trigger",
            ]
            if self.interruptcontroller:
                zero_pins.extend(
                    f"{self.interruptcontroller}/{port}_{channel:02d}"
                    for channel in range(64)
                    if channel not in used_channels
                    for port in INTERRUPT_STATUS_PORTS
                )
            self._append_net("zcu104_constant_zero", zero_pins)

        if self.constant_one:
            self._append_net(
                "zcu104_constant_one",
                [
                    f"{self.constant_one}/dout",
                    f"{self.timecontroller}/dram_init_calib_done",
                    f"{self.main_reset}/dcm_locked",
                    f"{self.inst_cache_reset}/dcm_locked",
                ],
            )

    def start_implementation(self) -> None:
        """Run implementation through bitstream generation and verify completion."""
        if self.implementation == 0:
            return
        TVM.tcl_code += (
            "update_compile_order -fileset sources_1\n"
            f"generate_target all [get_files {self.target_path}/"
            f"{self.project_name}/{self.project_name}.srcs/sources_1/bd/"
            f"{self.project_name}_blk/{self.project_name}_blk.bd]\n"
            f"make_wrapper -files [get_files {self.target_path}/"
            f"{self.project_name}/{self.project_name}.srcs/sources_1/bd/"
            f"{self.project_name}_blk/{self.project_name}_blk.bd] -top\n"
            f"add_files -norecurse {self.target_path}/{self.project_name}/"
            f"{self.project_name}.gen/sources_1/bd/{self.project_name}_blk/"
            f"hdl/{self.project_name}_blk_wrapper.v\n"
            f"launch_runs impl_1 -to_step write_bitstream "
            f"-jobs {self.implementation}\n"
            "wait_on_run impl_1\n"
            "set impl_status [get_property STATUS [get_runs impl_1]]\n"
            "if {![string match \"write_bitstream Complete!*\" $impl_status]} {\n"
            '  error "Implementation failed: $impl_status"\n'
            "}\n"
            "set bitstream_file ${project_dir}/${project_name}/"
            "${project_name}.runs/impl_1/${project_name}_blk_wrapper.bit\n"
            "if {![file exists $bitstream_file]} {\n"
            '  error "Implementation did not produce $bitstream_file"\n'
            "}\n"
            "open_run impl_1\n"
            "set failing_setup_paths [get_timing_paths -quiet -delay_type max "
            "-slack_lesser_than 0 -max_paths 1]\n"
            "set failing_hold_paths [get_timing_paths -quiet -delay_type min "
            "-slack_lesser_than 0 -max_paths 1]\n"
            "if {[llength $failing_setup_paths] > 0 || "
            "[llength $failing_hold_paths] > 0} {\n"
            '  error "Implementation completed with negative timing slack"\n'
            "}\n"
            "file mkdir ${project_dir}/${project_name}/reports\n"
            "report_timing_summary -file "
            "${project_dir}/${project_name}/reports/timing_summary.rpt\n"
            "report_utilization -file "
            "${project_dir}/${project_name}/reports/utilization.rpt\n"
            "report_drc -file ${project_dir}/${project_name}/reports/drc.rpt\n"
            "report_methodology -file "
            "${project_dir}/${project_name}/reports/methodology.rpt\n"
            "report_bus_skew -file "
            "${project_dir}/${project_name}/reports/bus_skew.rpt\n"
            "report_cdc -details -file "
            "${project_dir}/${project_name}/reports/cdc.rpt\n"
        )

    def make_tcl(self) -> None:
        """Create, validate, and optionally implement the ZCU104 design."""
        self.set_prj_name()
        self.create_prj()
        self.add_constraints()
        self.set_board()
        self.set_ip_repo()
        self.set_block_diagram()
        self.make_output_ports()
        self.make_input_ports()
        self.make_interface()
        self.make_clk_ports()

        for bd_cell in self.bd_cell:
            bd_cell.set_config()
            if bd_cell.module_name == self.CPU:
                self._apply_processing_system_preset(bd_cell)
            bd_cell.connect_manual()
            if self.auto_connection:
                bd_cell.connect_main_interconnect()
                if (
                    self.event_controller_option
                    and bd_cell.vlnv in RTIO_TARGET_VLNVS
                    and hasattr(bd_cell, "axi")
                ):
                    for index in range(4):
                        bd_cell.set_address_value(
                            f"{self.interruptcontroller}/m_axi_rtio_{index}",
                            bd_cell.axi,
                        )
            bd_cell.set_address()
            if (
                self.event_controller_option
                and hasattr(bd_cell, "axi")
                and bd_cell.vlnv in {
                    "xilinx.com:user:TimeController",
                    "xilinx.com:user:InterruptController",
                }
            ):
                for index in range(4):
                    TVM.address_code += (
                        "exclude_bd_addr_seg -target_address_space "
                        f"[get_bd_addr_spaces {self.interruptcontroller}/"
                        f"m_axi_rtio_{index}] "
                        f"[get_bd_addr_segs {bd_cell.module_name}/s_axi/reg0]\n"
                    )

        if self.auto_connection:
            self.connect_axi_interface()
            self.connect_rtio_interface()

        self.connect_ports()
        self.set_address()
        TVM.tcl_code += "validate_bd_design\nsave_bd_design\n"
        self.start_implementation()
        self.start_gui()

        with open(self.tcl_path, "w", encoding="utf-8") as tcl_file:
            tcl_file.write(TVM.tcl_code)
        if self.auto_connection:
            self.make_module_address_map()
        run_vivado_tcl(self.tcl_path)
        TVM.clear_tcl_code()
        delete_dump()


def create_zcu104_maker(
    json_file: str,
    maker_class: Type[ZCU104Maker] = ZCU104Maker,
) -> ZCU104Maker:
    """Build a non-RF FDM maker from a lolenc SoC JSON description."""
    _reset_tvm_state()
    with open(json_file, "r", encoding="utf-8") as json_data:
        data = json.load(json_data)

    maker = maker_class(**data["block_diagram"])
    channel = 0
    for module_name, ip_data in data.get("bd_cell", {}).items():
        cell = BDCellMaker(**ip_data)
        cell.module_name = module_name
        maker.bd_cell.append(cell)
        if hasattr(cell, "axi"):
            maker.total_axi_number += 1

        vlnv = getattr(cell, "vlnv", "")
        if "xilinx.com:ip:zynq_ultra_ps_e" in vlnv:
            maker.CPU = module_name
        elif vlnv == "xilinx.com:user:TimeController":
            maker.timecontroller = module_name
        elif (
            "xilinx.com:ip:axi_interconnect" in vlnv
            and module_name == "axi_interconnect_0"
        ):
            maker.axi_interconnect = module_name
        elif (
            "xilinx.com:ip:proc_sys_reset" in vlnv
            and module_name == "proc_sys_reset_0"
        ):
            maker.main_reset = module_name
        elif (
            "xilinx.com:ip:proc_sys_reset" in vlnv
            and module_name == "inst_cache_reset_0"
        ):
            maker.inst_cache_reset = module_name
        elif vlnv == "xilinx.com:user:InterruptController":
            maker.interruptcontroller = module_name

        if vlnv in RTIO_TARGET_VLNVS:
            cell.channel = channel
            channel += 1

    required_cells = {
        "processing system": maker.CPU,
        "AXI interconnect": maker.axi_interconnect,
        "TimeController": maker.timecontroller,
        "InterruptController": maker.interruptcontroller,
        "main reset": maker.main_reset,
        "FDM reset": maker.inst_cache_reset,
        "zero constant": maker.constant_zero,
        "one constant": maker.constant_one,
    }
    missing = [name for name, cell in required_cells.items() if not cell]
    if missing:
        raise RuntimeError(
            f"{maker.platform_name} FDM design is missing: "
            + ", ".join(missing)
        )

    cell_names = {cell.module_name for cell in maker.bd_cell}
    named_cells = {
        "zero constant": maker.constant_zero,
        "one constant": maker.constant_one,
    }
    unknown = [
        f"{name} ({cell})"
        for name, cell in named_cells.items()
        if cell not in cell_names
    ]
    if unknown:
        raise RuntimeError(
            f"{maker.platform_name} FDM design references unknown cells: "
            + ", ".join(unknown)
        )

    rtio_count = len(maker._rtio_cells())
    if not 1 <= rtio_count <= 64:
        raise RuntimeError(
            f"{maker.platform_name} FDM design requires between 1 and 64 "
            "RTIO targets"
        )

    maker.override_parameter()
    return maker


def main() -> None:
    """Command-line entry point for ZCU104 project generation."""
    parser = argparse.ArgumentParser(
        description="Create a non-RF lolenc FDM project for the ZCU104"
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-c", "--config", help="Configuration JSON")
    parser.add_argument("-f", "--soc_json", help="ZCU104 SoC JSON")
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
        parser.error("the ZCU104 FDM profile requires -a true")
    if not args.event_controller_option:
        parser.error("the ZCU104 FDM profile requires -e true")

    configuration = args.config or "configuration_ZCU104.json"
    soc_json = args.soc_json or "ZCU104_FDM_Test.json"

    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)
    logging.warning("GUI Option: %s", args.gui)
    logging.warning("Auto Connection Option: %s", args.auto_connection)
    logging.warning("Event Controller Option: %s", args.event_controller_option)

    set_global_namespace(configuration)
    maker = create_zcu104_maker(soc_json)
    maker.implementation = args.implementation
    maker.gui = args.gui
    maker.auto_connection = args.auto_connection
    maker.event_controller_option = args.event_controller_option
    maker.make_tcl()


if __name__ == "__main__":
    main()
