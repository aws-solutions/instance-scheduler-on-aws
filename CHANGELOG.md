# Change Log
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
## [1.3.3] - 2020-08-31
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
