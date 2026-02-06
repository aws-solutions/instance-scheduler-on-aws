# Change Log

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [v3.1.2] - 2025-02-06

### Fixed

- Fixed deployment errors in GovCloud
- Namespace now properly applied to EventRules allowing for
  multiple parallel deployments of Instance Scheduler in the same account
- Fixed CFN Stack Delete race-case that would sometimes cause resource deregistration to fail
  and hang the stack
- Fixed RDS registration filters to properly handle when cluster-snapshot resources are tagged.

### Changed

- Updated registration logs to include `resource` context key
  containing the registered/deregistered resource's ARN

## [v3.1.1] - 2025-01-13

### Added

- IS-Error tag now includes time of when the error was last updated

### Changed

- Short-circuit configuration errors (Unknown Schedule, Unsupported Resource, Incompatible Schedule) no longer reported
  to event-bus as scheduling errors

### Security

- Updated urllib3 to mitigate CVE-2026-21441
- Updated Werkzeug to mitigate CVE-2026-21860

## [3.1.0] - 2025-12-18

### Added

- Added Support for License Manager controlled EC2 instances
- Added `IS-MinDesiredMax` control tag to ASGs to simplify management of ASG resources
- Added support for retrying Insufficient Capacity Errors on EC2 with different instance sizes
  - Use `IS-PreferredInstanceTypes` control tag to specify acceptable instance types that can be used
- Added `IS-GlobalEvents` (in hub) and `IS-LocalEvents` (in all targets) event buses that will output the following events:
  - `Resource Registered` whenever a resource is registered for scheduling
  - `Scheduling Action` whenever a resource is started/stopped by the scheduler

### Changed

- Instance Scheduler now listens for tagging events and tracks managed instances in an internal
`registry` table
  - Optimized scheduling orchestration to improve scaling performance for larger deployments.
- Managed regions is now defined per-account in the remote stack rather than globally on the hub stack
- Instance Scheduler will now apply informational tags to resources during scheduling:
  - `IS-ManagedBy` -- indicates location of Instance Scheduler Hub Stack
  - `IS-LastAction` -- displays the last successful action taken by instance scheduler
  - `IS-Error` -- displays error code when errors occur during scheduling
  - `IS-ErrorMessage` -- displays additional information about the most recent error code
- Cleaned up Operational Insights dashboard and added widgets to display ASG scheduling metrics
- Brought ASG scheduling flows inline with other scheduling flows
- Moved logs into dedicated `-scheduling-logs` and `-administrative-logs` log groups
- Restructured logs to use structured-logging optimized for log-insights queries and provided pre-canned
queries that can be used in the CloudWatch Log Insights console.

### Removed

- Listing member accounts via an SSM parameter (passing
  `{param: ssm-param-name}` to the accounts parameter on the hub stack)
  is no longer supported.
- Scheduled instance resizing (defining `period-name@size` in a schedule)
  is no longer supported.
- Started/Stopped tags configuration parameter on hub stack has been removed (replaced by informational tagging feature)
- Deployments of more than 40 accounts must now use organizations mode
- EnableXXXScheduling properties removed -- Service-specific scheduling is now handled automatically in response to tagging events
- Removed per-schedule metrics from cloudwatch

### Security

- Updated Filelock to mitigate CVE-2025-68146
- Updated js-yaml to mitigate CVE-2025-64718

## [3.0.12] - 2025-12-10

### Security

- Updated urllib3 to mitigate CVE-2025-66471

## [3.0.11] - 2025-07-29

### Security

- Updated urllib3 to mitigate CVE-2025-50182
- Updated requests to mitigate CVE-2024-47081
- Updated brace-expansion to mitigate CVE-2025-5889
- Updated OpenSSL to mitigate CVE-2024-12797

### Changed

- Minimum supported version of scheduler CLI raised from Python 3.9 to Python 3.11

### Removed

- Removed AppRegistry integration

## [3.0.10] - 2025-05-22

### Security

- Upgrade setuptools to mitigate CVE-2025-47273
- Upgrade aws-cdk to mitigate GHSA-5pq3-h73f-66hr and GHSA-qc59-cxj2-c2w4

### Changed

- Updated Lambda default memory size to 512MB

## [3.0.9] - 2025-04-10

### Security

- Upgrade Jinja2 to mitigate CVE-2025-27516
- Upgrade aws-cdk to mitigate CVE-2025-2598
- Upgrade esbuild to mitigate GHSA-67mh-4wv8-2f99
- Upgrade OpenSSL to mitigate CVE-2024-12797

### Changed

- Reintroduced --use-maintenance-window flag for schedules. The flag will be enabled by default but can be set to false
  to disable RDS preferred maintenance windows and EC2 maintenance windows

## [3.0.8] - 2025-01-31

### Changed

- Upgrade AWS Powertools from V2 to V3

### Security

- Upgrade jinja to mitigate CVE-2024-56201 and CVE-2024-56326

## [3.0.7] - 2024-11-21

### Security

- Upgrade cross-spawn to mitigate CVE-2024-21538

## [3.0.6] - 2024-11-07

### Changed

- RDS instances will now be automatically started 10 minutes prior to their preferred maintenance windows

### Fixed

- Clamped role session name to 64 characters to fix scenario where longer
  namespaces could cause runtime errors during sts assume
- Fixed long-term retry logic for EC2/RDS scheduling.
EC2 and RDS will now retry start actions on instances that failed during the previous scheduling cycle
- Fixed AccessDenied error when spoke account self-registration process attempted to create a log group

### Security

- Upgrade Werkzeug to mitigate CVE-2024-49766 and CVE-2024-49767

## [3.0.5] - 2024-10-01

### Fixed

- Fixed bug in Nth weekday logic that would sometimes cause Nth weekday to be interpreted as 1 week too early

### Changed

- added rds:CreateDBSnapshot and rds:AddTagsToResource snapshot to scheduling roles to support recent changes to
  RDS IAM requirements.

### Security

- Upgrade pyca/cryptography to mitigate GHSA-h4gh-qq45-vh27

## [3.0.4] - 2024-08-30

### Fixed

- Fixed China region compatibility issues by adding new -cn variants of solution stack templates
- Fixed bug in RDS Scheduling Logic that would cause the scheduler to crash when more than 100
  tagged RDS instances were present in a single scheduling target

### Added

- added SECURITY.md file with instructions on how security issues can be reported to AWS

## [3.0.3] - 2024-07-31

### Security

- Upgrade fast-xml-parser to mitigate CVE-2024-41818

## [3.0.2] - 2024-07-24

### Fixed

- Fixed an error that caused CloudFormation-managed schedules using the (now deprecated) UseMaintenanceWindow flag be an un-updatable

### Security

- Upgrade Certifi to mitigate CVE-2024-39689

## [3.0.1] - 2024-06-27

### Changed

- Scheduler CLI installation process now uses a version-agnostic installation process
- Lambda memory size for orchestration and asg scheduling lambdas is now configurable

### Fixed

- Fixed an error that would cause maintenance window scheduling to fail when the SSM api returned expired maintenance windows without a `NextExecutionTime` property
- Fixed KMS encryption key being deleted when DynamoDB tables were configured to be retained on stack delete
- Fixed an error that caused ASG schedule updates to fail when more than 5 schedules were updated at once
- Fixed a possible name conflict with Operational Insights Dashboard when deploying multiple copies of Instance Scheduler to the same account

### Security

- Upgrade braces to mitigate CVE-2024-4068
- Upgrade urllib3 to mitigate CVE-2024-37891

### Removed

- Removed e2e testing pipeline from public assets

## [3.0.0] - 2024-06-05

### Added

- Added support for scheduling of Neptune and DocumentDB clusters
- Added support for scheduling of ASG through the automatic creation of Scheduled Scaling Rules from configured schedules
- Added optional Operational Insights Dashboard to CloudWatch for monitoring and insights into solution performance
- Added support for using multiple EC2 maintenance windows with a single schedule
- Added ability to specify KMS keys that Instance Scheduler should be granted permissions to use when starting
  EC2 instances with encrypted EBS volumes

### Changed

- Separated "Scheduled Services" parameter into individual enabled/disabled parameters for each supported service
- Upgrade Python runtime to 3.11
- Extensive refactoring to internal code to improve code quality and testability
- CloudWatch metrics feature renamed to "Per Schedule Metrics" and integrated with new Operational Insights Dashboard
- DynamoDB Deletion Protection now enabled by default on solution DynamoDB tables.
- Refactored maintenance window dynamodb table to be more cost-efficient at scale
- Updated schedule logs to include SchedulingDecision entries for all decisions made by the EC2/RDS schedulers.
- Scheduler CLI will now error when attempting to overwrite schedules managed by CloudFormation

### Removed

- Configuration settings from CloudFormation parameters no longer duplicated in DynamoDB
- Remove deprecated "overwrite" Schedule flag (distinct from still-supported "override" flag)
- Cloudwatch Metrics feature replaced with Operational Monitoring

### Fixed

- Fixed deployment error in China partition, introduced in v1.5.0
- Fixed bug where CloudFormation Schedules used UTC timezone if not specified in template (instead of stack default)
- Fixed bug that would cause the scheduling request handler lambda would hang when trying to scheduler more than 50 RDS instances in the same region
- Fixed bug that would sometimes cause the CFN schedule custom resource to error when many schedules were deployed in parallel
- Fixed bug that would cause spoke stacks to not be correctly deregistered from the hub stack when undeployed
- Fixed bug in cli describe_schedule_usage command that would incorrectly estimate the behavior of schedules using nth weekday expressions
- Fixed bug that would cause schedules using monthday ranges of the format "n-31" to fail to load in months
  with less days then the end of the range (such as February)
- Fixed configured_in_stack property not being correctly applied to periods deployed by CloudFormation custom resource.

### Security

- Break monolith Lambda Function and permissions apart based on principle of least privilege
- Spoke stack trust permissions restricted to only specific lambda roles in the Hub account
- Allow KMS keys for scheduling encrypted EBS volumes to be specified directly on hub/spoke stacks in cloudformation
  rather needing to be added to scheduling roles manually
- Upgrade Requests to mitigate CVE-2024-35195

## [1.5.6] - 2024-05-10

### Security

- Upgrade werkzeug to mitigate CVE-2024-34069
- Upgrade jinja2 to mitigate CVE-2024-34064

## [1.5.5] - 2024-04-12

### Security

- Upgrade Black to mitigate CVE-2024-21503
- Upgrade idna to mitigate CVE-2024-3651

## [1.5.4] - 2024-04-01

### Security

- Upgrade cryptography to mitigate CVE-2024-26130, CVE-2023-50782, CVE-2024-0727, CVE-2023-49083
- Upgrade Jinja to mitigate CVE-2024-22195
- Upgrade Werkzeug to mitigate CVE-2023-46136
- Upgrade IP to mitigate CVE-2023-42282
- Remove ecdsa to mitigate CVE-2024-23342

## [1.5.3] - 2023-10-22

### Security

- Upgrade @babel/traverse to mitigate CVE-2023-45133
- Upgrade urllib3 to mitigate CVE-2023-45803

## [1.5.2] - 2023-10-09

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
