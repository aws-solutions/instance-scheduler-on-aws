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
echo $PWD
# Test the CDK project
npm install
npm run build && npm run test
rc=$?
if [ $rc = "1" ]; then
	echo "cdk snapshot tests failed." 1>&2
	exit 1
fi


# Run the lambda python tests
cd ./lambda || return $?
pip install -r testing_requirements.txt
#python3 -m pytest ./tests --cov=$CWD --cov-report xml
mkdir -p coverage-reports/
coverage_report_path_for_lambda=coverage-reports/coverage-lambda.xml
python3 -m pytest tests/ --cov --cov-report term-missing --cov-report "xml:$coverage_report_path_for_lambda"
rc=$?
if [ $rc = "1" ]; then
	echo "Lambda unit tests failed." 1>&2
	exit 1
fi
cd ../runbooks/ssm-py-scripts || return $?
mkdir -p coverage-reports/
coverage_report_path_for_runbook=coverage-reports/coverage-runbooks.xml
python3 -m pytest tests/ --cov --cov-report term-missing --cov-report "xml:$coverage_report_path_for_runbook"

rc=$?
if [ $rc = "1" ]; then
	echo "ssm runbook unit tests failed." 1>&2
	exit 1
fi

# The pytest --cov with its parameters and .coveragerc generates a xml cov-report with `coverage/sources` list
# with absolute path for the source directories. To avoid dependencies of tools (such as SonarQube) on different
# absolute paths for source directories, this substitution is used to convert each absolute source directory
# path to the corresponding project relative path. The $source_dir holds the absolute path for source directory.
source_dir_generate_in_xml=$source_dir
source_dir_final_in_xml=$source_dir/lambda/coverage-reports/coverage-lambda.xml
source_dir_final_in_xml_runbook=$source_dir/runbooks/ssm-py-scripts/coverage-reports/coverage-runbooks.xml
sed -i -e "s,<source>${source_dir_generate_in_xml}/lambda,<source>source/lambda,g" $source_dir_final_in_xml
sed -i -e "s,<source>${source_dir_generate_in_xml}/runbooks/ssm-py-scripts,<source>source/runbooks/ssm-py-scripts,g" $source_dir_final_in_xml_runbook
rc=$?
if [ $rc = "1" ]; then
	echo "(source/run-all-tests.sh) ERROR: updating the changes to the coverage report which is required for sonar to identify code coverage." 1>&2
	exit 1
fi

# Return to the source/ level
cd $source_dir