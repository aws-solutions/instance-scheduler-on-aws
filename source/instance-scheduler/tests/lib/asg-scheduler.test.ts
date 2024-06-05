// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import { Template } from "aws-cdk-lib/assertions";
import { conditions, createAsgSchedulerStack } from "../test_utils/stack-factories";

// Brief type of CloudFormation resource for testing
type CfnResourceType = {
  readonly Type: string;
  readonly Properties: unknown;
  readonly Condition?: string;
};

it("should put a condition on every resource in AsgScheduler", () => {
  const id = "ASGSchedulerTest";
  const asgSchedulerStack = createAsgSchedulerStack(id);
  const jsonTemplate = Template.fromStack(asgSchedulerStack).toJSON();
  const resources: { [key: string]: CfnResourceType } = jsonTemplate.Resources;

  if (!resources) throw new Error("Resources not found.");

  for (const key in resources) {
    const condition = resources[key].Condition;

    if (key.startsWith(id)) {
      expect(condition).toEqual(conditions.enableAsgs);
    } else {
      expect(condition).not.toEqual(conditions.enableAsgs);
    }
  }
});
