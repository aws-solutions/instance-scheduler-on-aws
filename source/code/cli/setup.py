######################################################################################################################
#  Copyright 2016 Amazon.com, Inc. or its affiliates. All Rights Reserved.                                           #
#                                                                                                                    #
#  Licensed under the Amazon Software License (the "License"). You may not use this file except in compliance        #
#  with the License. A copy of the License is located at                                                             #
#                                                                                                                    #
#      http://aws.amazon.com/asl/                                                                                    #
#                                                                                                                    #
#  or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES #
#  OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions    #
#  and limitations under the License.                                                                                #
######################################################################################################################

from setuptools import setup

setup(
    name="scheduler-cli",
    packages=["scheduler_cli"],
    entry_points={
        "console_scripts": ['scheduler-cli = scheduler_cli.scheduler_cli:main']
    },
    version="#version#",
    description="AWS Instance Scheduler CLI",
    install_requires=[
        "argparse",
        "requests>=2.18.4",
        "jmespath>=0.9.3",
        "boto3>=1.4.7"]
)

