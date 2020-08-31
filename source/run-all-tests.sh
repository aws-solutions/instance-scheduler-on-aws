#!/bin/bash
#
# This script runs all tests for the root CDK project, as well as any microservices, Lambda functions, or dependency 
# source code packages. These include unit tests, integration tests, and snapshot tests.
# 
# This script is called by the ../initialize-repo.sh file and the buildspec.yml file. It is important that this script 
# be tested and validated to ensure that all available test fixtures are run.
#
# The if/then blocks are for error handling. They will cause the script to stop executing if an error is thrown from the
# node process running the test case(s). Removing them or not using them for additional calls with result in the 
# script continuing to execute despite an error being thrown.

# Save the current working directory
source_dir=$PWD

# Test the CDK project
npm install
npm run test
if [ "$?" = "1" ]; then
	echo "(source/run-all-tests.sh) ERROR: there is likely output above." 1>&2
	exit 1
fi

# Return to the source/ level
cd $source_dir