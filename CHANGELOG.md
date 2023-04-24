# Change Log
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.5.0] - 2023-04-27
### Added
- Enable solution to support deployment using organization id.
- Lambda code is organized with tox.
- Development/e2e testing pipeline included under source/infrastructure/pipeline capable of automatically deploying and testing solution.
- App Registry integration
### Fixed
- Boto Retry module could cause unintended high lambda utilization in case of API failures.
- Cross account scheduling no longer requires IAM role name but only account id.

## [1.4.2] - 2023-01-11
### Fixed
- Upgrade certifi to mitigate [CVE-2022-23491](https://nvd.nist.gov/vuln/detail/CVE-2022-23491).
- Updated issues in bandit scan.
- Updated the CDK version 2.x

## [1.4.1] - 2022-05-12
### Fixed
- Replaced the DescribeLogStreams API call used for getting the next sequence token with PutLogEvents API call to reduce the lambda execution time [#307](https://github.com/awslabs/aws-instance-scheduler/issues/307)

## [1.4.0] - 2021-04-26
### Added
- Enable solution to be deployed as mutliple stacks in the same account/region
### Fixed
- Fix the SSM Maintenance window issue where solution was not fetching SSM Maintenance windows from other account/regions
- Updated logging utility to remove incorrect timestamp
- Fixed issue with scheduler stopping instances at UTC time even when configured with other timezones and Period having weekday configured as Wed#4. [Github Issue](https://github.com/awslabs/aws-instance-scheduler/issues/238)
- Modified Anonymous Data reporting refer implementation guide for details.
- Removed redundant logging of UTC timestamp along with the Account/Region default stamp in logs in AWS CloudWatch.
- Fixed [Github Issue](https://github.com/awslabs/aws-instance-scheduler/issues/184) for scheduler-cli.

## [1.3.3] - 2020-08-31
### Fixed
- Update the project to utilize aws cdk constructs for cloudformation template creation.
- Fix the issue for ensuring throttling is avoided to cloudwatch API's from github PR [#177](https://github.com/awslabs/aws-instance-scheduler/pull/177)
## [1.3.2] - 2020-06-22
### Fixed
- Fix the issue to start instances before the SSM maintenance window beings [#101](https://github.com/awslabs/aws-instance-scheduler/issues/101)
- Updated the SSM feature to reduce lambda cost 
- Added HIBERNATE to the list of valid schedule properties


## [1.3.1] - 2020-03-10
### Fixed
- Fix the issue for new instances launched outside of the schedule period [#127](https://github.com/awslabs/aws-instance-scheduler/issues/127)
- Fix the issue for retries failures to due incompatible code [#133](https://github.com/awslabs/aws-instance-scheduler/issues/133)
- Fix the issue for instances being stopped after maintenance window begins [#101](https://github.com/awslabs/aws-instance-scheduler/issues/101)

## [1.3.0] - 2019-08-26
### Added
- Upgraded the Solution to Python 3.7
