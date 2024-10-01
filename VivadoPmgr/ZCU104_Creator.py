# -*- coding: utf-8 -*-
"""
Created on Mon Feb 19 19:15:25 2024

@author: alexi
"""
import re
import argparse
from VivadoPmgr.Verilog_Creator import *

POSSIBLE_FIFO_DEPTH = [
    512, 1024, 2048, 4096, 8192, 
    16384, 32768, 65536, 131072
    ]

class ZCU104Maker(TVM):
    def __init__(self, **kwargs):
        """
        
        project_name : block design name
        json_path : ZCU104 json file path
        bd_cell : list of block design cell names
        verilog_maker : General verilog code creator
        file : verilog file for block design
        CPU : name of Zynq CPU
        reset : reset module name
        clk_wiz : PLL module name
        timecontroller : timecontroller module name ( which makes 
             64 bit counter)
        rfdc : RFDC module name(which includes DAC and ADC)

        """
        super().__init__()
        self.project_name : str = None
        self.json_path : list[str] = None
        self.bd_cell : list[BDCellMaker] = []
        self.verilog_maker : list[VerilogMaker] = []
        self.file : list[str] = []

        self.axi_offset : str = None
        self.axi_interconnect : str = ""
        self.total_axi_number : int = 0
        self.input_ports : list[str] = []
        self.output_ports : list[str] = []
        self.clk : dict[str : dict[str : str]] = {}
        self.CPU : str = ""
        self.reset : str = ""
        self.clk_wiz : str = ""

        self.timecontroller : str = ""

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
        # self.set_possible_fifo_depth()
        ensure_directory_exists(self.target_path)
        TVM.axi_offset = int(self.axi_offset,16)

    def override_parameter(self) -> None:
        """
        override verilog code configuration from ZCU104 configuration
        """
        for v in self.verilog_maker:
            for ip in v.ip:
                if ( ip.name == "fifo_generator" and 
                    hasattr(self,v.name + "_fifo_depth") ):
                    fifo_depth = getattr(self,v.name + "_fifo_depth")
                    ip.config["Input_Depth"] = fifo_depth
                    ip.config["Output_Depth"] = fifo_depth
                    ip.config["Full_Threshold_Assert_Value"] = str(
                        int(fifo_depth) - 8
                    )
                    ip.config["Full_Threshold_Negate_Value"] = str(
                        int(fifo_depth) - 8
                    )
            v.make_tcl()

        TVM.CPU = self.CPU
        TVM.axi_interconnect = self.axi_interconnect
        TVM.total_axi_number = self.total_axi_number

    def set_possible_fifo_depth(self) -> None:
        """
        set possible fifo depth from given configuration file. This is 
        specified in 
        "block_diagram ": {
            "{module name}_fifo_depth" : value of fifo_depth
        }
        """
        pattern = r"\b\w+_fifo_depth\b"
        attributes = dir(self)
        fifo_depths = [attr for attr in attributes if re.search(pattern, attr)]
        for fifo_depth in fifo_depths:
            fifo_depth_value = int(getattr(self,fifo_depth))
            i = 0
            while POSSIBLE_FIFO_DEPTH[i] < fifo_depth_value:
                i += 1
                if i >= len(POSSIBLE_FIFO_DEPTH):
                    raise Exception("rtob fifo depth is too big")
                setattr(self,fifo_depth,str(POSSIBLE_FIFO_DEPTH[i]))

    def make_output_ports(self) -> None:
        """
        Make output ports from configuration file. This is specified in 
        "block_diagram" : { 
            "output_ports" : [list of output ports]
        }
        """
        for port in self.output_ports:
            TVM.tcl_code += f"set {port} [ create_bd_port -dir O {port} ]\n"

    def MakeInputPorts(self) -> None:
        """
        Make input ports from configuration file. This is specified in 
        "block_diagram" : {
            "input_ports" : [list of input ports]
        }
        """
        for port in self.input_ports:
            TVM.tcl_code += f"set {port} [ create_bd_port -dir I {port} ]\n"

    def make_clk_ports(self) -> None:
        """
        Make external clock ports from configuration file. This is specified in 
        "block_diagram" : {
            "clk" : {
                "{clock_name}" : {
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
        TVM.tcl_code += (
            f"set project_name \"{self.project_name}\"\n"
            f"set project_dir \"{self.target_path}\"\n"
        )

    def set_ip_repo(self) -> None:
        if self.file:
            TVM.tcl_code += (
                "set_property  ip_repo_paths {" +
                " ".join([f"{file}" for file in self.file]) + 
                " } [current_project]\nupdate_ip_catalog\n" 
            )

    def set_block_diagram(self) -> None:
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
            f"connect_bd_net -net {self.reset}_peripheral_aresetn"
            f" [get_bd_pins {self.reset}/peripheral_aresetn]" +
            "".join(
                [
                    f" [get_bd_pins {bd_cell.module_name}/s_axi_aresetn]" 
                     if hasattr(bd_cell,"axi") else "" for bd_cell 
                     in self.bd_cell
                 ]
            )
        )
        TVM.tcl_code += (
            "".join(
                [
                    (f" [get_bd_pins {self.axi_interconnect}/"
                    "M{str(i).zfill(2)}_ARESETN]")
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
                     if hasattr(bd_cell,"axi") else "" for bd_cell  
                     in self.bd_cell
                 ]
            )
        )
        TVM.tcl_code += (
            "".join(
                [
                    f" [get_bd_pins {self.axi_interconnect}"
                    +"/M{str(i).zfill(2)}_ACLK]" 
                    for i in range(self.total_axi_number)
                ]
            )
        )
        TVM.tcl_code += (
            f" [get_bd_pins {self.reset}/slowest_sync_clk]"
            f" [get_bd_pins {self.axi_interconnect}/ACLK]"
            f" [get_bd_pins {self.axi_interconnect}/S00_ACLK]\n"
            f"connect_bd_net -net {self.reset}_ext_reset_in"
            f" [get_bd_pins {self.CPU}/pl_resetn0]"
            f" [get_bd_pins {self.reset}/ext_reset_in]\n"
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
        faster clock which is provided to OSERDES3 IP of TTLx8_out. 

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
                        [f" [get_bd_pins {bd_cell.module_name}/rtio_clk]" 
                         if "xilinx.com:user" in bd_cell.vlnv else "" 
                         for bd_cell in self.bd_cell]
                    )
                )
                TVM.tcl_code += (
                    "".join(
                        [f" [get_bd_pins {bd_cell.module_name}/m00_axis_aclk]" 
                        if bd_cell.vlnv == "xilinx.com:user:DAC_Controller" 
                        else "" for bd_cell in self.bd_cell]
                    )
                )
            TVM.tcl_code += "\n"
            TVM.tcl_code += (
                "connect_bd_net -net"
                f" {self.timecontroller}_rtio_resetn"
                f" [get_bd_pins {self.timecontroller}/rtio_resetn]"
                f" [get_bd_pins {self.rfdc}/s0_axis_aresetn]"
                f" [get_bd_pins {self.rfdc}/s1_axis_aresetn]\n"
            )
        if self.clk_wiz != "":
            TVM.tcl_code += (
                f"connect_bd_net -net {self.clk_wiz}_clk_out1"
                f" [get_bd_pins {self.clk_wiz}/clk_out1]"+
                "".join(
                    [f" [get_bd_pins {bd_cell.module_name}/clk_x4]" 
                    if bd_cell.vlnv == "xilinx.com:user:TTLx8_out" else "" 
                    for bd_cell in self.bd_cell]
                )
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
        TVM.tcl_code += "start_gui\n"

    def make_tcl(self) -> None:
        self.set_prj_name()
        self.create_prj()
        self.add_constraints()
        self.set_board()
        self.set_ip_repo()
        self.set_block_diagram()
        self.make_output_ports()
        self.MakeInputPorts()
        self.make_clk_ports()
        for bd_cell in self.bd_cell:
            bd_cell.set_config()
        self.connect_ports()
        # self.connect_axi_interface()
        # self.connect_rtio_interface()
        # self.set_address()
        self.start_gui()
        with open(os.path.join(
                self.target_path, self.project_name+".tcl"), "w") as file:
            file.write(TVM.tcl_code)
        run_vivado_tcl(self.tcl_path)
        TVM.clear_tcl_code()
        delete_dump()

def create_zcu104_maker(json_file : str) -> ZCU104Maker:
    with open(json_file, "r") as file:
        data = json.load(file)
    rm = ZCU104Maker(**data["block_diagram"])
    for module_name, ip_data in data.get("bd_cell", {}).items():
        bd_cell_maker = BDCellMaker(**ip_data)
        bd_cell_maker.module_name = module_name
        rm.bd_cell.append(bd_cell_maker)
        if hasattr(bd_cell_maker, "axi"):
            rm.total_axi_number += 1
        if hasattr(bd_cell_maker,"vlnv"):
            if ("xilinx.com:ip:zynq_ultra_ps_e" 
                in getattr(bd_cell_maker,"vlnv")):
                setattr(rm,"CPU",bd_cell_maker.module_name)
            if ("xilinx.com:user:TimeController" 
                in getattr(bd_cell_maker,"vlnv")):
                setattr(rm,"timecontroller",bd_cell_maker.module_name)
            if ("xilinx.com:ip:axi_interconnect" 
                in getattr(bd_cell_maker,"vlnv")):
                setattr(rm,"axi_interconnect",bd_cell_maker.module_name)
            if ("xilinx.com:ip:proc_sys_reset"
                in getattr(bd_cell_maker,"vlnv")):
                setattr(rm,"reset",bd_cell_maker.module_name)
            if ("xilinx.com:ip:usp_rf_data_converter"
                in getattr(bd_cell_maker,"vlnv")):
                setattr(rm,"rfdc",bd_cell_maker.module_name)
            if "xilinx.com:ip:clk_wiz:6.0" in getattr(bd_cell_maker,"vlnv"):
                setattr(rm,"clk_wiz",bd_cell_maker.module_name)
    rm.override_parameter()
    return rm

def main() -> None:
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
    args = parser.parse_args()

    configuration = args.config if args.config else "configuration.json"
    soc_json = args.soc_json if args.soc_json else "ZCU104.json"

    set_global_namespace(configuration)
    ZCU104_Maker = create_zcu104_maker(soc_json)
    ZCU104_Maker.make_tcl()
