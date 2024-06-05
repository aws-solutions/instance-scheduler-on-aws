// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { Stack, Stage } from "aws-cdk-lib";
import * as codebuild from "aws-cdk-lib/aws-codebuild";
import { Effect, PolicyStatement } from "aws-cdk-lib/aws-iam";
import * as pipelines from "aws-cdk-lib/pipelines";
import { NagSuppressions } from "cdk-nag";
import { Construct } from "constructs";
import { E2eTestStack } from "./e2e-test-stack";
import { InstanceSchedulerTestingStack } from "./instance-scheduler-testing-stack";

const DEPLOY_STAGE_NAME = "Deployment-Test";
const STACK_NAME = "InstanceScheduler";
const TEST_RESOURCES_STACK_NAME = "InstanceSchedulerE2ETestResources";

export interface SourceProvider {
  getSource: (scope: Construct) => pipelines.IFileSetProducer;
}

export class TestingPipelineStack extends Stack {
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
  constructor(scope: Construct, construct_id: string, sourceProvider: SourceProvider) {
    super(scope, construct_id);

    const synth = this.synthStep(sourceProvider.getSource(this));
    const pipeline = new pipelines.CodePipeline(this, "Pipeline", {
      synth,
      codeBuildDefaults: {
        buildEnvironment: {
          buildImage: codebuild.LinuxBuildImage.STANDARD_7_0,
          computeType: codebuild.ComputeType.X_LARGE,
        },
      },
    });

    const deployStage = new DeployStage(this, DEPLOY_STAGE_NAME);
    pipeline.addStage(deployStage, {
      post: [this.endToEndTestStep(deployStage), this.fullTestStep()],
    });

    pipeline.buildPipeline();

    //pipeline must be built before findings can be suppressed
    NagSuppressions.addStackSuppressions(this, [
      {
        id: "AwsSolutions-IAM5",
        reason: "necessary permissions for the pipeline to build, update, and self-mutate",
      },
      {
        id: "AwsSolutions-CB4",
        reason: "Update step provided by construct",
      },
    ]);

    NagSuppressions.addResourceSuppressions(synth.project, [
      { id: "AwsSolutions-CB3", reason: "Privileged mode is required to build Lambda PythonFunctions with Docker" },
    ]);

    NagSuppressions.addResourceSuppressions(pipeline.pipeline.artifactBucket, [
      {
        id: "AwsSolutions-S1",
        reason: "Bucket is used internally by the pipeline and does not need access logging",
      },
    ]);
  }

  synthStep(source: pipelines.IFileSetProducer) {
    return new pipelines.CodeBuildStep("Synth", {
      buildEnvironment: { privileged: true },
      input: source,
      installCommands: [
        "pyenv global $PYTHON_311_VERSION",
        "python -m pip install -U pip setuptools poetry tox",
        "npm ci",
      ],
      commands: ["npm run test", "npm run synth"],
      primaryOutputDirectory: "build/cdk.out",
    });
  }

  fullTestStep() {
    return new pipelines.CodeBuildStep("FullTest", {
      buildEnvironment: { privileged: true },
      installCommands: [
        "n 20",
        "npm install --location=global npm@^10",
        "pyenv install -s 3.8 3.9 3.12",
        "pyenv global $PYTHON_311_VERSION 3.12 3.9 3.8",
        "python -m pip install -U pip setuptools poetry tox",
        "npm ci",
      ],
      commands: [
        "cd deployment",
        "./build-open-source-dist.sh",
        "cd ..",
        "npm run test:ci",
        "cd deployment",
        "./build-s3-dist.sh solutions instance-scheduler-on-aws v0.0.0",
      ],
      primaryOutputDirectory: "build/cdk.out",
      partialBuildSpec: codebuild.BuildSpec.fromObject({
        reports: {
          cdk_test_reports: {
            files: ["cdk-test-report.xml"],
            "file-format": "JUNITXML",
            "base-directory": "deployment/test-reports",
          },
          lambda_test_reports: {
            files: ["lambda-test-report.xml"],
            "file-format": "JUNITXML",
            "base-directory": "deployment/test-reports",
          },
          cli_test_reports: {
            files: ["cli-test-report.xml"],
            "file-format": "JUNITXML",
            "base-directory": "deployment/test-reports",
          },
        },
      }),
    });
  }

  endToEndTestStep(deployStage: DeployStage) {
    return new pipelines.CodeBuildStep("EndToEndTests", {
      installCommands: [
        "n 20",
        "npm install --location=global npm@^10",
        "npm ci",
        "pyenv global $PYTHON_311_VERSION",
        "python -m pip install -U pip setuptools poetry tox ./source/cli",
      ],
      commands: ["npm run e2e-tests"],
      env: {
        TEST_ASSETS_STACK: deployStage.e2eTestResourcesStack.stackName,
        HUB_STACK: deployStage.instanceSchedulerStack.stackName,
      },
      partialBuildSpec: codebuild.BuildSpec.fromObject({
        reports: {
          e2e_test_reports: {
            files: ["e2e-test-report.xml"],
            "file-format": "JUNITXML",
            "base-directory": "deployment/test-reports",
          },
        },
      }),
      rolePolicyStatements: [
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ["*"],
          resources: ["*"],
        }),
      ],
    });
  }
}

class DeployStage extends Stage {
  readonly instanceSchedulerStack = new InstanceSchedulerTestingStack(this, STACK_NAME, {
    appregApplicationName: "AWS-Solutions",
    appregSolutionName: "instance-scheduler-on-aws",
    description: "test deployment from the InstanceScheduler e2e pipeline",
    solutionId: "SO0030",
    solutionName: "instance-scheduler-on-aws",
    solutionVersion: "pipeline",
  });

  readonly e2eTestResourcesStack = new E2eTestStack(this, TEST_RESOURCES_STACK_NAME);
}
