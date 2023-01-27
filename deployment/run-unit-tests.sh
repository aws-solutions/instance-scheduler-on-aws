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


set -e #fail script if any commands fail

#relevant directories
source_template_dir=$PWD #/deployment
root_dir="$source_template_dir/.."
cdk_src_dir="$source_template_dir/../source"
lamda_src_dir="$source_template_dir/../source/lambda"
coverage_reports_dir="$source_template_dir/coverage-reports"



echo "------------------------------------------------------------------------------"
echo "Running Unit Tests"
echo "------------------------------------------------------------------------------"
echo "Working Directory: $PWD"
echo "CDK Sources Directory: $cdk_src_dir"
echo "Lambda Sources Directory: $lamda_src_dir"
echo "Coverage Reports Directory: $coverage_reports_dir"

mkdir -p "$coverage_reports_dir"

echo "------------------------------------------------------------------------------"
echo "Installing Tox"
echo "------------------------------------------------------------------------------"
cd "$root_dir" || (echo "$root_dir does not exist" && exit 1)
pip install tox

echo "------------------------------------------------------------------------------"
echo "Starting CDK Unit Test"
echo "------------------------------------------------------------------------------"
cdk_coverage_report_path="$coverage_reports_dir/cdk-coverage"
echo "running tests and saving coverage to $coverage_reports_dir"
tox -e cdk --exit-and-dump-after 1200 -- --coverage --coverageDirectory "$cdk_coverage_report_path"

echo "------------------------------------------------------------------------------"
echo "Starting Lambda Unit Tests"
echo "------------------------------------------------------------------------------"
lambda_coverage_report_path="$coverage_reports_dir/lambda-coverage.xml"
echo "running tests and saving coverage to $lambda_coverage_report_path"
tox -e lambda --exit-and-dump-after 1200 -- --cov --cov-report "xml:$lambda_coverage_report_path"

# Return to calling dir (/deployment)
cd $source_template_dir