#!/usr/bin/env node
// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { App, Aspects, DefaultStackSynthesizer, StackSynthesizer } from "aws-cdk-lib";
import { AwsSolutionsChecks, NagSuppressions } from "cdk-nag";
import { getSolutionContext } from "./instance-scheduler/lib/cdk-context";
import { InstanceSchedulerStack } from "./instance-scheduler/lib/instance-scheduler-stack";
import { InstanceSchedulerRemoteStack } from "./instance-scheduler/lib/remote-stack";
import { SourceProvider, TestingPipelineStack } from "./pipeline/lib/testing-pipeline-stack";
import { E2eTestStack } from "./pipeline/lib/e2e-test-stack";
import { PipelineBootstrapStack } from "./pipeline/lib/pipeline-bootstrap-stack";
import { buildCodeCommitSource } from "./pipeline/lib/code-commit-source";
import { buildCodeStarSource } from "./pipeline/lib/code-star-source";

interface AppProps {
  solutionVersion: string;
  synthesizer: StackSynthesizer;
}

function addAppStacks(app: App, props: AppProps): void {
  const solutionDetails = getSolutionContext(app);

  const hubStack = new InstanceSchedulerStack(app, "instance-scheduler-on-aws", {
    synthesizer: props.synthesizer,
    description: `(${solutionDetails.solutionId}) ${solutionDetails.solutionName} ${props.solutionVersion}`,
    solutionId: solutionDetails.solutionId,
    solutionName: solutionDetails.solutionName,
    solutionVersion: props.solutionVersion,
    appregApplicationName: solutionDetails.appRegAppName,
    appregSolutionName: solutionDetails.appRegSolutionName,
  });

  new InstanceSchedulerRemoteStack(app, "instance-scheduler-on-aws-remote", {
    synthesizer: props.synthesizer,
    description: `(${solutionDetails.solutionId}S) ${solutionDetails.solutionName} remote ${props.solutionVersion}`,
    solutionId: solutionDetails.solutionId,
    solutionName: solutionDetails.solutionName,
    solutionVersion: props.solutionVersion,
    appregApplicationName: solutionDetails.appRegAppName,
    appregSolutionName: solutionDetails.appRegSolutionName,
  });

  NagSuppressions.addResourceSuppressionsByPath(
    hubStack,
    "/instance-scheduler-on-aws/SchedulerRole/DefaultPolicy/Resource",
    [
      {
        id: "AwsSolutions-IAM5",
        reason: "The scheduling lambda must access multiple resources across services",
      },
    ],
  );
}

function getSourceProvider(sourceType: string): SourceProvider {
  switch (sourceType) {
    case "codecommit":
      return { getSource: buildCodeCommitSource };
    case "codestar":
      return { getSource: buildCodeStarSource };
    default:
      throw Error("Unknown source type");
  }
}

function addPipelineStacks(app: App): void {
  new PipelineBootstrapStack(app, "instance-scheduler-on-aws-testing-pipeline-bootstrap");
  const sourceType = app.node.tryGetContext("instance-scheduler-on-aws-pipeline-source") ?? "codecommit";
  new TestingPipelineStack(app, "instance-scheduler-on-aws-testing-pipeline", getSourceProvider(sourceType));

  /*
  E2eTestStack does not actually need to be built here to work in the pipeline,
  but building it here ensures it gets covered by CDK-Nag
   */
  new E2eTestStack(app, "instance-scheduler-on-aws-end-to-end-testing-resources");
}

function main(): void {
  const packageVersion =
    process.env.npm_package_version ??
    (() => {
      throw new Error("npm package version not available, invoke synth from npm");
    })();
  let solutionVersion = `v${packageVersion}`;
  let synthesizer = new DefaultStackSynthesizer();

  const { DIST_OUTPUT_BUCKET, SOLUTION_NAME, VERSION } = process.env;
  const solutionsPipelineOverrides = DIST_OUTPUT_BUCKET && SOLUTION_NAME && VERSION;

  if (solutionsPipelineOverrides) {
    solutionVersion = VERSION;
    synthesizer = new DefaultStackSynthesizer({
      generateBootstrapVersionRule: false,
      fileAssetsBucketName: `${DIST_OUTPUT_BUCKET}-\${AWS::Region}`,
      bucketPrefix: `${SOLUTION_NAME}/${VERSION}/`,
    });
  }

  const app = new App();
  Aspects.of(app).add(new AwsSolutionsChecks({ verbose: true }));

  addAppStacks(app, { solutionVersion, synthesizer });
  addPipelineStacks(app);
}

main();
