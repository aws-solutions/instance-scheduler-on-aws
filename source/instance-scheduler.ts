#!/usr/bin/env node
// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { App, Aspects, DefaultStackSynthesizer, StackSynthesizer } from "aws-cdk-lib";
import { AwsSolutionsChecks } from "cdk-nag";
import { getSolutionContext } from "./instance-scheduler/lib/cdk-context";
import { InstanceSchedulerStack } from "./instance-scheduler/lib/instance-scheduler-stack";
import { SpokeStack } from "./instance-scheduler/lib/remote-stack";
interface AppProps {
  solutionVersion: string;
  synthesizer: StackSynthesizer;
}

function addAppStacks(app: App, props: AppProps): void {
  const solutionDetails = getSolutionContext(app);

  new InstanceSchedulerStack(app, "instance-scheduler-on-aws", {
    synthesizer: props.synthesizer,
    description: `(${solutionDetails.solutionId}) ${solutionDetails.solutionName} ${props.solutionVersion}`,
    solutionId: solutionDetails.solutionId,
    solutionName: solutionDetails.solutionName,
    solutionVersion: props.solutionVersion,
    analyticsReporting: false,
  });

  new SpokeStack(app, "instance-scheduler-on-aws-remote", {
    synthesizer: props.synthesizer,
    description: `(${solutionDetails.solutionId}S) ${solutionDetails.solutionName} remote ${props.solutionVersion}`,
    solutionId: solutionDetails.solutionId,
    solutionName: solutionDetails.solutionName,
    solutionVersion: props.solutionVersion,
    analyticsReporting: false,
  });
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
}

main();
