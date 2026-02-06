// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { Aws } from "aws-cdk-lib";
import { Effect, Policy, PolicyStatement } from "aws-cdk-lib/aws-iam";
import { NagSuppressions } from "cdk-nag";
import { Construct } from "constructs";
import { RegionRegistrationCustomResource } from "../lambda-functions/region-registration";

export interface RegionRegistrationSSMParamsPermissionsPolicyProps {
  readonly namespace: string;
}

export function getSSMParams(namespace: string): PolicyStatement {
  return new PolicyStatement({
    actions: ["ssm:GetParametersByPath", "ssm:GetParameters", "ssm:GetParameter"],
    effect: Effect.ALLOW,
    resources: [
      `arn:${Aws.PARTITION}:ssm:*:${Aws.ACCOUNT_ID}:parameter${RegionRegistrationCustomResource.ssmParamPathName(namespace)}/*`,
    ],
  });
}

export function describeSSMParams(): PolicyStatement {
  return new PolicyStatement({
    actions: ["ssm:DescribeParameters"],
    effect: Effect.ALLOW,
    resources: ["*"],
  });
}

export function updateSSMParams(namespace: string): PolicyStatement {
  return new PolicyStatement({
    actions: ["ssm:PutParameter", "ssm:DeleteParameter", "ssm:DeleteParameters"],
    effect: Effect.ALLOW,
    resources: [
      `arn:${Aws.PARTITION}:ssm:*:${Aws.ACCOUNT_ID}:parameter${RegionRegistrationCustomResource.ssmParamPathName(namespace)}/*`,
    ],
  });
}

export class RegionRegistrationSSMParamsPermissionsPolicy extends Policy {
  constructor(scope: Construct, id: string, props: RegionRegistrationSSMParamsPermissionsPolicyProps) {
    super(scope, id);

    this.addStatements(getSSMParams(props.namespace), describeSSMParams(), updateSSMParams(props.namespace));

    NagSuppressions.addResourceSuppressions(this, []);
  }
}
