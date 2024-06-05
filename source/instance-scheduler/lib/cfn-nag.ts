// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { CfnResource } from "aws-cdk-lib";
import { IConstruct } from "constructs";

export interface CfnNagSuppression {
  readonly id: string;
  readonly reason: string;
}

export function addCfnNagSuppressions(resource: IConstruct, ...suppressions: CfnNagSuppression[]): void {
  const cfnResource = resource.node.defaultChild as CfnResource;
  if (!cfnResource?.cfnOptions) {
    throw new Error(`Resource ${cfnResource?.logicalId} has no cfnOptions, unable to add cfn-nag suppression`);
  }
  const existingSuppressions: CfnNagSuppression[] = cfnResource.cfnOptions.metadata?.cfn_nag?.rules_to_suppress;
  if (existingSuppressions) {
    existingSuppressions.push(...suppressions);
  } else {
    cfnResource.cfnOptions.metadata = {
      cfn_nag: {
        rules_to_suppress: [...suppressions],
      },
    };
  }
}
