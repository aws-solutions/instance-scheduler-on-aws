# Change Log

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.5.3] - 2023-10-22

### Security

- Upgrade @babel/traverse to mitigate CVE-2023-45133
- Upgrade urllib3 to mitigate CVE-2023-45803

## [1.5.2] - 2023-10-9

### Security

- Upgrade cryptography to mitigate GHSA-v8gr-m533-ghj9 and GHSA-jm77-qphf-c4w8
- Upgrade urllib3 to mitigate CVE-2023-43804
- Upgrade certifi to mitigate CVE-2023-37920

## [1.5.1] - 2023-07-24

### Changed

- Add a default start and stop tag
- Use EC2 API more efficiently when filtering EC2 instances for scheduling
- Use system tzdata instead of pytz
- Upgrade Python runtime to 3.10
- Package CLI as sdist and wheel
- Refactoring, type hinting, and improved testing
- Add projen for managing project configuration

### Fixed

- Restore Python 3.8 support to CLI
- Fix bug starting EC2 instances at least 10 minutes before maintenance windows
- Fix bug targeting RDS instances that are part of an Aurora cluster for scheduling
- Fix bug where EC2 instances failing to start or stop cause an entire batch to fail to start or stop
- Fix bug where the instance type field on a period in a CloudFormation schedule has no effect
- Fix bug creating CloudWatch log streams when hub scheduling is disabled

### Security

- Upgrade cryptography to mitigate CVE-2023-38325 and CVE-2023-2650
- Upgrade aws-cdk-lib to mitigate CVE-2023-35165
- Upgrade fast-xml-parser to mitigate CVE-2023-34104
- Upgrade requests to mitigate CVE-2023-32681
- Upgrade word-wrap to mitigate CVE-2023-26115
- Upgrade semver to mitigate CVE-2022-25883

## [1.5.0] - 2023-04-27

### Added

- Enable solution to support deployment using organization id.
- Lambda code is organized with tox.
- Development/e2e testing pipeline included under source/infrastructure/pipeline capable of automatically deploying and
  testing solution.
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

- Replaced the DescribeLogStreams API call used for getting the next sequence token with PutLogEvents API call to reduce
  the lambda execution time [#307](https://github.com/aws-solutions/instance-scheduler-on-aws/issues/307)

## [1.4.0] - 2021-04-26

### Added

- Enable solution to be deployed as mutliple stacks in the same account/region

### Fixed

- Fix the SSM Maintenance window issue where solution was not fetching SSM Maintenance windows from other
  account/regions
- Updated logging utility to remove incorrect timestamp
- Fixed issue with scheduler stopping instances at UTC time even when configured with other timezones and Period having
  weekday configured as Wed#4. [Github Issue](https://github.com/aws-solutions/instance-scheduler-on-aws/issues/238)
- Modified Anonymous Data reporting refer implementation guide for details.
- Removed redundant logging of UTC timestamp along with the Account/Region default stamp in logs in AWS CloudWatch.
- Fixed [Github Issue](https://github.com/aws-solutions/instance-scheduler-on-aws/issues/184) for scheduler-cli.

## [1.3.3] - 2020-08-31

### Fixed

- Update the project to utilize aws cdk constructs for cloudformation template creation.
- Fix the issue for ensuring throttling is avoided to cloudwatch API's from github PR
  [#177](https://github.com/aws-solutions/instance-scheduler-on-aws/pull/177)

## [1.3.2] - 2020-06-22

### Fixed

- Fix the issue to start instances before the SSM maintenance window beings
  [#101](https://github.com/aws-solutions/instance-scheduler-on-aws/issues/101)
- Updated the SSM feature to reduce lambda cost
- Added HIBERNATE to the list of valid schedule properties

## [1.3.1] - 2020-03-10

### Fixed

- Fix the issue for new instances launched outside of the schedule period
  [#127](https://github.com/aws-solutions/instance-scheduler-on-aws/issues/127)
- Fix the issue for retries failures to due incompatible code
  [#133](https://github.com/aws-solutions/instance-scheduler-on-aws/issues/133)
- Fix the issue for instances being stopped after maintenance window begins
  [#101](https://github.com/aws-solutions/instance-scheduler-on-aws/issues/101)

## [1.3.0] - 2019-08-26

### Added

- Upgraded the Solution to Python 3.7
