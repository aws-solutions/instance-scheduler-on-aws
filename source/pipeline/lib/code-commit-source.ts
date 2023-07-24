// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import { Construct } from "constructs";
import { PipelineBootstrapStack, tokenFor } from "./pipeline-bootstrap-stack";
import * as codecommit from "aws-cdk-lib/aws-codecommit";
import * as pipelines from "aws-cdk-lib/pipelines";

export function buildCodeCommitSource(scope: Construct) {
  const repoName = tokenFor(scope, PipelineBootstrapStack.ssmParamKeys.repoName);
  const branchName = tokenFor(scope, PipelineBootstrapStack.ssmParamKeys.repoBranch);
  const repo = codecommit.Repository.fromRepositoryName(scope, "instanceSchedulerRepo", repoName);

  return pipelines.CodePipelineSource.codeCommit(repo, branchName);
}
