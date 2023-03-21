// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import * as codebuild from "aws-cdk-lib/aws-codebuild";
import * as pipeslines from "aws-cdk-lib/pipelines"
import CodeStarSource from "./code-star-source";
import {Construct} from "constructs";
import {Stack, Stage} from "aws-cdk-lib";
import {StringParameter} from "aws-cdk-lib/aws-ssm";
import {AwsInstanceSchedulerStack} from "../../instance-scheduler/lib/aws-instance-scheduler-stack";
import {NagSuppressions} from "cdk-nag";
import {E2eTestStack} from "./e2e-test-stack";
import {Effect, PolicyStatement} from "aws-cdk-lib/aws-iam";
import * as hubStackUtils from "../e2e-tests/utils/hub-stack-utils";

const DEPLOY_STAGE_NAME = "Deployment-Test";
const END_TO_END_STAGE_NAME = "End-to-End-Tests"
const STACK_NAME = "InstanceScheduler";
const TEST_RESOURCES_STACK_NAME = "InstanceSchedulerE2ETestResources";

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

    const pipeline = new pipeslines.CodePipeline(this, "Pipeline", {
      synth: this.getSynthStep(),
      codeBuildDefaults: {
        buildEnvironment: {
          buildImage: codebuild.LinuxBuildImage.STANDARD_6_0,
          computeType: codebuild.ComputeType.LARGE,
          privileged: true
        },
      },
    });

    const deployStage = new DeployStage(this, DEPLOY_STAGE_NAME)
    pipeline.addStage(deployStage, {
      pre: [
        this.getUnitTestStep()
      ]

    });

    const e2eTestStage = new EndToEndTestStage(this, END_TO_END_STAGE_NAME)
    pipeline.addStage(e2eTestStage, {
      post: [
        this.getEndToEndTestStep(deployStage.instanceSchedulerStack, e2eTestStage.e2eTestResourcesStack)
      ]
    })



    //pipeline must be built before findings can be suppressed
    pipeline.buildPipeline();
    NagSuppressions.addStackSuppressions(this, [
      {
        id: "AwsSolutions-IAM5",
        reason: "necessary permissions for the pipeline to build, update, and self-mutate"
      },
      {
        id: "AwsSolutions-CB4",
        reason: "Update step provided by construct"
      }
    ]);

    NagSuppressions.addResourceSuppressions(pipeline.pipeline.artifactBucket, [
      {
        id: "AwsSolutions-S1",
        reason: "Bucket is used internally by the pipeline and does not need access logging"
      }
    ]);
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
    return new pipeslines.CodeBuildStep("Synth", {
      input: this.get_connection(),
      installCommands: [
        'pip install tox',
      ],
      commands: [
        'cd source/infrastructure',
        'npm ci',
        'cd pipeline',
        'npx cdk synth',
      ],
      primaryOutputDirectory: 'build/cdk.pipeline.out'
    });
  }

  getUnitTestStep() {
    return new pipeslines.CodeBuildStep("unitTests", {

      installCommands: ["pip install tox"],
      commands: [
        'tox -e cdk',
        'tox -e lambda -- --junitxml=deployment/test-reports/lambda-test-report.xml'
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
      rolePolicyStatements: [],
    });
  }

  getEndToEndTestStep(mainInstanceSchedulerStack: AwsInstanceSchedulerStack, testingResourcesStack: E2eTestStack) {


    return new pipeslines.CodeBuildStep("EndToEndTests", {
      installCommands: ["pip install tox"],
      commands: [
        'tox -e e2e',
      ],
      envFromCfnOutputs: {
        ...testingResourcesStack.outputs,
        ...hubStackUtils.extractOutputsFrom(mainInstanceSchedulerStack)
      },
      partialBuildSpec: codebuild.BuildSpec.fromObject({
        reports: {
          e2e_test_reports: {
            files: ["e2e-test-report.xml"],
            "file-format": "JUNITXML",
            "base-directory": "deployment/test-reports"
          }
        },
      }),
      rolePolicyStatements: [
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['*'],
          resources: ['*']
        })
      ],
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
    solutionId: "",
    solutionName: "",
    solutionVersion: "",
    paramOverrides: {
      schedulerFrequency: "1",
      scheduledServices: "Both",
    }
  });
}

class EndToEndTestStage extends Stage {
  constructor(scope: Construct, construct_id: string) {
    super(scope, construct_id);
  }

  e2eTestResourcesStack = new E2eTestStack(this, TEST_RESOURCES_STACK_NAME)
}

export default PipelineStack;
