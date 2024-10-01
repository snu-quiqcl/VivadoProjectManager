# Vivado_prj_manager
It is vivado project maker based on speicified json file. It requires two json files. In first json file, configuration json file, you should write your vivado environment and information about your FPGA board. For instance, path of vivado repository, and version of your vivado are required. In second json file, verilog json file, you should write your verilog code information. For instance, verilog code paths and IP configuration settings are required.

## Installation
Download git file and go to direcotry ```Vivado_prj_manager```. You can install Vivado project manager with below command. Actual package name is ```VivadoPmgr```.
```
pip install .
```
## Configuration JSON file
Below json file is example of configuration json file.

```json
{
    "common_path" : "VERILOG_FILE_PATH",
    "target_path" : "TARGET_PATH",
    "vivado_path" : "C:/Xilinx/Vivado/2020.2/bin/vivado.bat",
    "board_path" : "C:/Xilinx/Vivado/2020.2/data/boards/board_files",
    "part_name" : "xczu28dr-ffvg1517-2-e",
    "board_name" : "xilinx.com:zcu111:part0:1.4",
    "constraints" : "CONSTRAINT_FILE_PATH/ZCU111_Rev1.0.xdc",
    "version" : "2020.2"
}
```

+ ```common_path``` : Path common direcotry of which your verilog files exist. For example, common path of ```C:/A/verilog_file1.sv```, ```C:/A/verilog_file2.sv``` and ```C:/A/B/verilog_file3.sv``` is ```C:/A/```. You should write its relative path of verilog files when you make second json file, verilog json file
  
+ ```target_path``` : Path which you want to make vivado project. Vivado project will be created in ```target_path```, and if this path does not exist, it will be created automatically

+ ```vivado_path``` : Path of ```vivado.bat``` which runs actual vivado TCL code and make vivado project. Note that almost of ```vivado.bat``` is located in ```Xilinx/Vivado/2020.2/bin```

+ ```board_path``` : Path board files exist, and it is also located in ```Xilinx/Vivado/2020.2/data/boards/board_files``` mostly

+  ```part_name``` : Your xilinx chip part name

+  ```board_name``` : Your FPGA board name. If you don't know it's board name, you can make vivado manually, and check its TCL code. Or, if you have vivado project already, goto setting in vivado project and check it.

+  ```constraints``` : Your FPGA constraint file path and its name

+  ```version``` : Version of your vivado

## Verilog JSON file
Below json file is example of verilog json file.

```json
{
    "verilog" : {
        "name" : "TTL_out",
        "top": "TTL_out.sv",
        "top_module_name" : "TTL_out"
        "gen_ip" : "True",
        "files" : [
            "TTL_out/TTL_Controller.sv",
            "TTL_out/TTL_out.sv",
            "RTIO_Lib/AXI2FIFO.sv",
            "RTIO_Lib/GPO_Core.sv",
            "RTIO_Lib/RTOB_Core.sv",
            "RTIO_Lib/adj_fifo.sv"
        ]
    },
    "ip" : {
        "fifo_generator_0" : {
            "name" : "fifo_generator",
            "version" : "13.2",
            "vendor" : "xilinx.com",
            "library" : "ip",
            "tcl_options" : ["name", "version", "vendor", "library", "module_name"],
            "config" : {
                "Fifo_Implementation" : "Independent_Clocks_Builtin_FIFO",
                "Read_Clock_Frequency" : "125",
                ...
            }
        }
    }
}
```

### verilog section

In this section, you should write your vivado project information.
+ ```name``` : Your vivado project name

+ ```top``` : Top verilog file in your vivado project. Note that this is not different from top module name.

+ ```top_module_name``` : Top module name of verilog file in your vivado project. You should specify top module name in this option if your top module name is different from top file name. If not, top file will not be selected automatically.
  
+ ```gen_ip``` : This is option whether you make customized IP or not. Some string parameter makes error when you make customized IP, so you have to disable this option when generation IP makes error.
  
+ ```files``` : List of yout verilog files. Note that its path is relateive path to ```common_path``` which is specified in configuration json file

### ip section

In this section, you should write configuration of IPs which is used in you vivado project. It will make ```.xic``` file automatically and include this IP to your vivado project. In this example, ```fifo_generator_0``` is instance name(module_name) which you used in verilog codes. And below is your IP configurations.
+ ```name``` : IP name. Note that this is not instance name, and it is IP name

+ ```version``` : Version of IP

+ ```vendor``` : Vendor of IP. Note that xilinx provided IP has vendor of ```xilinx.com```

+ ```library``` : Its value is ```ip``` now, and there is no option now

+ ```tcl_options``` : TCL option which you will use. For instance, only ```name```, ```version```, ```vendor```, ```library```, ```module_name``` is used and ```config``` in ```fifo_generator_0``` ip section

+ ```config``` : Configuration of IP. You should specify each key and value manually. If you want to get configuration of your IP, enter ```report_property [get_ips "IP where you want to export configuration"]``` in vivado console.

## Making Vivado Project
You can make vivado project with below command. Vivado will run automatically and its state will be printed on the display.
```
MakeVivadoProject -c configuration.json -f verilog.json
```

## Making RFSoC Project
You can make rfsoc project and fully connected block diagram with below command. Vivado will run automatically and its state will be printed on the display.
```
MakeRFSoCProject -c configuration.json -f soc.json
```

## Making ZCU104 Project
You can make zcu104 project and empty block diagram with below command. Vivado will run automatically and its state will be printed on the display.
```
MakeZCU104Project -c configuration.json -f soc.json
```
