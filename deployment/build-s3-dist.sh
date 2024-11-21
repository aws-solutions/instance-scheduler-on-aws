#!/usr/bin/env bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
[[ $DEBUG ]] && set -x
set -e -o pipefail

header() {
    declare text=$1
    echo "------------------------------------------------------------------------------"
    echo "$text"
    echo "------------------------------------------------------------------------------"
}

usage() {
    echo "Please provide the base source bucket name, trademark approved solution name and version where the lambda code will eventually reside."
    echo "For example: ./build-s3-dist.sh solutions trademarked-solution-name v1.0.0"
}

main() {
    if [ ! "$1" ] || [ ! "$2" ] || [ ! "$3" ]; then
        usage
        exit 1
    fi
    set -u

    declare DIST_OUTPUT_BUCKET=$1 SOLUTION_NAME=$2 VERSION=$3
    # Check to see if the required parameters have been provided:


    export DIST_OUTPUT_BUCKET
    export SOLUTION_NAME
    export VERSION

    # Get reference for all important folders
    local project_root=$(dirname "$(cd -P -- "$(dirname "$0")" && pwd -P)")
    local deployment_dir="$project_root"/deployment
    #output folders
    local global_dist_dir="$deployment_dir"/global-s3-assets
    local regional_dist_dir="$deployment_dir"/regional-s3-assets

    #build directories
    local build_dir="$project_root"/build
    local cdk_out_dir="$build_dir"/cdk.out

    #project folders
    local cli_source_dir="$project_root/source/cli"

    header "[Init] Remove any old dist files from previous runs"

    rm -rf "$global_dist_dir"
    mkdir -p "$global_dist_dir"
    rm -rf "$regional_dist_dir"
    mkdir -p "$regional_dist_dir"
    rm -rf "$build_dir"
    mkdir -p "$build_dir"

    header "[Synth] CDK Project"

    npm run synth -- --no-version-reporting

    header "[Packing] Template artifacts"

    # copy templates to global_dist_dir
    echo "Move templates from staging to global_dist_dir"
    cp "$cdk_out_dir"/*.template.json "$global_dist_dir"/

    # Rename all *.template.json files to *.template
    echo "Rename all *.template.json to *.template"
    echo "copy templates and rename"
    for f in "$global_dist_dir"/*.template.json; do
        mv -- "$f" "${f%.template.json}.template"
    done

    header "[CDK-Helper] Copy the Lambda Asset"
    pushd "$deployment_dir"/cdk-solution-helper/asset-packager
    npm ci
    npx ts-node ./index "$cdk_out_dir" "$regional_dist_dir"
    popd

    header "[Scheduler-CLI] Package the Scheduler cli"
    pushd "$cli_source_dir"
    python -m poetry build
    cp -r ./dist "$build_dir/instance_scheduler_cli"
    popd

    pushd "$build_dir"
    zip -r "$global_dist_dir/instance_scheduler_cli.zip" "instance_scheduler_cli"
    popd
}

main "$@"
