// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import * as cfn from "@aws-sdk/client-cloudformation";

export class CfnStackResourceFinder {
  readonly resources: cfn.StackResourceSummary[];
  constructor(resources: cfn.StackResourceSummary[]) {
    this.resources = resources;
  }

  static async fromStackName(stackName: string) {
    const cfnClient = new cfn.CloudFormationClient();

    const paginatorConfig = {
      client: cfnClient,
      pageSize: 20,
    };

    const listStackResourcesPaginator = cfn.paginateListStackResources(paginatorConfig, {
      StackName: stackName,
    });

    const stackResources: cfn.StackResourceSummary[] = [];
    for await (const { StackResourceSummaries } of listStackResourcesPaginator) {
      if (StackResourceSummaries) {
        stackResources.push(...StackResourceSummaries);
      }
    }

    return new CfnStackResourceFinder(stackResources);
  }

  findResourceByPartialId(partialId: string) {
    return this.resources.find(
      (resource: cfn.StackResourceSummary) => resource.LogicalResourceId?.startsWith(partialId),
    );
  }
}
