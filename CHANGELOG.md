# Change Log
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2021-09-30
### Added
- Custom Automation runbooks (capability of AWS Systems Manager) to start and stopping EC2 and RDS resources in multiple AWS Regions and accounts.
- Support for AWS Organizations - no need to maintain a list of accounts. 
### Update
- Simplify user experience by updating cross-account IAM role setup.
- Custom namespace to maintain instance scheduling for different environments.
### Removed
- Create RDS Snapshot before stopping the RDS instance. This feature is pending update to AWS managed runbook and will be added in the next release.

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
