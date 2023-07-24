#!/bin/bash
#
#  Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#  SPDX-License-Identifier: Apache-2.0
#

#
# This assumes all of the OS-level configuration has been completed and git repo has already been cloned
#
# This script should be run from the repo's deployment directory

#"$DEBUG" == 'true' -> enable detailed messages.
#set -x enables a mode of the shell where all executed commands are printed to the terminal
[[ $DEBUG ]] && set -x
set -eou pipefail

solution_name="instance-scheduler-on-aws"

# Get reference for all important folders
project_root="$PWD/.."
deployment_dir="$PWD"
open_source_dist_dir="$deployment_dir/open-source"

echo "------------------------------------------------------------------------------"
echo "[Init] Remove any old dist files from previous runs"
echo "------------------------------------------------------------------------------"

rm -rf $open_source_dist_dir
mkdir -p $open_source_dist_dir

echo "------------------------------------------------------------------------------"
echo "Create zip"
echo "------------------------------------------------------------------------------"

cd $project_root

zip -q -r9 "$open_source_dist_dir"/"$solution_name" . \
   -x ".git/*" \
   -x "*/.idea/*" \
   -x "*/.mypy_cache/*" \
   -x "*/.pytest_cache/*" \
   -x "*/__pycache__/*" \
   -x "*/.tox/*" \
   -x "*/.coverage" \
   -x "coverage/*" \
   -x ".venv/*" \
   -x "*/.venv/*" \
   -x "build/*" \
   -x "deployment/global-s3-assets/*" \
   -x "deployment/open-source/*" \
   -x "deployment/regional-s3-assets/*" \
   -x "deployment/test-reports/*" \
   -x "deployment/coverage-reports/*" \
   -x "node_modules/*" \
   -x "*/node_modules/*" \
   -x "*/dist/*" \
   -x "*/cdk.out/*" \
   -x ".viperlightrc.*" \
   -x "codescan-*.sh"

cd $deployment_dir
echo "Completed building $solution_name.zip dist"
