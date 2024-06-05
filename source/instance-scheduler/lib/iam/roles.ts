// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import { Aws } from "aws-cdk-lib";

export function roleArnFor(accountId: string, roleName: string) {
  return `arn:${Aws.PARTITION}:iam::${accountId}:role/${roleName}`;
}
