# -*- coding: utf-8 -*-
""" This moduule creates new RFSoC block diagram with given configuration file.

Created on Mon Feb 19 19:15:25 2024

@author: alexi
"""

import re
import argparse
import json
import os
import logging
from typing import Union

from VivadoPmgr.Verilog_Creator import (
    VerilogMaker,
    BDCellMaker,
    TVM,
    run_vivado_tcl,
    delete_dump,
    ensure_directory_exists,
    set_global_namespace,
    create_verilog_maker,
)

FIFO_FULL_BUFFER = 8
POSSIBLE_FIFO_DEPTH = [
    512, 1024, 2048, 4096, 8192,
    16384, 32768, 65536, 131072
]

# pylint: disable=too-many-instance-attributes, invalid-name
class RFSoCMaker(TVM):
    """
    Creates RFSoC block diagram with given configuration file.
    """
    def __init__(self, **kwargs):
        """
        
        project_name: block design name
        DDS_Controller_fifo_depth: DDS module fifo depth
        TTL_Controller_fifo_depth: TTL_Controller module fifo depth
        TTLx8_Controller_fifo_depth: high speed TTL output module fifo depth
        InputController_fifo_depth: InputController output, input fifo depth
        json_path: RFSoC json file path
        bd_cell: list of block design cell names
        verilog_maker: General verilog code creator
        file: verilog file for block design
        CPU: name of Zynq CPU
        reset: reset module name
        clk_wiz: PLL module name
        timecontroller: timecontroller module name ( which makes 
             64 bit counter)
        rfdc: RFDC module name(which includes DAC and ADC)

        """
        super().__init__()
        self.project_name: str = None
        self.DDS_Controller_fifo_depth: Union[str,None] = None
        self.TTL_Controller_fifo_depth: Union[str,None] = None
        self.TTLx8_Controller_fifo_depth: Union[str,None] = None
        self.InputController_fifo_depth: Union[str,None] = None
        self.SwitchController_fifo_depth: Union[str,None] = None
        self.json_path: list[str]
        self.bd_cell: list[BDCellMaker] = []
        self.verilog_maker: list[VerilogMaker] = []
        self.file: list[str] = []
        self.implementation: int = 0
        self.gui: bool = True
        self.auto_connection: bool = True

        # AXI configuration
        self.axi_offset: str = None
        self.axi_interconnect: str = ""
        self.total_axi_number: int = 0

        # Input and Output ports
        self.input_ports: list[str] = []
        self.output_ports: list[str] = []
        self.interface: list[str] = {}
        self.CPU: str = ""

        # Clock Configuration
        self.clk_wiz: str = ""
        self.clk: dict[str: dict[str: str]] = {}

        # Reset Modules
        self.main_reset: str = ""
        self.dram_reset: str = ""

        self.timecontroller: str = ""
        self.rfdc: str = ""
        self.interruptcontroller: str = ""

        for key, value in kwargs.items():
            setattr(self, key, value)

        for json_file in self.json_path:
            vm = create_verilog_maker(json_file)
            self.verilog_maker.append(vm)
            self.file.append(vm.target_path)

        self.target_path = os.path.join(
            TVM.target_path,self.project_name).replace("\\","/")
        self.tcl_path = os.path.join(
            self.target_path,self.project_name+".tcl")
        self.set_possible_fifo_depth()
        ensure_directory_exists(self.target_path)
        TVM.axi_offset = int(self.axi_offset,16)

    def override_parameter(self) -> None:
        """
        override verilog code configuration from rfsoc configuration
        """
        for v in self.verilog_maker:
            for ip in v.ip:
                if ip.name == "fifo_generator":
                    fifo_depth = getattr(self,v.name + "_fifo_depth")
                    ip.config["Input_Depth"] = fifo_depth
                    ip.config["Output_Depth"] = fifo_depth
                    ip.config["Full_Threshold_Assert_Value"] = str(
                        int(fifo_depth) - FIFO_FULL_BUFFER
                    )
                    ip.config["Full_Threshold_Negate_Value"] = str(
                        int(fifo_depth) - FIFO_FULL_BUFFER
                    )
            v.make_tcl()

        for bd_cell in self.bd_cell:
            if bd_cell.module_name == self.axi_interconnect:
                bd_cell.config["NUM_MI"] = self.total_axi_number
        TVM.CPU = self.CPU
        TVM.axi_interconnect = self.axi_interconnect
        TVM.total_axi_number = self.total_axi_number

    def set_possible_fifo_depth(self) -> None:
        """
        set possible fifo depth from given configuration file. This is 
        specified in 
        "block_diagram ": {
            "{module name}_fifo_depth": value of fifo_depth
        }
        """
        pattern = r"\b\w+_fifo_depth\b"
        attributes = dir(self)
        fifo_depths = [
            attr for attr in attributes
            if (re.search(pattern, attr) and isinstance(getattr(self,attr),str))
        ]
        for fifo_depth in fifo_depths:
            if getattr(self,fifo_depth) is None:
                pass
            else:
                fifo_depth_value = int(getattr(self,fifo_depth))
                i = 0
                while POSSIBLE_FIFO_DEPTH[i] < fifo_depth_value:
                    i += 1
                    if i >= len(POSSIBLE_FIFO_DEPTH):
                        raise RuntimeError("rtob fifo depth is too big")
                setattr(self,fifo_depth,str(POSSIBLE_FIFO_DEPTH[i]))

    def make_output_ports(self) -> None:
        """
        Make output ports from configuration file. This is specified in 
        "block_diagram": { 
            "output_ports": [list of output ports]
        }
        """
        for port in self.output_ports:
            TVM.tcl_code += f"set {port} [ create_bd_port -dir O {port} ]\n"

    def make_input_ports(self) -> None:
        """
        Make input ports from configuration file. This is specified in 
        "block_diagram": {
            "input_ports": [list of input ports]
        }
        """
        for port in self.input_ports:
            TVM.tcl_code += f"set {port} [ create_bd_port -dir I {port} ]\n"

    def make_interface(self) -> None:
        """
        Make external interface ports from configuration file. This is specified in
        "block_diagram": {
            "interface": {
                "{interface_name}": {
                    configuration of interface ports
                }
            }
        }
        create_bd_intf_port -mode Master -vlnv xilinx.com:interface:ddr4_rtl:1.0 PL_DDR4
        """
        for intf, option in self.interface.items():
            mode = option["mode"]
            vlnv = option["vlnv"]
            TVM.tcl_code += f"create_bd_intf_port -mode {mode}"
            TVM.tcl_code += f" -vlnv {vlnv} {intf}\n"

    def make_clk_ports(self) -> None:
        """
        Make external clock ports from configuration file. This is specified in 
        "block_diagram": {
            "clk": {
                "{clock_name}": {
                    configuration of clock ports
                }
            }
        }
        """
        for port, option in self.clk.items():
            TVM.tcl_code += f"set {port} [ create_bd_port "
            for key, val in option.items():
                TVM.tcl_code += f"-{key} {val} "
            TVM.tcl_code += f" {port} ]\n"

    def set_prj_name(self) -> None:
        """
        Set project name and project directory to TCL code.
        """
        TVM.tcl_code += (
            f"set project_name \"{self.project_name}\"\n"
            f"set project_dir \"{self.target_path}\"\n"
        )

    def set_ip_repo(self) -> None:
        """
        Add IP repository to Vivado project.
        """
        if self.file:
            TVM.tcl_code += (
                "set_property  ip_repo_paths {" +
                " ".join([f"{file}" for file in self.file]) + 
                " } [current_project]\nupdate_ip_catalog\n" 
            )

    def set_block_diagram(self) -> None:
        """
        Create new block diagram with given project name.
        """
        TVM.tcl_code += (
            f"create_bd_design \"{self.project_name}_blk\"\n"
            f"current_bd_design \"{self.project_name}_blk\"\n"
            "set parentObj [get_bd_cells /]\n"
            "set parentObj [get_bd_cells \"\"]\n"
            "set parentType [get_property TYPE $parentObj]\n"
            "current_bd_instance $parentObj\n"
        )

    def connect_ports(self) -> None:
        """
        This method make TCL script which connect ports of IP 
        modules.
        
        Returns
        -------
        None
        
        """
        TVM.tcl_code += TVM.connection_code

    def set_address(self) -> None:
        """
        This method make TCL script which assign axi address to all of IP 
        modules. Address assign code is separated since 
        
        Returns
        -------
        None
        
        """
        TVM.tcl_code += TVM.address_code

    def connect_axi_interface(self) -> None:
        """
        This module connects AXI interface ports. Note that s_axi_aclk and
        rtio_clk is different clock so two of them must be seperated.
        
        Returns
        -------
        None
        
        """
        TVM.tcl_code += (
            f"connect_bd_net -net {self.main_reset}_peripheral_aresetn"
            f" [get_bd_pins {self.main_reset}/peripheral_aresetn]" +
            "".join(
                [
                    f" [get_bd_pins {bd_cell.module_name}/s_axi_aresetn]"
                     if ( hasattr(bd_cell,"axi") and
                         (not "xilinx.com:user" in bd_cell.vlnv) or
                         (bd_cell.vlnv == "xilinx.com:user:TimeController") or
                         (bd_cell.vlnv == "xilinx.com:user:InterruptController")
                     )
                     else "" for bd_cell  in self.bd_cell
                 ]
            )
        )
        TVM.tcl_code += (
            "".join(
                [
                    (f" [get_bd_pins {self.axi_interconnect}/"
                    f"M{str(i).zfill(2)}_ARESETN]")
                    if not i in TVM.user_bdcell_w_axi else ""
                    for i in range(self.total_axi_number)
                ]
            )
        )
        TVM.tcl_code += (
            f" [get_bd_pins {self.axi_interconnect}/S00_ARESETN]"
            f" [get_bd_pins {self.axi_interconnect}/ARESETN]"
            f" [get_bd_pins {self.clk_wiz}/resetn]\n"
        )

        TVM.tcl_code += (
            f"connect_bd_net -net {self.CPU}_s_axi_aclk"
            f" [get_bd_pins {self.CPU}/maxihpm0_fpd_aclk]"
            f" [get_bd_pins {self.CPU}/pl_clk0]" +
            "".join(
                [
                    f" [get_bd_pins {bd_cell.module_name}/s_axi_aclk]" 
                    if (
                        hasattr(bd_cell,"axi") and
                        (not "xilinx.com:user" in bd_cell.vlnv) or
                        (bd_cell.vlnv == "xilinx.com:user:TimeController") or
                        (bd_cell.vlnv == "xilinx.com:user:InterruptController")
                    ) else "" for bd_cell in self.bd_cell
                ]
            )
        )
        TVM.tcl_code += (
            "".join(
                [
                    (f" [get_bd_pins {self.axi_interconnect}"
                    f"/M{str(i).zfill(2)}_ACLK]") if not i in TVM.user_bdcell_w_axi
                    else "" for i in range(self.total_axi_number)
                ]
            )
        )
        TVM.tcl_code += (
            f" [get_bd_pins {self.main_reset}/slowest_sync_clk]"
            f" [get_bd_pins {self.axi_interconnect}/ACLK]"
            f" [get_bd_pins {self.axi_interconnect}/S00_ACLK]\n"
            f"connect_bd_net -net {self.main_reset}_ext_reset_in"
            f" [get_bd_pins {self.CPU}/pl_resetn0]"
            f" [get_bd_pins {self.main_reset}/ext_reset_in]\n"
            f"connect_bd_intf_net -intf_net {self.CPU}"
            f"_M_AXI_HPM0_FPD [get_bd_intf_pins "
            f"{self.CPU}/M_AXI_HPM0_FPD]"
            f" [get_bd_intf_pins {self.axi_interconnect}/S00_AXI]\n"
        )

    def connect_rtio_interface(self) -> None:
        """
        This connect RTIO interface ports. There are auto_start, counter, 
        rtio_clk, rtio_resetn. auto_start pin is came from TimeController
        module and it is connected to all of rtio modules. counter port is 
        also came from TimeController module and it is connected to all of rtio
        modules. rtio_clk is came from RFDC IP, so it should check whether RFDC
        IP is exist and if not, it does not connect rtio_clk so you should 
        connect rtio_clk manually. rtio_resetn is connected to RFDC IP since
        saxi_resetn is in the s_axi_clk clock region which is different from
        rtio_clk(dac0_clk) clock region. clk_wiz module is used to make 4 times
        faster clock which is provided to OSERDES3 IP of TTLx8_Controller. 

        Returns
        -------
        None

        """
        if self.bd_cell:
            TVM.tcl_code += (
                f"connect_bd_net -net {self.timecontroller}_auto_start"+
                "".join(
                    [f" [get_bd_pins {bd_cell.module_name}/auto_start]"
                    if "xilinx.com:user" in bd_cell.vlnv else "" for bd_cell
                    in self.bd_cell]) +
                "\n" 
            )
            TVM.tcl_code += (
                f"connect_bd_net -net {self.timecontroller}_counter"+
                "".join(
                    [f" [get_bd_pins {bd_cell.module_name}/counter]"
                    if "xilinx.com:user" in bd_cell.vlnv else "" for bd_cell
                    in self.bd_cell]) +
                "\n" 
            )
        if self.rfdc != "":
            TVM.tcl_code += f"connect_bd_net -net {self.rfdc}_clk_dac0"
            TVM.tcl_code += f" [get_bd_pins {self.rfdc}/clk_dac0]"
            TVM.tcl_code += f" [get_bd_pins {self.rfdc}/s0_axis_aclk]"
            TVM.tcl_code += f" [get_bd_pins {self.rfdc}/s1_axis_aclk]"
            TVM.tcl_code += f" [get_bd_pins {self.clk_wiz}/clk_in1]"
            if self.bd_cell:
                TVM.tcl_code += (
                    "".join(
                        [
                            f" [get_bd_pins {bd_cell.module_name}/rtio_clk]"
                            if ("xilinx.com:user" in bd_cell.vlnv  and
                                (bd_cell.vlnv != "xilinx.com:user:InterruptController")
                            )
                            else ""
                            for bd_cell in self.bd_cell
                        ]
                    )
                )
                # Connect s_axi_clk of Custom BD cell with RFDC dac_clk
                TVM.tcl_code += (
                    "".join(
                        [
                            f" [get_bd_pins {bd_cell.module_name}/s_axi_aclk]"
                            if(("xilinx.com:user" in bd_cell.vlnv)  and
                                (bd_cell.vlnv != "xilinx.com:user:TimeController") and
                                (bd_cell.vlnv != "xilinx.com:user:InterruptController")
                            )
                            else "" for bd_cell in self.bd_cell
                        ]
                    )
                )
                TVM.tcl_code += (
                    "".join(
                        [
                            (f" [get_bd_pins {self.axi_interconnect}"
                            f"/M{str(i).zfill(2)}_ACLK]")
                            if i in TVM.user_bdcell_w_axi else ""
                            for i in range(self.total_axi_number)
                        ]
                    )
                )
                TVM.tcl_code += (
                    "".join(
                        [f" [get_bd_pins {bd_cell.module_name}/m00_axis_aclk]"
                        if (bd_cell.vlnv == "xilinx.com:user:SwitchController")
                        else "" for bd_cell in self.bd_cell]
                    )
                )
            TVM.tcl_code += "\n"

            TVM.tcl_code += (
                "connect_bd_net -net"
                f" {self.timecontroller}_rtio_resetn"
                f" [get_bd_pins {self.timecontroller}/rtio_resetn]"
                f" [get_bd_pins {self.rfdc}/s0_axis_aresetn]"
                f" [get_bd_pins {self.rfdc}/s1_axis_aresetn]"
            )
            TVM.tcl_code += (
                "".join(
                    [
                        (f" [get_bd_pins {self.axi_interconnect}/"
                        f"M{str(i).zfill(2)}_ARESETN]")
                        if i in TVM.user_bdcell_w_axi else ""
                        for i in range(self.total_axi_number)
                    ]
                )
            )
            TVM.tcl_code += (
                "".join(
                    [
                        f" [get_bd_pins {bd_cell.module_name}/s_axi_aresetn]"
                        if ( hasattr(bd_cell,"axi") and
                             ("xilinx.com:user" in bd_cell.vlnv) and
                             (bd_cell.vlnv != "xilinx.com:user:TimeController") and
                             (bd_cell.vlnv != "xilinx.com:user:InterruptController")
                        )
                        else "" for bd_cell in self.bd_cell
                     ]
                )
            )
            TVM.tcl_code += "\n"

        # Interrupt Controller Connection. Maimum number is 64
        interrupt_controller_ports = [
            "almost_empty",     # PL_INT 121 -> Core1
            "almost_full",      # PL_INT 121 -> Core1
            "timestamp_error",  # PL_INT 122 -> Core2
            "busy_error",       # PL_INT 122 -> Core2
            "overflow_error",   # PL_INT 122 -> Core2
        ]
        if self.interruptcontroller != "":
            for bd_cell in self.bd_cell:
                if (
                    bd_cell.vlnv in [
                        "xilinx.com:user:TTLx8_Controller",
                        "xilinx.com:user:DDS_Controller",
                        "xilinx.com:user:InputController",
                        "xilinx.com:user:TTL_Controller",
                        "xilinx.com:user:SwitchController",
                    ]
                ):
                    # Connect Almost Empty
                    for interrupt_controller_port in interrupt_controller_ports:
                        TVM.tcl_code += (
                            f"connect_bd_net -net {self.interruptcontroller}"
                            f"_{interrupt_controller_port}_{str(bd_cell.channel).zfill(2)}"
                            f" [get_bd_pins {self.interruptcontroller}/"
                            f"{interrupt_controller_port}_{str(bd_cell.channel).zfill(2)}]"
                            f" [get_bd_pins {bd_cell.module_name}/{interrupt_controller_port}]"
                        )
                        TVM.tcl_code += "\n"
            TVM.tcl_code += (
                f"connect_bd_net -net {self.interruptcontroller}"
                "_PL_irq"
                f" [get_bd_pins {self.interruptcontroller}/PL_irq]"
                f" [get_bd_pins {self.CPU}/pl_ps_irq0]"
            )
            TVM.tcl_code += "\n"

    def start_gui(self) -> None:
        """
        It makes vivado GUI run after creation of block diagram. Note that 
        you should make wrapper in TCL code or turn on vivado GUI and save 
        block diagram. If not, there would be blank block diagram.

        Returns
        -------
        None

        """
        if self.gui:
            TVM.tcl_code += "start_gui\n"

    def start_implementation(self) -> None:
        """
        Start implementation of given block diagram with Vivado.
        """
        if self.implementation != 0:
            TVM.tcl_code += (
                "update_compile_order -fileset sources_1\n"
                f"make_wrapper -files [get_files {self.target_path}/"
                f"{self.project_name}/{self.project_name}.srcs/sources_1/bd/"
                f"{self.project_name}_blk/{self.project_name}_blk.bd] -top\n"
                f"add_files -norecurse {self.target_path}/{self.project_name}/"
                f"{self.project_name}.gen/sources_1/bd/{self.project_name}_blk/"
                f"hdl/{self.project_name}_blk_wrapper.v\n"
                f"launch_runs impl_1 -to_step write_bitstream -jobs {self.implementation}\n"
                "write_hw_platform -fixed -include_bit -force -file "
                f"{self.target_path}/{self.project_name}/{self.project_name}.xsa\n"
            )

    def make_module_address_map(self) -> None:
        """
        Make device_db json file which contains module address map.
        """
        module_addr_map: dict[str,int] = {}
        # User Module address map
        for bd_cell_maker in self.bd_cell:
            if "xilinx.com:user:SwitchController" in getattr(bd_cell_maker,"vlnv"):
                module_addr_map[bd_cell_maker.module_name] = make_module_map(
                    bd_cell_maker
                )
            if "xilinx.com:user:DDS_Controller" in getattr(bd_cell_maker,"vlnv"):
                module_addr_map[bd_cell_maker.module_name] = make_module_map(
                    bd_cell_maker
                )
            if "xilinx.com:user:TTL_Controller" in getattr(bd_cell_maker,"vlnv"):
                module_addr_map[bd_cell_maker.module_name] = make_module_map(
                    bd_cell_maker
                )
            if "xilinx.com:user:TTLx8_Controller" in getattr(bd_cell_maker,"vlnv"):
                module_addr_map[bd_cell_maker.module_name] = make_module_map(
                    bd_cell_maker
                )
            if "xilinx.com:user:InputController" in getattr(bd_cell_maker,"vlnv"):
                module_addr_map[bd_cell_maker.module_name] = make_module_map(
                    bd_cell_maker
                )
            module_address_map_json: str = os.path.join(os.getcwd(),"device_db.json")
        with open(module_address_map_json, "w", encoding="utf-8") as file:
            json.dump(module_addr_map, file, indent=4)

    def make_tcl(self) -> None:
        """
        Create TCL script which makes RFSoC block diagram with given configuration file.
        """
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
        self.connect_ports()
        if self.auto_connection:
            self.connect_axi_interface()
            self.connect_rtio_interface()
            self.set_address()
        self.start_implementation()
        self.start_gui()
        with open(os.path.join(
            self.target_path, self.project_name+".tcl"), "w", encoding="utf-8"
        ) as file:
            file.write(TVM.tcl_code)
        self.make_module_address_map()
        run_vivado_tcl(self.tcl_path)
        TVM.clear_tcl_code()
        delete_dump()

def make_module_map(bd_cell: BDCellMaker) -> dict[str,dict[str,str]]:
    """
    Make module map from given name, address and channel.
    """
    data = {
        "axi_addr": hex(bd_cell.axi_address),
        "arguments": {
            "channel": bd_cell.channel
        }
    }
    if "xilinx.com:user:SwitchController" in getattr(bd_cell,"vlnv"):
        data["module"] = "lolenc.bsp.src.module.SwitchController"
        data["class"] = "SwitchController"
    if "xilinx.com:user:DDS_Controller" in getattr(bd_cell,"vlnv"):
        data["module"] = "lolenc.bsp.src.module.DDS_Controller"
        data["class"] = "DDS_Controller"
    if "xilinx.com:user:TTL_Controller" in getattr(bd_cell,"vlnv"):
        data["module"] = "lolenc.bsp.src.module.TTL_Controller"
        data["class"] = "TTL_Controller"
    if "xilinx.com:user:TTLx8_Controller" in getattr(bd_cell,"vlnv"):
        data["module"] = "lolenc.bsp.src.module.TTLx8_Controller"
        data["class"] = "TTLx8_Controller"
    if "xilinx.com:user:InputController" in getattr(bd_cell,"vlnv"):
        data["module"] = "lolenc.bsp.src.module.InputController"
        data["class"] = "InputController"
    return data

def create_rfsoc_maker(json_file: str) -> RFSoCMaker:
    """
    Creates RFSoC maker from json file.
    """
    with open(json_file, "r", encoding="utf-8") as file:
        data = json.load(file)
    rm = RFSoCMaker(**data["block_diagram"])
    channel: int = 0
    for module_name, ip_data in data.get("bd_cell", {}).items():
        bd_cell_maker = BDCellMaker(**ip_data)
        bd_cell_maker.module_name = module_name
        rm.bd_cell.append(bd_cell_maker)
        if hasattr(bd_cell_maker, "axi"):
            rm.total_axi_number += 1
        # pylint: disable=unsubscriptable-object
        if hasattr(bd_cell_maker,"vlnv"):
            if "xilinx.com:ip:zynq_ultra_ps_e" in getattr(bd_cell_maker,"vlnv"):
                setattr(rm,"CPU",bd_cell_maker.module_name)
            if "xilinx.com:user:TimeController" in getattr(bd_cell_maker,"vlnv"):
                setattr(rm,"timecontroller",bd_cell_maker.module_name)
            if ("xilinx.com:ip:axi_interconnect" in getattr(bd_cell_maker,"vlnv") and
                bd_cell_maker.module_name == "axi_interconnect_0"):
                setattr(rm,"axi_interconnect",bd_cell_maker.module_name)
            if ("xilinx.com:ip:proc_sys_reset" in getattr(bd_cell_maker,"vlnv") and
                bd_cell_maker.module_name == "proc_sys_reset_0"):
                setattr(rm,"main_reset",bd_cell_maker.module_name)
            if ("xilinx.com:ip:proc_sys_reset" in getattr(bd_cell_maker,"vlnv") and
                bd_cell_maker.module_name == "dram_reset_0"):
                setattr(rm,"dram_reset",bd_cell_maker.module_name)
            if "xilinx.com:ip:usp_rf_data_converter" in getattr(bd_cell_maker,"vlnv"):
                setattr(rm,"rfdc",bd_cell_maker.module_name)
            if "xilinx.com:ip:clk_wiz:6.0" in getattr(bd_cell_maker,"vlnv"):
                setattr(rm,"clk_wiz",bd_cell_maker.module_name)
            if "xilinx.com:user:InterruptController" in getattr(bd_cell_maker,"vlnv"):
                setattr(rm,"interruptcontroller",bd_cell_maker.module_name)
            # Set channel number for each module
            if (
                "xilinx.com:user:SwitchController" in getattr(bd_cell_maker,"vlnv") or
                "xilinx.com:user:DDS_Controller" in getattr(bd_cell_maker,"vlnv") or
                "xilinx.com:user:TTL_Controller" in getattr(bd_cell_maker,"vlnv") or
                "xilinx.com:user:TTLx8_Controller" in getattr(bd_cell_maker,"vlnv") or
                "xilinx.com:user:InputController" in getattr(bd_cell_maker,"vlnv")
            ):
                setattr(bd_cell_maker,"channel",channel)
                channel += 1
    rm.override_parameter()
    return rm

def main() -> None:
    """
    Main function of RFSoC block diagram creator.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Make SoC Block diagram with json files. You need configuration "
            "file which set directory of vivado and common directory path"
            "and json files which specifies the SoC design"
        )
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", 
        help="Increase output verbosity"
    )
    parser.add_argument("-c", "--config", help="Configuration file name")
    parser.add_argument("-f", "--soc_json", help="SoC JSON file name")
    parser.add_argument(
        "-i",
        "--implementation",
        type = int,
        default=0,
        help="Implementation option"
    )
    parser.add_argument(
        "-g",
        "--gui",
        type=lambda x: (str(x).lower() == 'true'),
        default=True,
        help="GUI open option"
    )
    parser.add_argument(
        "-a",
        "--auto_connection",
        type=lambda x: (str(x).lower() == 'true'),
        default=True,
        help="Auto Connection option"
    )
    args = parser.parse_args()

    configuration: str = args.config if args.config else "configuration.json"
    soc_json: str = args.soc_json if args.soc_json else "RFSoC.json"
    implementation: int = args.implementation
    gui: bool = args.gui
    auto_connection: bool = args.auto_connection
    logging.warning("GUI Option: %s",gui)
    logging.warning("Auto Connection Option: %s",auto_connection)

    set_global_namespace(configuration)
    rfsoc_maker = create_rfsoc_maker(soc_json)
    setattr(rfsoc_maker,"implementation",implementation)
    setattr(rfsoc_maker,"gui",gui)
    setattr(rfsoc_maker,"auto_connection",auto_connection)
    rfsoc_maker.make_tcl()
