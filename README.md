# Instance Scheduler on AWS

The Instance Scheduler on AWS solution automates the starting and stopping of Amazon Elastic Compute Cloud (Amazon EC2)
and Amazon Relational Database Service (Amazon RDS) instances.

This solution helps reduce operational costs by stopping resources that are not in use and starting them when they are
needed. The cost savings can be significant if you leave all of your instances running at full utilization continuously.

## Getting Started

To understand how to use Instance Scheduler on AWS, please review the [implementation
guide](https://docs.aws.amazon.com/solutions/latest/instance-scheduler-on-aws/solution-overview.html) on the [solution
landing page](https://aws.amazon.com/solutions/implementations/instance-scheduler-on-aws/). To deploy the solution, see
[Deploying the Solution](#deploying-the-solution).

## Repository Organization

```
|- .github/                       - GitHub issue and pull request templates
|- .projen/                       - projen-generated project metadata
|- deployment/                    - build scripts
|- projenrc/                      - projen source code
|- source/                        - project source code
  |- app/                         - AWS Lambda Function source code
  |- cli/                         - Instance Scheduler CLI source code
  |- instance-scheduler/          - CDK source code
  |- pipeline/                    - automated testing pipeline source code
```

## Deploying the Solution

### One-Click Deploy From Amazon Web Services

Refer to the [solution landing page](https://aws.amazon.com/solutions/implementations/instance-scheduler-on-aws/) to
deploy Instance Scheduler on AWS using our pre-packaged deployment assets.

### Deploy from source code using CDK

Instance Scheduler can be deployed to your AWS account directly from the source code using AWS Cloud Development Kit
(CDK).

#### Prerequisites

- cloned repository
- AWS CLI v2
- Node.JS 18
- docker

#### Deploying the hub stack

```
npm install
npx cdk bootstrap
npx cdk deploy instance-scheduler-on-aws
```

This will deploy the solution into your aws account using all default configuration settings. You will then need to
update those settings to their desired values from the CloudFormation console by selecting the deployed template and
clicking "Update" -> "Use Current Template".

Refer to the [Implementation
Guide](https://docs.aws.amazon.com/solutions/latest/instance-scheduler-on-aws/deployment.html#step1) for guidance on
what each of the configuration parameters is for.

#### Deploying Remote Stacks in Other Accounts

To deploy the remote stack for cross-account scheduling, you will first need to have deployed the primary control stack.
Then update your aws credentials to match those of the remote account you would like to schedule and deploy the remote
stack.

```
npx cdk bootstrap
npx cdk deploy instance-scheduler-on-aws-remote --parameters InstanceSchedulerAccount={account-id} --parameters namespace={namespace} --parameters UsingAWSOrganizations={useOrgs}
```

Replace:

- {account-id} with the id of the account that contains the primary control stack.
- {namespace} with the same unique namespace that was provided to the primary control stack
- {useOrgs} with the same value set in the primary control stack (Yes/No)

For example: `InstanceSchedulerAccount=111222333444`

### Deploy from GitHub (AWS Console)

This method mimics the procedure used by AWS One-Click Deploy allowing you to deploy the solution from the AWS console
using assets that you can control and update.

#### Overview

AWS Solutions use two buckets: a bucket for global access to templates, which is accessed via HTTPS, and regional
buckets for access to assets within the region, such as Lambda code. You will need:

- One global bucket that is accessed via the https end point. AWS CloudFormation templates are stored here. Ex.
  "mybucket"
- One regional bucket for each region where you plan to deploy using the name of the global bucket as the root, and
  suffixed with the region name. Ex. "mybucket-us-east-1"
- Your buckets should be encrypted and disallow public access.

#### You will need:

- cloned repository
- AWS CLI v2
- Node.js 18
- docker
- Two S3 buckets (minimum): 1 global and 1 for each region where you will deploy.

#### Step 1 - Download from GitHub

Clone the repository to a local directory on your linux client. Note: If you intend to modify Instance Scheduler you may
wish to create your own fork of the GitHub repo and work from that. This allows you to check in any changes you make to
your private copy of the solution.

#### Step 2 - Build the solution

From the _deployment_ folder in your cloned repo, run build-s3-dist.sh, passing the root name of your bucket(ex.
mybucket), name of the solution (i.e. instance-scheduler-on-aws) and the version you are building (ex. v1.5.0). We
recommend using a similar version based on the version downloaded from GitHub (ex. GitHub: v1.5.0, your build:
v1.5.0.mybuild).

```
cd deployment
./build-s3-dist.sh <bucketname> instance-scheduler-on-aws <version>
```

#### Step 3 - Upload to your buckets

The previous step will have generated several folders in your local directory including:

```
deployment/global-s3-assets
deployment/regional-s3-assets
```

Upload the contents of `deployment/global-s3-assets` to your global bucket and `deployment/regional-s3-assets` to your
regional buckets following the pattern `s3://<bucket-name>/<solution-name>/<version>/<asset>`.

For example:

```
//global assets
s3://mybucket/instance-scheduler-on-aws/v1.5.0/instance-scheduler.template
s3://mybucket/instance-scheduler-on-aws/v1.5.0/instance-scheduler-remote.template

//regional assets
s3://mybucket-us-east-1/instance-scheduler-on-aws/v1.5.0/f779f5b7643ba70e9a5e25c8898f4e4e8e54ca15b150eee1dd25c2c636b188b8.zip
s3://mybucket-us-west-1/instance-scheduler-on-aws/v1.5.0/f779f5b7643ba70e9a5e25c8898f4e4e8e54ca15b150eee1dd25c2c636b188b8.zip
```

_Note: The scheduler-cli is optional and does not need to be published to the global bucket for deploy to work._

#### Step 4 - Deploy The Solution

Refer to the [Implementation
Guide](https://docs.aws.amazon.com/solutions/latest/instance-scheduler-on-aws/deployment.html) for deployment
instructions, using the link to the instance-scheduler.template from your bucket, rather than the one for AWS Solutions.
Ex. https://mybucket.s3.amazonaws.com/instance-scheduler-on-aws/v1.5.0.mybuild/instance-scheduler.template

## Testing the Solution

### Prerequisites

- cloned repository
- AWS CLI v2
- Node.js 18
- docker
- Python 3.10
- tox

### Running Tests Locally

```
npm install
npm run test
```

### Automated Testing Pipeline

Instance Scheduler on AWS includes an optional automated testing pipeline that can be deployed to automatically test any
changes you develop for the solution on your own development fork. Once setup, this pipeline will automatically
download, build, and test any changes that you push to a specified branch on your development fork.

The pipeline can be configured to automatically watch and pull from repos hosted on either [AWS
CodeCommit](https://aws.amazon.com/codecommit/) or GitHub.

#### Prerequisites

- AWS account
- repository fork
- AWS CLI v2
- Node.js 18
- docker

#### Step 0 (If Using GitHub) - Connect CodeStar to Your GitHub Account

For the pipeline to be able to test your changes, you must provide permission to access your development repo.

https://docs.aws.amazon.com/dtconsole/latest/userguide/connections-create-github.html

_Note: CodeStar only needs access to your Instance Scheduler development fork, it does not need access to all
repositories._

Once the connection has been set up, make sure you save the connection ARN for the next step.

#### Step 1 - Prepare Your Environment

In your local environment, first install all necessary dependencies and bootstrap your account for CDK deployment.

```
npm install
npx cdk bootstrap
```

#### Step 2 - Deploy the testing pipeline bootstrap stack

```
npx cdk deploy instance-scheduler-on-aws-testing-pipeline-bootstrap
```

Once the stack is deployed, Go to CloudFormation and [update the bootstrap
stack](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-direct.html) with the
configuration your pipeline should use

At a minimum you must provide:

- repoName -- the name of your forked repo (either in CodeCommit or GitHub)
- repoBranch -- The branch in your fork that should be watched and pulled from for testing

if sourcing from GitHub instead of CodeCommit, you must also provide:

- codestarArn -- the CodeStar connection ARN from the previous step
- repoArn -- the GitHub owner of your fork

For example, if your GitHub username is "myUser" and you would like to test changes pushed to the develop branch of your
fork the values you would need to set would be:

```
arn = {arn from Step 0}
owner = myUser
repo = instance-scheduler-on-aws
branch = develop
```

#### Step 3 - Deploy the Testing Pipeline

```
# source from CodeCommit
npx cdk deploy instance-scheduler-on-aws-testing-pipeline --context instance-scheduler-on-aws-pipeline-source=codecommit

# source from GitHub
npx cdk deploy instance-scheduler-on-aws-testing-pipeline --context instance-scheduler-on-aws-pipeline-source=codestar
```

_note: If you do not provide a context, the pipeline will default to using codecommit._

This will deploy the automated testing pipeline into your AWS account which will then begin running tests against your
development fork automatically.

To view the results. Go to [CodePipeline](https://us-east-1.console.aws.amazon.com/codesuite/codepipeline/pipelines) and
click on the pipeline that begins with instance-scheduler-on-aws-testing-pipeline.

## Modifying the Solution

### projen

This solution uses [projen](https://projen.io/) to manage certain project files. If you need to modify any of these
files, modify the source in [.projenrc.ts](./.projenrc.ts) and run `projen` to regenerate the files.

## CDK Documentation

Instance Scheduler on AWS templates are generated using AWS CDK, for further information on CDK please refer to the
[documentation](https://docs.aws.amazon.com/cdk/latest/guide/getting_started.html).


## Collection of Operational Metrics
This solution collects anonymous operational metrics to help AWS improve the quality and features of the solution. For more information, including how to disable this capability, please see the [implementation guide](https://docs.aws.amazon.com/solutions/latest/instance-scheduler-on-aws/anonymized-data.html).

---

Copyright 2021 Amazon.com, Inc. or its affiliates. All Rights Reserved.

Licensed under the Apache License Version 2.0 (the "License"). You may not use this file except in compliance with the
License. A copy of the License is located at

    http://www.apache.org/licenses/

or in the "[LICENSE](./LICENSE)" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT
WARRANTIES OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing
permissions and limitations under the License.
