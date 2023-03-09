#!/bin/bash
#
#  Copyright 2021 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License"). You may not use this file except in compliance
#  with the License. A copy of the License is located at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  or in the 'license' file accompanying this file. This file is distributed on an 'AS IS' BASIS, WITHOUT WARRANTIES
#  OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions
#  and limitations under the License.
#


# Check to see if the required parameters have been provided:
if [ -z "$1" ] || [ -z "$2" ] || [ -z "$3" ]; then
    echo "Please provide the base source bucket name, trademark approved solution name and version where the lambda code will eventually reside."
    echo "For example: ./build-s3-dist.sh solutions trademarked-solution-name v1.0.0"
    exit 1
fi

export DIST_OUTPUT_BUCKET=$1
export SOLUTION_NAME=$2
export VERSION=$3

# Get reference for all important folders
project_root="$PWD/.."
deployment_dir="$PWD"
#output folders
global_dist_dir="$deployment_dir/global-s3-assets"
regional_dist_dir="$deployment_dir/regional-s3-assets"

#build directories
build_dir="$project_root/build"
cdk_out_dir="$build_dir/cdk.out"

#project folders
lambda_source_dir="$project_root/source/app" #not currently needed, but here for reference
cli_source_dir="$project_root/source/cli"
cdk_source_dir="$project_root/source/infrastructure"




[ "$DEBUG" == 'true' ] && set -x
set -e

echo "------------------------------------------------------------------------------"
echo "[Init] Remove any old dist files from previous runs"
echo "------------------------------------------------------------------------------"

echo "rm -rf $global_dist_dir"
rm -rf $global_dist_dir
echo "mkdir -p $global_dist_dir"
mkdir -p $global_dist_dir
echo "rm -rf $regional_dist_dir"
rm -rf $regional_dist_dir
echo "mkdir -p $regional_dist_dir"
mkdir -p $regional_dist_dir
echo "rm -rf $build_dir"
rm -rf $build_dir
echo "mkdir -p $build_dir"
mkdir -p $build_dir
echo "rm -rf $cdk_out_dir"
rm -rf $cdk_out_dir


echo "------------------------------------------------------------------------------"
echo "[Synth] CDK Project"
echo "------------------------------------------------------------------------------"

# Install the npm install in the source folder
echo "cd $cdk_source_dir"
cd "$cdk_source_dir"
echo "npm ci"
npm ci
echo "node_modules/aws-cdk/bin/cdk synth --output=$build_dir"
node_modules/aws-cdk/bin/cdk synth --no-version-reporting

echo "------------------------------------------------------------------------------"
echo "[Packing] Template artifacts"
echo "------------------------------------------------------------------------------"

# copy templates to global_dist_dir
echo "Move templates from staging to global_dist_dir"
echo "cp $cdk_out_dir/*.template.json $global_dist_dir/"
cp "$cdk_out_dir"/*.template.json "$global_dist_dir"/


# Rename all *.template.json files to *.template
echo "Rename all *.template.json to *.template"
echo "copy templates and rename"
for f in $global_dist_dir/*.template.json; do
    mv -- "$f" "${f%.template.json}.template"
done


echo "------------------------------------------------------------------------------"
echo "[CDK-Helper] Copy the Lambda Asset"
echo "------------------------------------------------------------------------------"
cd "$deployment_dir"/cdk-solution-helper/asset-packager && npm ci
npx ts-node ./index "$cdk_out_dir" "$regional_dist_dir"

echo "------------------------------------------------------------------------------"
echo "[Scheduler-CLI] Package the Scheduler cli"
echo "------------------------------------------------------------------------------"
cp -pr $cli_source_dir $build_dir/
cd "$build_dir/cli"
echo "Build the scheduler cli package"
mv ./setup.py ./setup.bak.py
echo "update the version in setup.py"
sed "s/#version#/$DIST_VERSION/g" ./setup.bak.py > ./setup.py
rm setup.bak.py
echo "update the version in scheduler_cli.py"
mv ./scheduler_cli/scheduler_cli.py ./scheduler_cli/scheduler_cli.bak.py
sed "s/#version#/$DIST_VERSION/g" ./scheduler_cli/scheduler_cli.bak.py > ./scheduler_cli/scheduler_cli.py
rm ./scheduler_cli/scheduler_cli.bak.py
zip -q --recurse-paths ./scheduler-cli.zip scheduler_cli/* setup.py instance-scheduler-cli-runner.py

echo "Copy the scheduler cli package to $global_dist_dir"
cp -pr ./scheduler-cli.zip $global_dist_dir/
