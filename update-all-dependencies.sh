# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

echo "Upgrading projen..."
projen upgrade

echo "Upgrading root npm..."
npm update

echo "Upgrading app..."
pushd source/app || exit
poetry update
popd || exit

echo "Upgrading cli..."
pushd source/cli || exit
poetry update
popd || exit

echo "Upgrading cdk-solution-helper..."
pushd deployment/cdk-solution-helper || exit
npm update
popd || exit

echo "All dependencies successfully updated"
echo "If you need to also update the solution and/or CDK version, do so inside .projenrc.ts and then re-run this script"