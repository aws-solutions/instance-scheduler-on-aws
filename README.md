# Instance Scheduler on AWS (ID SO0030)

Scheduler for Cross-Account and Cross-Region scheduling for EC2 and RDS instances

## Getting Started

To get started with Instance Scheduler, please review the solution documentation. 
[Instance Scheduler on AWS](https://aws.amazon.com/solutions/implementations/instance-scheduler-on-aws/)

## Building from GitHub
***

### Overview of the process

Building from GitHub source will allow you to modify the solution. The process consists of downloading the source from 
GitHub, creating buckets to be used for deployment, building the solution, and uploading the artifacts needed for deployment.

#### You will need:

* a Linux client with the AWS CLI v2 installed and python 3.7+, AWS CDK
* source code downloaded from GitHub
* two S3 buckets (minimum): 1 global and 1 for each region where you will deploy

### Download from GitHub

Clone the repository to a local directory on your linux client. Note: if you intend to 
modify Instance Scheduler you may wish to create your own fork of the GitHub repo and work from that. 
This allows you to check in any changes you make to your private copy of the solution.


## Repository Organization

```
|- deployment/                - contains build scripts, deployment templates, and dist folders for staging assets.
  |- build-s3-dist.sh         - builds the solution and copies artifacts to the appropriate /global-s3-assets or /regional-s3-assets folders.
  |- run-unit-tests.sh        - runs the unit tests for the lambda files.
|- source/                    - all source code, scripts, tests, etc.
  |- app/                     - lambda source file
  |- cli/                     - scheduler-cli source files
  |- infrastructure/          - cdk source files
    |- pipeline               - automated testing pipeline source files
```

## Deploy the Solution From Github

AWS Solutions use two buckets: a bucket for global access to templates, which is accessed via HTTPS, and regional buckets for access to assets within the region, such as Lambda code. You will need:

* One global bucket that is access via the http end point. AWS CloudFormation templates are stored here. Ex. "mybucket"
* One regional bucket for each region where you plan to deploy using the name of the global bucket as the root, and suffixed with the region name. Ex. "mybucket-us-east-1"
* Your buckets should be encrypted and disallow public access

**Build the solution**

From the *deployment* folder in your cloned repo, run build-s3-dist.sh, passing the root name of 
your bucket(ex. mybucket), name of the solution i.e. aws-instance-scheduler 
and the version you are building (ex. v1.5.0). 
We recommend using a similar version based on the version downloaded from GitHub 
(ex. GitHub: v1.5.0, your build: v1.5.0.mybuild)

```
chmod +x build-s3-dist.sh
build-s3-dist.sh <bucketname> aws-instance-scheduler <version>
```



**Upload to your buckets**

Upload the template and the lambda to your bucket in the following pattern,
```
s3://mybucket-us-east-1/aws-instance-scheduler/v1.5.0/instance-scheduler.zip (lambda Code)
```

Templates
```
s3://mybucket/aws-instance-scheduler/v1.5.0/instance-scheduler.template
s3://mybucket/aws-instance-scheduler/v1.5.0/instance-scheduler-remote.template
```

### Deploy

See the [AWS Instance Scheduler Implementation Guide](https://s3.amazonaws.com/solutions-reference/aws-instance-scheduler/latest/instance-scheduler.pdf) for deployment instructions, using the link to the instance-scheduler.template from your bucket, rather than the one for AWS Solutions. Ex. https://mybucket.s3.amazonaws.com/aws-instance-scheduler/v1.4.0.mybuild/instance-scheduler.template


# Testing the Solution

## Running Tests Locally
To test the solution you will need to install tox

```
pip install tox
```

Then from the root directory of the solution
```
//run all unit tests
tox

//test just the lambda code
tox -e lambda

//test just the cdk code
tox -e cdk
```

## Automated Testing Pipeline

#### _Prerequisites - You must have an AWS account and a fork of this repo_

Instance Scheduler on AWS includes an optional automated testing pipeline that can be deployed to automatically test any changes you
develop for the solution on your own development fork. Once setup, this pipeline will automatically download, 
build, and test any changes that you push to a specified branch on your development fork.



### Step 1 - Connect CodeStar to Your Github Account

For the pipeline to be able to test your changes, you must provide permission for CodeStar to 
access your development repo

https://docs.aws.amazon.com/dtconsole/latest/userguide/connections-create-github.html

_note: codestar only needs access to your Instance Scheduler development fork, it does not need access to all repositories_

Once the connection has been setup, make sure you save the connection ARN for the next step

### Step 2 -  Setup Pipeline Parameters
Go to [Systems Manager Parameter Store](https://us-east-1.console.aws.amazon.com/systems-manager/parameters) 
and configure the following string parameters

- /InstanceScheduler-build/connection/arn    -- the CodeStar connection ARN from the previous step
- /InstanceScheduler-build/connection/owner  -- the github owner of your fork
- /InstanceScheduler-build/connection/repo   -- the repo name of your fork
- /InstanceScheduler-build/connection/branch -- The branch in your fork that you want to test

For example, if your github username is "myUser" and you would like to test changes pushed to the develop branch of your fork
the values you would need to set would be:
```
arn = {arn from Step 1}
owner = myUser
repo = aws-instance-scheduler
branch = develop
```

### Step 3 - Deploy the Testing Pipeline

```
cd source/infrastructure
npm install
cd pipeline
cdk bootstrap
cdk deploy aws-instance-scheduler-testing-pipeline
```
This will deploy the automated testing pipeline into your AWS account which will then begin running tests against your
development fork automatically

To view the results. Go to [CodePipeline](https://us-east-1.console.aws.amazon.com/codesuite/codepipeline/pipelines) and
click on the pipeline that begins with aws-instance-scheduler-testing-pipeline

# CDK Documentation

AWS Instance Scheduler templates are generated using AWS CDK, for further information on CDK please refer to the [documentation](https://docs.aws.amazon.com/cdk/latest/guide/getting_started.html)


***

Copyright 2021 Amazon.com, Inc. or its affiliates. All Rights Reserved.

Licensed under the Apache License Version 2.0 (the "License"). You may not use this file except in compliance with the License. A copy of the License is located at

    http://www.apache.org/licenses/

or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions and limitations under the License.
