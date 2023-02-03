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
        'tox -e cdk -- --ci --reporters=default --reporters=jest-junit',
      ],
      commands: [
        'cd source/infrastructure',
        "npx cdk synth"
      ],
      partialBuildSpec:
          this.get_reports_partial_build_spec("deployment/test-reports/cdk-test-report.xml"),
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
      partialBuildSpec: this.get_reports_partial_build_spec(
          "pytest-integration-report.xml"
      ),
    });
  }

  get_reports_partial_build_spec(filename: string) {
    return codebuild.BuildSpec.fromObject({
      reports: {
        pytest_reports: {
          files: [filename],
          "file-format": "JUNITXML",
        },
      },
    });
  }
}

class DeployStage extends Stage {
  constructor(scope: Construct, construct_id: string) {
    super(scope, construct_id);
  }

  instanceSchedulerStack = new AwsInstanceSchedulerStack(this, STACK_NAME, {
    appregApplicationName: "",
    appregSolutionName: "",
    description: "",
    solutionBucket: "",
    solutionId: "",
    solutionName: "",
    solutionProvider: "",
    solutionTradeMarkName: "",
    solutionVersion: "",
  });
}

export default PipelineStack;
