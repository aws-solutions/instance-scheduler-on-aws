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

# Important: CDK global version number
cdk_version=2.62.2

# Check to see if the required parameters have been provided:
if [ -z "$1" ] || [ -z "$2" ] || [ -z "$3" ]; then
    echo "Please provide the base source bucket name, trademark approved solution name and version where the lambda code will eventually reside."
    echo "For example: ./build-s3-dist.sh solutions trademarked-solution-name v1.0.0"
    exit 1
fi

export DIST_VERSION=$3
export DIST_OUTPUT_BUCKET=$1
export SOLUTION_ID=SO0030
export SOLUTION_NAME=$2
export SOLUTION_TRADEMARKEDNAME=$2

# Get reference for all important folders
template_dir="$PWD"
staging_dist_dir="$template_dir/staging"
global_dist_dir="$template_dir/global-s3-assets"
regional_dist_dir="$template_dir/regional-s3-assets"
lambda_source_dir="$template_dir/../source/app"
cli_source_dir="$template_dir/../source/cli"
cdk_source_dir="$template_dir/../source/infrastructure"



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
echo "rm -rf $staging_dist_dir"
rm -rf $staging_dist_dir
echo "mkdir -p $staging_dist_dir"
mkdir -p $staging_dist_dir

echo "------------------------------------------------------------------------------"
echo "[Synth] CDK Project"
echo "------------------------------------------------------------------------------"

# Install the global aws-cdk package
echo "cd $cdk_source_dir"
cd $cdk_source_dir
echo "npm install aws-cdk@$cdk_version"
npm install aws-cdk@$cdk_version

echo "------------------------------------------------------------------------------"
echo "NPM Install in the source folder"
echo "------------------------------------------------------------------------------"

# Install the npm install in the source folder
echo "npm install"
npm install

# Run 'cdk synth' to generate raw solution outputs
echo "cd "$cdk_source_dir""
cd "$cdk_source_dir"
echo "node_modules/aws-cdk/bin/cdk synth --output=$staging_dist_dir"
npm run build && node_modules/aws-cdk/bin/cdk synth --output=$staging_dist_dir --no-version-reporting

# Remove unnecessary output files
echo "cd $staging_dist_dir"
cd "$staging_dist_dir"
echo "rm tree.json manifest.json cdk.out"
rm tree.json manifest.json cdk.out

echo "------------------------------------------------------------------------------"
echo "[Packing] Template artifacts"
echo "------------------------------------------------------------------------------"

# Move outputs from staging to global_dist_dir
echo "Move outputs from staging to global_dist_dir"
echo "cp $template_dir/*.template $global_dist_dir/"
cp $staging_dist_dir/*.template.json $global_dist_dir/
rm *.template.json

# Rename all *.template.json files to *.template
echo "Rename all *.template.json to *.template"
echo "copy templates and rename"
for f in $global_dist_dir/*.template.json; do
    mv -- "$f" "${f%.template.json}.template"
done

echo "------------------------------------------------------------------------------"
echo "[Packing] Source code lambda python artifacts and scheduler-cli artifacts"
echo "------------------------------------------------------------------------------"
echo "Copy the python lambda files from source/lambda directory to staging lambda directory"
cp -pr $lambda_source_dir $staging_dist_dir/
cp -pr $cli_source_dir $staging_dist_dir/

echo "Update the version information in version.py"
cd $staging_dist_dir/app
mv version.py version.py.org
sed "s/%version%/$DIST_VERSION/g" version.py.org > version.py

echo "Install all the python dependencies in the staging directory before packaging"
pip3 install -U -r $lambda_source_dir/requirements.txt -t $staging_dist_dir/app/

echo "Build lambda distribution packaging"
zip -q --recurse-paths ./instance-scheduler.zip version.txt main.py version.py configuration/* requesthandlers/* chardet/* urllib3/* idna/* requests/* schedulers/* util/* boto_retry/* models/* pytz/* certifi/*
echo "Copy lambda distribution to $regional_dist_dir"
cp -pr ./instance-scheduler.zip $regional_dist_dir/

echo "cd into the scheduler cli folder ./cli"

cd ../cli
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
