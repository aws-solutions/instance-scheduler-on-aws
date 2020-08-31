# AWS Instance Scheduler (ID SO0030)

Scheduler for Cross-Account and Cross-Region scheduling for EC2 and RDS instances

## Getting Started

To get started with the AWS Instance Scheduler, please review the solution documentation. [AWS Instance Scheduler](https://aws.amazon.com/solutions/implementations/instance-scheduler/?did=sl_card&trk=sl_card)

## Building from GitHub
***

### Overview of the process

Building from GitHub source will allow you to modify the solution. The process consists of downloading the source from GitHub, creating buckets to be used for deployment, building the solution, and uploading the artifacts needed for deployment.

#### You will need:

* a Linux client with the AWS CLI v2 installed and python 3.7+, AWS CDK
* source code downloaded from GitHub
* two S3 buckets (minimum): 1 global and 1 for each region where you will deploy

### Download from GitHub

Clone or download the repository to a local directory on your linux client. Note: if you intend to modify Ops Automator you may wish to create your own fork of the GitHub repo and work from that. This allows you to check in any changes you make to your private copy of the solution.

**Git Clone example:**

```
git clone https://github.com/awslabs/aws-instance-scheduler.git
```

**Download Zip example:**
```
wget https://github.com/awslabs/aws-instance-scheduler/archive/master.zip
```

#### Repository Organization

```
|- deployment/                - contains build scripts, deployment templates, and dist folders for staging assets.
  |- cdk-solution-helper/     - helper function for converting CDK output to a format compatible with the AWS Solutions pipelines.
  |- build-open-source-dist.sh  - builds the open source package with cleaned assets and builds a .zip file in the /open-source folder for distribution to GitHub
  |- build-s3-dist.sh         - builds the solution and copies artifacts to the appropriate /global-s3-assets or /regional-s3-assets folders.
  |- run-unit-tests.sh         - runs the unit tests for the lambda files.
|- source/                    - all source code, scripts, tests, etc.
  |- bin/
    |- aws-instance-scheduler.ts - the AWS Instance scheduler cdk app.
  |- lambda/                  - Lambda function with source code and test cases.        
  |- lib/
    |- aws-instance-scheduler-stack.ts  - the main CDK stack for aws instance scheduler solution.
    |- aws-instance-scheduler-remote-stack.ts  - the main CDK stack for aws instance scheduler solution remote template.
  |- test/
    |- __snapshots__/
    |- aws-instance-scheduler-remote-stack.test.ts   - unit and snapshot tests for aws instance scheduler.
    |- aws-instance-scheduler-stack.test.ts   - unit and snapshot tests for aws instance scheduler.
  |- cdk.json                 - config file for CDK.
  |- jest.config.js           - config file for unit tests.
  |- package.json             - package file for the aws instance scheduler CDK project.
  |- README.md                - doc file for the CDK project.
  |- run-all-tests.sh         - runs all tests within the /source folder. Referenced in the buildspec and build scripts.
|- .gitignore
|- .viperlightignore          - Viperlight scan ignore configuration  (accepts file, path, or line item).
|- .viperlightrc              - Viperlight scan configuration.
|- buildspec.yml              - main build specification for CodeBuild to perform builds and execute unit tests.
|- CHANGELOG.md               - required for every solution to include changes based on version to auto-build release notes.
|- CODE_OF_CONDUCT.md         - standardized open source file for all solutions.
|- CONTRIBUTING.md            - standardized open source file for all solutions.
|- LICENSE.txt                - required open source file for all solutions - should contain the Apache 2.0 license.
|- NOTICE.txt                 - required open source file for all solutions - should contain references to all 3rd party libraries.
|- README.md                  - required file for all solutions.

```

### Build

AWS Solutions use two buckets: a bucket for global access to templates, which is accessed via HTTPS, and regional buckets for access to assets within the region, such as Lambda code. You will need:

* One global bucket that is access via the http end point. AWS CloudFormation templates are stored here. Ex. "mybucket"
* One regional bucket for each region where you plan to deploy using the name of the global bucket as the root, and suffixed with the region name. Ex. "mybucket-us-east-1"
* Your buckets should be encrypted and disallow public access

**Build the solution**

From the *deployment* folder in your cloned repo, run build-s3-dist.sh, passing the root name of your bucket (ex. mybucket) and the version you are building (ex. v1.0.0). We recommend using a semver version based on the version downloaded from GitHub (ex. GitHub: v1.0.0, your build: v1.0.0.mybuild)

```
chmod +x build-s3-dist.sh
build-s3-dist.sh <bucketname> <version>
```

**Run Unit Tests**

```
cd ./deployment
chmod +x ./run-unit-tests.sh
./run-unit-tests.sh
```

Confirm that all unit tests pass.

**Upload to your buckets**

Upload the template and the lambda to your bucket in the following pattern,
```
s3://mybucket/aws-instance-scheduler/v1.3.3/instance-scheduler.zip (lambda Code)
```

Templates
```
s3://mybucket-us-east-1/aws-instance-scheduler/v1.3.3/AwsInstanceScheduler.template
s3://mybucket-us-east-1/aws-instance-scheduler/v1.3.3/AwsInstanceSchedulerRemote.template
```

## Deploy

See the (AWS Instance Scheduler Implementation Guide)[https://s3.amazonaws.com/solutions-reference/aws-instance-scheduler/latest/instance-scheduler.pdf] for deployment instructions, using the link to the AwsInstanceScheduler.template from your bucket, rather than the one for AWS Solutions. Ex. https://mybucket.s3.amazonaws.com/aws-instance-scheduler/v1.0.0.mybuild/AwsInstanceScheduler.template

## CDK Documentation

AWS Instance Scheduler templates are generated using AWS CDK, for further information on CDK please refer to the (documentation)[https://docs.aws.amazon.com/cdk/latest/guide/getting_started.html].


***

Copyright 2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.

Licensed under the Apache License Version 2.0 (the "License"). You may not use this file except in compliance with the License. A copy of the License is located at

    http://www.apache.org/licenses/

or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions and limitations under the License.
