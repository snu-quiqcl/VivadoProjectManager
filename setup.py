# -*- coding: utf-8 -*-
"""
Created on Tue May 14 17:19:44 2024

@author: alexi
"""

import shutil
import os
from setuptools import setup, find_packages, Command

class CleanCommand(Command):
    """Custom clean command to tidy up the project root."""
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        shutil.rmtree("build", ignore_errors=True)
        print("Removed build")
        egg_info = [f for f in os.listdir(".") if f.endswith(".egg-info")]
        for folder in egg_info:
            shutil.rmtree(folder, ignore_errors=True)
            print(f"Removed {folder}")

setup(
    name='VivadoPmgr',
    version='0.1',
    entry_points={
        'console_scripts': [
            'MakeVivadoProject=VivadoPmgr.Verilog_Creator:main',
            'MakeRFSoCProject=VivadoPmgr.RFSoC_Creator:main',
            'MakeZCU104Project=VivadoPmgr.ZCU104_Creator:main',
        ],
    },
    install_requires=[
    ],
    packages=find_packages(include=['VivadoPmgr', 'VivadoPmgr.*']),
    author='JeonghyunPark',
    author_email='alexist@snu.ac.kr',
    description=('This makes Vivado projects based on yout json meta file and'
                 'verilog files'),
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    url='https://github.com/snu-quiqcl/Vivado_prj_manager.git',
    classifiers=[
        'Programming Language :: Python :: 3',
        'Operating System :: Window',
    ],
    cmdclass={
        'clean': CleanCommand,
    }
)