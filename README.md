# Instance Scheduler on AWS (ID SO0030)

Instance Scheduler on AWS automates the starting and stopping of Amazon Elastic Compute Cloud (Amazon EC2) and Amazon Relational Database Service (Amazon RDS) instances.

This solution helps reduce operational costs by stopping resources that are not in use and starting them when they are needed. The cost savings can be significant if you leave all of your instances running at full utilization continuously.

## Getting Started

To understand how to use Instance Scheduler on AWS, please review the [implementation guide](https://docs.aws.amazon.com/solutions/latest/instance-scheduler-on-aws/solution-overview.html)
on the [solution landing page](https://aws.amazon.com/solutions/implementations/instance-scheduler-on-aws/). 
To deploy the solution, see [Deploying the Solution](#deploying-the-solution)


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

## Deploying the Solution
***
### One-Click Deploy From Amazon Web Services
Refer to the [solution landing page](https://aws.amazon.com/solutions/implementations/instance-scheduler-on-aws/)
to deploy Instance Scheduler on AWS using our pre-packaged deployment assets.

### Deploy from GitHub (CDK Deploy)

Instance Scheduler can be deployed to your AWS account directly from the source code using `cdk deploy`.

#### Deploying the Primary Control Stack
```
cd source/infrastructure
npm install
cd instance-scheduler
cdk bootstrap
cdk deploy aws-instance-scheduler
```

This will deploy the solution into your aws account using all default configuration settings. 
You will then need to update those settings to their desired values from the CloudFormation console 
by selecting the deployed template and clicking "Update" -> "Use Current Template".

Refer to the [Implementation Guide](https://docs.aws.amazon.com/solutions/latest/instance-scheduler-on-aws/deployment.html#step1)
for guidance on what each of the configuration parameters is for.

#### Deploying Remote Stacks in Other Accounts
To deploy the remote stack for cross-account scheduling, you will first need to have deployed the primary
control stack. Then update your aws credentials to match those of the remote account you would like to schedule
and deploy the remote stack.
```
/source/infrastructure/aws-instance-scheduler

cdk bootstrap
cdk deploy aws-instance-scheduler-remote --parameters InstanceSchedulerAccount={account-id} --parameters namespace={namespace} --parameters UsingAWSOrganizations={useOrgs}
```
Replace:
- {account-id} with the id of the account that contains the primary control stack.
- {namespace} with the same unique namespace that was provided to the primary control stack
- {useOrgs} with the same value set in the primary control stack (yes/no)

For example: `InstanceSchedulerAccount=111222333444`


### Deploy from GitHub (AWS Console)
This method mimics the procedure used by AWS One-Click Deploy allowing you to deploy the solution
from the AWS console using assets that you can control and update. 

#### Overview
AWS Solutions use two buckets: a bucket for global access to templates, which is accessed via HTTPS, and regional buckets for access to assets within the region, such as Lambda code. You will need:

* One global bucket that is accessed via the https end point. AWS CloudFormation templates are stored here. Ex. "mybucket"
* One regional bucket for each region where you plan to deploy using the name of the global bucket as the root, and suffixed with the region name. Ex. "mybucket-us-east-1"
* Your buckets should be encrypted and disallow public access.

#### You will need:

* A Linux-compatible client with the AWS CLI v2, an accessible Docker daemon, and the latest versions of Python and NPM.
* A clone (or fork) of this repo.
* Two S3 buckets (minimum): 1 global and 1 for each region where you will deploy.

#### Step 1 - Download from GitHub

Clone the repository to a local directory on your linux client. Note: If you intend to 
modify Instance Scheduler you may wish to create your own fork of the GitHub repo and work from that. 
This allows you to check in any changes you make to your private copy of the solution.

#### Step 2 - Build the solution

From the *deployment* folder in your cloned repo, run build-s3-dist.sh, passing the root name of 
your bucket(ex. mybucket), name of the solution (i.e. aws-instance-scheduler) 
and the version you are building (ex. v1.5.0). 
We recommend using a similar version based on the version downloaded from GitHub 
(ex. GitHub: v1.5.0, your build: v1.5.0.mybuild).

```
cd deployment
chmod +x build-s3-dist.sh
build-s3-dist.sh <bucketname> aws-instance-scheduler <version>
```

#### Step 3 - Upload to your buckets

The previous step will have generated several folders in your local directory including:
```angular2html
deployment/global-s3-assets
deployment/regional-s3-assets
```

Upload the contents of `deployment/global-s3-assets` to your global bucket and `deployment/regional-s3-assets` 
to your regional buckets following the pattern
`s3://<bucket-name>/<solution-name>/<version>/<asset>`.

For example:
```
//global assets
s3://mybucket/aws-instance-scheduler/v1.5.0/instance-scheduler.template
s3://mybucket/aws-instance-scheduler/v1.5.0/instance-scheduler-remote.template

//regional assets
s3://mybucket-us-east-1/aws-instance-scheduler/v1.5.0/f779f5b7643ba70e9a5e25c8898f4e4e8e54ca15b150eee1dd25c2c636b188b8.zip
s3://mybucket-us-west-1/aws-instance-scheduler/v1.5.0/f779f5b7643ba70e9a5e25c8898f4e4e8e54ca15b150eee1dd25c2c636b188b8.zip
```

*Note: The scheduler-cli is optional and does not need to be published to the global bucket for deploy to work.*



#### Step 4 - Deploy The Solution

Refer to the [Implementation Guide](https://docs.aws.amazon.com/solutions/latest/instance-scheduler-on-aws/deployment.html) 
for deployment instructions, using the link to the instance-scheduler.template from your bucket, 
rather than the one for AWS Solutions. 
Ex. https://mybucket.s3.amazonaws.com/aws-instance-scheduler/v1.5.0.mybuild/instance-scheduler.template


## Testing the Solution
***

### Running Tests Locally
To test the solution you will need to install tox:

```
pip install tox
```

Then from the root directory of the solution,
```
//run all unit tests
tox

//test just the lambda code
tox -e lambda

//test just the cdk code
tox -e cdk

//test just the cli code
tox -e cli
```

### Automated Testing Pipeline

#### _Prerequisites - You must have an AWS account and a fork of this repo_

Instance Scheduler on AWS includes an optional automated testing pipeline that can be deployed to automatically test any changes you
develop for the solution on your own development fork. Once setup, this pipeline will automatically download, 
build, and test any changes that you push to a specified branch on your development fork.



#### Step 1 - Connect CodeStar to Your GitHub Account

For the pipeline to be able to test your changes, you must provide permission for CodeStar to 
access your development repo.

https://docs.aws.amazon.com/dtconsole/latest/userguide/connections-create-github.html

_Note: CodeStar only needs access to your Instance Scheduler development fork, it does not need access to all repositories._

Once the connection has been set up, make sure you save the connection ARN for the next step.

#### Step 2 -  Setup Pipeline Parameters
Go to [Systems Manager Parameter Store](https://us-east-1.console.aws.amazon.com/systems-manager/parameters) 
and configure the following string parameters:

- /InstanceScheduler-build/connection/arn    -- the CodeStar connection ARN from the previous step
- /InstanceScheduler-build/connection/owner  -- the GitHub owner of your fork
- /InstanceScheduler-build/connection/repo   -- the repo name of your fork
- /InstanceScheduler-build/connection/branch -- The branch in your fork that you want to test

For example, if your GitHub username is "myUser" and you would like to test changes pushed to the develop branch of your fork
the values you would need to set would be:
```
arn = {arn from Step 1}
owner = myUser
repo = aws-instance-scheduler
branch = develop
```

#### Step 3 - Deploy the Testing Pipeline

```
cd source/infrastructure
npm install
cd pipeline
cdk bootstrap
cdk deploy aws-instance-scheduler-testing-pipeline
```
This will deploy the automated testing pipeline into your AWS account which will then begin running tests against your
development fork automatically.

To view the results. Go to [CodePipeline](https://us-east-1.console.aws.amazon.com/codesuite/codepipeline/pipelines) and
click on the pipeline that begins with aws-instance-scheduler-testing-pipeline.

## CDK Documentation

AWS Instance Scheduler templates are generated using AWS CDK, for further information on CDK 
please refer to the [documentation](https://docs.aws.amazon.com/cdk/latest/guide/getting_started.html).


***

Copyright 2021 Amazon.com, Inc. or its affiliates. All Rights Reserved.

Licensed under the Apache License Version 2.0 (the "License"). You may not use this file except in compliance with the License. A copy of the License is located at

    http://www.apache.org/licenses/

or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions and limitations under the License.
