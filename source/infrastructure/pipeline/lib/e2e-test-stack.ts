// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import { testResourceProviders } from "../e2e-tests";
import { CfnOutput } from "aws-cdk-lib";

export class E2eTestStack extends cdk.Stack {
  outputs: Record<string, CfnOutput> = {};
  constructor(scope: Construct, id: string) {
    super(scope, id);

    for (const testResourceProvider of testResourceProviders) {
      const output = testResourceProvider.createTestResources(this);
      this.outputs = { ...this.outputs, ...output };
    }

    cdk.Stack.of(this);
  }
}
