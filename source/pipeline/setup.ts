// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import * as cfn from "@aws-sdk/client-cloudformation";

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export default async function setupTestSuite(_globalConfig: never, _projectConfig: never) {
  const hubStackName = process.env["HUB_STACK"];
  const testAssetsStackName = process.env["TEST_ASSETS_STACK"];

  if (hubStackName == null) {
    throw new Error(`Missing required environment variable: HUB_STACK`);
  }

  if (testAssetsStackName == null) {
    throw new Error(`Missing required environment variable: TEST_ASSETS_STACK`);
  }

  console.log(`HUB STACK: ${hubStackName}`);
  console.log(`TEST ASSETS STACK: ${testAssetsStackName}`);

  copyOutputsToEnv(await describeCfnStackOutputs(hubStackName));
  copyOutputsToEnv(await describeCfnStackOutputs(testAssetsStackName));
}

const cfnClient = new cfn.CloudFormationClient();
async function describeCfnStackOutputs(stackName: string) {
  const stackDescription = await cfnClient.send(
    new cfn.DescribeStacksCommand({
      StackName: stackName,
    }),
  );

  const stackOutputs = stackDescription.Stacks?.[0].Outputs;

  if (stackOutputs == null) {
    throw new Error(`unable to describe stack outputs for stack ${stackName}`);
  }

  return stackOutputs;
}

function copyOutputsToEnv(outputs: cfn.Output[]) {
  for (const output of outputs) {
    const key = output.OutputKey;
    const value = output.OutputValue;
    if (key && value) {
      process.env[key] = value;
    }
  }
}
