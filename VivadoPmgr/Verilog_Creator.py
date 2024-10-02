# -*- coding: utf-8 -*-
"""
Created on Sun Feb 18 19:33:29 2024

@author: alexi
"""

import json
import os
import subprocess
import shutil
import argparse
import logging

class TVM:
    """
    This is Verilog Mother
    """
    common_path: str = None
    target_path: str = None
    vivado_path: str = None
    board_path: str = None
    part_name: str = None
    board_name: str = None
    version: str = None
    constraints: str = None

    tcl_code: str = ""
    connection_code: str = ""

    CPU: str = ""
    axi_interconnect: str = ""
    axi_number: int = 0
    axi_offset: int = 0
    address_code: str = ""
    total_axi_number: int = 0
    user_bdcell_w_axi: list[int] = []

    def __init__(self):
        pass

    @classmethod
    def set_class_vars(cls, **kwargs):
        """
        This function sets the class variables
        """
        for key, value in kwargs.items():
            setattr(cls, key, value)

    @classmethod
    def clear_tcl_code(cls):
        """
        This function clears the tcl code
        """
        cls.tcl_code = ""

    def add_files(self):
        """
        this function adds files to the project
        """
        # pylint: disable=no-member
        for file in self.files:
            TVM.tcl_code += f"add_files -norecurse {{{file}}}\n"

    def add_constraints(self):
        """
        This function adds constraints to the project
        """
        TVM.tcl_code += (
            f"add_files -fileset constrs_1 -norecurse "
            f"{TVM.constraints}\n"
        )

    def create_prj(self):
        """
        This function creates the project
        """
        TVM.tcl_code += (
            f"create_project ${{project_name}} "
            f"${{project_dir}}/${{project_name}} -part {TVM.part_name}\n"
        )

    def set_board(self):
        """
        This function sets the board
        """
        if not TVM.board_name is None:
            TVM.tcl_code += (
                f"set boardpath {{{TVM.board_path}}}\n"
                "set_param board.repoPaths [list $boardpath]\n"
                f"set_property BOARD_PART {TVM.board_name} [current_project]\n"
            )
# pylint: disable=too-few-public-methods
class IPMaker:
    """ This class creates an IP """
    def __init__(self, **kwargs):
        super().__init__()
        self.version: str = None
        self.vendor: str = None
        self.config: dict = None
        self.name: str = None
        self.module_name: str = None
        self.target_path: str = None
        self.tcl_options: list[str] = []

        for key, value in kwargs.items():
            setattr(self, key, value)

    def set_config(self):
        """ This function sets the configuration of the IP """
        TVM.tcl_code += f"create_ip -dir {self.target_path}"
        for tcl_option in self.tcl_options:
            TVM.tcl_code += f" -{tcl_option} {getattr(self,tcl_option)}"
        TVM.tcl_code += "\n"

        if self.config:
            TVM.tcl_code += (
                "set_property -dict [list " + " ".join(
                    [f"CONFIG.{key} {{{value}}}" for key, value
                     in self.config.items()]
                ) +
                "]"
                f" [get_ips {self.module_name}]\n"
            )

# pylint: disable=too-many-instance-attributes
class BDCellMaker:
    """ This class creates a BD Cell"""
    def __init__(self, **kwargs):
        super().__init__()
        self.module_name: str
        self.axi_address: int
        self.type: str
        self.vlnv: str
        self.config: dict = {}
        self.ports: dict = {}
        self.interface: dict = {}
        self.module_name: str
        self.tcl_options: list[str]
        self.channel: int

        for key, value in kwargs.items():
            setattr(self, key, value)

    def set_config(self):
        """
        This function sets the configuration of the BD Cell
        """
        TVM.tcl_code += f"set {self.module_name} [ create_bd_cell"
        for tcl_option in self.tcl_options:
            TVM.tcl_code += f" -{tcl_option} {getattr(self,tcl_option)}"
        TVM.tcl_code += f" {self.module_name} ]\n"

        if self.config:
            TVM.tcl_code += (
                "set_property -dict [list " + " ".join(
                    [f"CONFIG.{key} {{{value}}}" for key, value
                     in self.config.items()]
                ) + "]"
            )
        if "xilinx.com:user" in self.vlnv and self.config:
            TVM.tcl_code += f" [get_bd_cells {self.module_name}]\n"

        elif self.config:
            TVM.tcl_code += f" ${self.module_name}\n"

    def connect_manual(self):
        """
        This function sets the connections of the BD Cell
        """
        for victim, target in self.ports.items():
            if "/" in target:
                TVM.connection_code += (
                    f"connect_bd_net "
                    f"[get_bd_pins {target}] [get_bd_pins {self.module_name}"
                    f"/{victim}]\n"
                )
            else:
                TVM.connection_code += (
                    f"connect_bd_net "
                    f"[get_bd_ports {target}] [get_bd_pins {self.module_name}"
                    f"/{victim}]\n"
                )

        for victim, target in self.interface.items():
            TVM.connection_code += (
                f"connect_bd_intf_net -intf_net {self.module_name}_{victim}"
                f" [get_bd_intf_pins {target}] [get_bd_intf_pins "
                f"{self.module_name}/{victim}]\n"
            )

    def connect_main_interconnect(self):
        """
        This function set teh interconnect of the BD Cell
        """
        _multi_master = False
        if hasattr(self,"axi"):
            _multi_master = check_for_nested_dict(self.axi)
            self.axi_address = TVM.axi_offset
            if _multi_master:
                data = self.axi.get(TVM.CPU + "/Data")
                range_ = int(data.get("range"),16)
            else:
                self.connect_interconnect(TVM.axi_interconnect, TVM.axi_number)
                range_ = int(self.axi.get("range"),16)
            TVM.axi_offset += range_
            TVM.axi_number += 1

    def connect_interconnect(self, interconnect_name, axi_num):
        """
        This function connect actual interconnect to the BD Cell
        """
        # Connect interconnect module manually
        if (
            "xilinx.com:ip:axi_interconnect" in self.vlnv or
            "xilinx.com:ip:ddr4" in self.vlnv
        ):
            return
        TVM.connection_code += (
            f"connect_bd_intf_net -intf_net {interconnect_name}_M"
            f"{str(axi_num).zfill(2)}_AXI [get_bd_intf_pins"
            f" {self.module_name}/s_axi] [get_bd_intf_pins"
            f" {interconnect_name}/"
            f"M{str(axi_num).zfill(2)}_AXI]\n"
        )
        if (("xilinx.com:user" in self.vlnv) and
            (self.vlnv != "xilinx.com:user:TimeController") and
            (self.vlnv != "xilinx.com:user:InterruptController")
        ):
            TVM.user_bdcell_w_axi.append(TVM.axi_number)

    def set_address(self):
        """
        This function sets the address of the BD Cell
        """
        _multi_master = False
        if hasattr(self,"axi"):
            _multi_master = check_for_nested_dict(self.axi)
            if _multi_master:
                for _master, data in self.axi.items():
                    self.set_address_value(_master, data)
            else:
                self.set_address_value(TVM.CPU + "/Data", self.axi)

    def set_address_value(self, master, data, offset = None):
        """
        This function sets the actual address value
        """
        if hasattr(data,"address_space"):
            reg = data["address_space"]
        elif "xilinx.com:user" in self.vlnv:
            reg = "s_axi/reg0"
        elif "xilinx.com:ip:ddr4" in self.vlnv:
            reg = "C0_DDR4_MEMORY_MAP/C0_DDR4_ADDRESS_BLOCK"
        else:
            reg = "s_axi/Reg"

        range_ = int(data.get("range"),16)
        if "offset" in data:
            offset = data.get("offset")
        else:
            offset = hex(self.axi_address)
        TVM.address_code += (
            f"assign_bd_address -offset {offset} -range "
            f"{hex(range_).upper()} -target_address_space "
            f"[get_bd_addr_spaces {master}] [get_bd_addr_segs "
            f"{self.module_name}/{reg}] -force\n"
        )

# pylint: disable=too-many-instance-attributes
class VerilogMaker(TVM):
    """
    Creates a Vivado project with the given verilog files and IPs
    """
    def __init__(self, **kwargs):
        super().__init__()
        self.name: str = None
        self.files: list = []
        self.ip: list[IPMaker] = []
        self.target_path: str = None
        self.tcl_path: str = None
        self.gen_ip: str = "True"
        self.top_module_name: str = ""
        self.top: str

        for key, value in kwargs.items():
            setattr(self, key, value)

        self.files = [
            os.path.join(TVM.common_path,file)
            .replace("\\","/") for file in self.files
        ]
        self.target_path = (
            os.path.join(TVM.target_path,self.name).replace("\\","/")
        )
        self.tcl_path = os.path.join(self.target_path,self.name+".tcl")

    def set_top(self):
        """
        This function sets the top module
        """
        TVM.tcl_code += (
            f"set_property top {self.name} [current_fileset]\n"
            f"set_property top_file {{ {self.target_path}/{self.top} }}"
            " [current_fileset]\n"
        )
        if self.top_module_name != "":
            TVM.tcl_code += (
                f"set_property top {self.top_module_name}"
                " [current_fileset]\n"
            )

    def add_ip(self):
        """
        This function adds IPs to the project
        """
        for ip in self.ip:
            ip.set_config()

    def generate_customized_ip(self):
        """
        This function generates customized IPs
        """
        TVM.tcl_code += (
            f"ipx::package_project -root_dir {self.target_path}"
            " -vendor xilinx.com -library user -taxonomy /UserIP\n"
            "ipx::save_core [ipx::current_core]\n"
            f"set_property  ip_repo_paths  {self.target_path}"
            " [current_project]\n"
            "update_ip_catalog\n"
        )

    def copy_files(self):
        """
        This function copies the files to the target path
        """
        ensure_directory_exists(self.target_path)
        for file in self.files:
            shutil.copy(
                file,os.path.join(self.target_path,os.path.basename(file))
            )
        self.files = [
            os.path.join(
                self.target_path,os.path.basename(file)
            ).replace("\\","/") for file in self.files
        ]

    def set_prj_name(self):
        """
        This function sets the project name and directory
        """
        TVM.tcl_code += (
            f"set project_name \"{self.name}\"\n"
            f"set project_dir \"{self.target_path}\"\n"
        )

    def make_tcl(self):
        """
        This function creates the tcl file
        """
        self.copy_files()
        self.set_prj_name()
        self.create_prj()
        self.add_files()
        self.set_board()
        self.add_ip()
        self.add_constraints()
        self.set_top()
        if self.gen_ip == "True":
            self.generate_customized_ip()
        with (
            open(os.path.join(self.target_path,self.name+".tcl"), "w", encoding="utf-8") as file
        ):
            file.write(TVM.tcl_code)
        run_vivado_tcl(self.tcl_path)
        TVM.clear_tcl_code()
        delete_dump()

def check_for_nested_dict(d)->bool:
    for key, value in d.items():
        if isinstance(value, dict):
            return True
    return False
def set_global_namespace(json_file):
    """
    This function sets the global namespace
    """
    with open(json_file, "r", encoding="utf-8") as file:
        data = json.load(file)
    TVM.set_class_vars(**data)

def create_verilog_maker(json_file: str) -> VerilogMaker:
    """
    This function creates a Verilog Maker
    """
    with open(json_file, "r", encoding="utf-8") as file:
        data = json.load(file)
    vm = VerilogMaker(**data["verilog"])
    for module_name, ip_data in data.get("ip", {}).items():
        ip_maker = IPMaker(**ip_data)
        ip_maker.module_name = module_name
        ip_maker.target_path = vm.target_path
        vm.ip.append(ip_maker)
    return vm

def ensure_directory_exists(directory_path):
    """ This function ensures that the directory exists and remove it if it exists"""
    if os.path.exists(directory_path):
        shutil.rmtree(directory_path)
        logging.warning("Directory %s is removed.",directory_path)
    try:
        os.makedirs(directory_path)
        logging.warning("Directory %s created.",directory_path)
    except OSError as error:
        logging.warning("Error creating directory %s: %s", directory_path, error)

def run_vivado_tcl(tcl_path):
    """
    This function runs the Vivado tcl
    """
    process = subprocess.Popen(
        [TVM.vivado_path, "-mode", "batch", "-source", tcl_path],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        universal_newlines=True, text=True
    )
    while process.poll() is None:
        out = process.stdout.readline()
        out = out.replace("\n","")
        logging.warning(out)
    _, stderr = process.communicate()
    logging.warning(stderr if stderr else "Vivado ended with no error")
    kill_process(process)

def kill_process(process):
    """
    This function kills the process
    """
    if process.poll() is None:
        logging.warning("Process is still running...")
        process.kill()
        logging.warning("Process is killed...")
    elif process.poll() == 0:
        logging.warning("Process is normally finished...")
    elif process.poll() == 1:
        logging.error("Process is abnormally finished...")

def delete_dump():
    """
    This function deletes the dump files
    """
    current_working_directory: str = os.getcwd()
    if os.path.exists(os.path.join(current_working_directory,"vivado.jou")):
        os.remove(os.path.join(current_working_directory,"vivado.jou"))
        logging.warning("vivado.jou is deleted")
    if os.path.exists(os.path.join(current_working_directory,"vivado.log")):
        os.remove(os.path.join(current_working_directory,"vivado.log"))
        logging.warning("vivado.log is deleted")
    if os.path.exists(os.path.join(current_working_directory,".Xil")):
        shutil.rmtree(os.path.join(current_working_directory,".Xil"))
        logging.warning(".Xil is deleted")

def main():
    """
    This is the main function
    """
    parser = argparse.ArgumentParser(
        description=(
            "Make SoC Block diagram with json files. You need "
            "configuration file which set directory of vivado and "
            "common directory path and json files which specifies "
            "the SoC design"
        )
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", 
        help="Increase output verbosity"
    )
    parser.add_argument("-c", "--config", help="Configuration file name")
    parser.add_argument("-f", "--verilog_json", help="verilog JSON file name")
    args = parser.parse_args()

    configuration = args.config if args.config else "configuration.json"
    verilog_json = (
        args.verilog_json if args.verilog_json
        else "verilog_json.json"
    )

    set_global_namespace(configuration)
    vm = create_verilog_maker(verilog_json)
    vm.make_tcl()
