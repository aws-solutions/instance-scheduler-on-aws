// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import * as codebuild from "aws-cdk-lib/aws-codebuild";
import * as pipelines from "aws-cdk-lib/pipelines";
import { Construct } from "constructs";
import { Stack, Stage } from "aws-cdk-lib";
import { InstanceSchedulerStack } from "../../instance-scheduler/lib/instance-scheduler-stack";
import { NagSuppressions } from "cdk-nag";
import { E2eTestStack } from "./e2e-test-stack";
import { Effect, PolicyStatement } from "aws-cdk-lib/aws-iam";
import * as hubStackUtils from "../e2e-tests/utils/hub-stack-utils";

const DEPLOY_STAGE_NAME = "Deployment-Test";
const END_TO_END_STAGE_NAME = "End-to-End-Tests";
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

    const pipeline = new pipelines.CodePipeline(this, "Pipeline", {
      synth: this.synthStep(sourceProvider.getSource(this)),
      codeBuildDefaults: {
        buildEnvironment: {
          buildImage: codebuild.LinuxBuildImage.STANDARD_6_0,
          computeType: codebuild.ComputeType.LARGE,
          privileged: true,
        },
      },
    });

    const deployStage = new DeployStage(this, DEPLOY_STAGE_NAME);
    pipeline.addStage(deployStage, {
      pre: [this.unitTestStep()],
    });

    const e2eTestStage = new EndToEndTestStage(this, END_TO_END_STAGE_NAME);
    pipeline.addStage(e2eTestStage, {
      post: [this.endToEndTestStep(deployStage.instanceSchedulerStack, e2eTestStage.e2eTestResourcesStack)],
    });

    //pipeline must be built before findings can be suppressed
    pipeline.buildPipeline();
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

    NagSuppressions.addResourceSuppressions(pipeline.pipeline.artifactBucket, [
      {
        id: "AwsSolutions-S1",
        reason: "Bucket is used internally by the pipeline and does not need access logging",
      },
    ]);
  }

  synthStep(source: pipelines.IFileSetProducer) {
    return new pipelines.CodeBuildStep("Synth", {
      input: source,
      installCommands: ["npm install --location=global npm@^9", "npm ci"],
      commands: ["npm run synth"],
      primaryOutputDirectory: "build/cdk.out",
    });
  }

  unitTestStep() {
    return new pipelines.CodeBuildStep("unitTests", {
      installCommands: [
        "npm install --location=global npm@^9",
        "pyenv install -s 3.8 3.9 3.11",
        "pyenv global 3.11 3.9 3.8",
        "python -m pip install -U pip setuptools tox",
        "npm ci",
      ],
      commands: ["npm run test:ci"],
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
      rolePolicyStatements: [],
    });
  }

  endToEndTestStep(mainInstanceSchedulerStack: InstanceSchedulerStack, testingResourcesStack: E2eTestStack) {
    return new pipelines.CodeBuildStep("EndToEndTests", {
      installCommands: ["npm install --location=global npm@^9", "npm ci"],
      commands: ["npm run e2e-tests"],
      envFromCfnOutputs: {
        ...testingResourcesStack.outputs,
        ...hubStackUtils.extractOutputsFrom(mainInstanceSchedulerStack),
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
  constructor(scope: Construct, construct_id: string) {
    super(scope, construct_id);
  }

  instanceSchedulerStack = new InstanceSchedulerStack(this, STACK_NAME, {
    appregApplicationName: "AWS-Solutions",
    appregSolutionName: "instance-scheduler-on-aws",
    description: "test deployment from the InstanceScheduler e2e pipeline",
    solutionId: "SO0030",
    solutionName: "instance-scheduler-on-aws",
    solutionVersion: "pipeline",
    paramOverrides: {
      schedulerFrequency: "1",
      scheduledServices: "Both",
      namespace: "e2etesting",
      enableSSMMaintenanceWindows: "Yes",
      trace: "Yes",
    },
    disableOpMetrics: true,
  });
}

class EndToEndTestStage extends Stage {
  constructor(scope: Construct, construct_id: string) {
    super(scope, construct_id);
  }

  e2eTestResourcesStack = new E2eTestStack(this, TEST_RESOURCES_STACK_NAME);
}
