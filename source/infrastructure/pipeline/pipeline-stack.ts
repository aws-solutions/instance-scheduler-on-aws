// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import CodeStarSource from "./code-star-source";
import { Construct } from "constructs";
import { CodeBuildStep, CodePipeline } from "aws-cdk-lib/pipelines";
import { ComputeType, LinuxBuildImage } from "aws-cdk-lib/aws-codebuild";
import { Stack, Stage } from "aws-cdk-lib";
import { StringParameter } from "aws-cdk-lib/aws-ssm";
import * as codebuild from "aws-cdk-lib/aws-codebuild";
import { AwsInstanceSchedulerStack } from "../lib/aws-instance-scheduler-stack";

const DEPLOY_STAGE_NAME = "test-deploy";
const STACK_NAME = "InstanceScheduler";

class PipelineStack extends Stack {
  /*
    This stack establishes a pipeline that builds, deploys, and tests the solution
    in a specified account. It also uses CodeStar connections to set up a webhook
    to GitHub to trigger the pipeline when commits are pushed.

    The repo is configured using SSM parameters, specifically the following:
        - /InstanceScheduler-build/connection/owner
        - GitHub repo owner
        - /InstanceScheduler-build/connection/repo
        - GitHub repo name
        - /InstanceScheduler-build/connection/branch
        - GitHub repo branch
        - /InstanceScheduler-build/connection/arn
        - CodeStar Connection ARN

    Set up the connection by following the documentation at
    https://docs.aws.amazon.com/dtconsole/latest/userguide/connections-create-github.html
    */

  constructor(scope: Construct, construct_id: string) {
    super(scope, construct_id);

    const pipeline = new CodePipeline(this, "Pipeline", {
      synth: this.getSynthStep(),
      codeBuildDefaults: {
        buildEnvironment: {
          buildImage: LinuxBuildImage.STANDARD_6_0,
          computeType: ComputeType.LARGE,
        },
      },
    });

    const deployStage = new DeployStage(this, DEPLOY_STAGE_NAME);

    pipeline.addStage(deployStage, {
      post: [this.getIntegrationTestStep({})],
    });
  }

  get_connection() {
    return new CodeStarSource(
      "CodeStarConnection",
      StringParameter.valueForStringParameter(
        this,
        "/InstanceScheduler-build/connection/arn"
      ),
      StringParameter.valueForStringParameter(
        this,
        "/InstanceScheduler-build/connection/owner"
      ),
      StringParameter.valueForStringParameter(
        this,
        "/InstanceScheduler-build/connection/repo"
      ),
      StringParameter.valueForStringParameter(
        this,
        "/InstanceScheduler-build/connection/branch"
      )
    );
  }

  getSynthStep() {
    return new CodeBuildStep("Synth", {
      input: this.get_connection(),
      installCommands: [
        'pip install tox',
        'tox -e cdk',
        'tox -e lambda -- --junitxml=deployment/test-reports/lambda-test-report.xml'
      ],
      commands: [
        'cd source/infrastructure',
        "npx cdk synth",
        'cd ../../deployment',
      ],
      partialBuildSpec: codebuild.BuildSpec.fromObject({
        reports: {
          cdk_test_reports: {
            files: ["cdk-test-report.xml"],
            "file-format": "JUNITXML",
            "base-directory": "deployment/test-reports"
          },
          lambda_test_reports: {
            files: ["lambda-test-report.xml"],
            "file-format": "JUNITXML",
            "base-directory": "deployment/test-reports"
          }
        },
      }),
      primaryOutputDirectory: 'deployment/cdk.out'
    });
  }

  getIntegrationTestStep(outputs_map: {}) {
    return new CodeBuildStep("IntegrationTest", {
      installCommands: ["pip install tox"],
      commands: [
        "tox -e integration -- --junitxml=pytest-integration-report.xml",
      ],
      envFromCfnOutputs: outputs_map,
      rolePolicyStatements: [],
      partialBuildSpec: codebuild.BuildSpec.fromObject({
        reports: {
          integration_test_reports: {
            files: ["integration-test-report.xml"],
            "file-format": "JUNITXML",
            "base-directory": "deployment/test-reports"
          }
        },
      }),
    });
  }
}

class DeployStage extends Stage {
  constructor(scope: Construct, construct_id: string) {
    super(scope, construct_id);
  }

  instanceSchedulerStack = new AwsInstanceSchedulerStack(this, STACK_NAME, {
    description: "AWS Instance Scheduler Test Stack",
    solutionId: "SO0030",
    solutionTradeMarkName: "aws-instance-scheduler",
    solutionProvider: "AWS Solution Development",
    solutionBucket: "",
    solutionName: "aws-instance-scheduler",
    solutionVersion: "TEST",
    appregApplicationName: "",
    appregSolutionName: "",
  });
}

export default PipelineStack;
