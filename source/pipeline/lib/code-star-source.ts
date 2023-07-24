// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import * as cp_actions from "aws-cdk-lib/aws-codepipeline-actions";
import { CodePipelineSource, FileSet } from "aws-cdk-lib/pipelines";
import { Artifact } from "aws-cdk-lib/aws-codepipeline";
import { PipelineBootstrapStack, tokenFor } from "./pipeline-bootstrap-stack";
import { Construct } from "constructs";

class CodeStarSource extends CodePipelineSource {
  // We need another class here instead of using the factory .connection() because
  // the factory uses the owner/repo string as the name for the construct. Since we're
  // looking up the connection configuration during deploy using SSM, we need to specify
  // a static name for synthesis.
  //
  // The implementation here is the same as what is produced from the factory method, but
  // with the addition of statically defining the name.

  private readonly owner: string;
  private readonly repo: string;

  private readonly connectionArn: string;

  constructor(
    name: string,
    connectionArn: string,
    owner: string,
    repo: string,
    readonly branch: string,
  ) {
    super(name);
    this.owner = owner;
    this.repo = repo;
    this.connectionArn = connectionArn;
    this.configurePrimaryOutput(new FileSet("Source", this));
  }

  protected getAction(output: Artifact, actionName: string, runOrder: number, variablesNamespace?: string) {
    return new cp_actions.CodeStarConnectionsSourceAction({
      output,
      actionName,
      runOrder,
      connectionArn: this.connectionArn,
      owner: this.owner,
      repo: this.repo,
      branch: this.branch,
      variablesNamespace,
    });
  }
}

export function buildCodeStarSource(scope: Construct) {
  return new CodeStarSource(
    "CodeStarConnection",
    tokenFor(scope, PipelineBootstrapStack.ssmParamKeys.codestarArn),
    tokenFor(scope, PipelineBootstrapStack.ssmParamKeys.repoOwner),
    tokenFor(scope, PipelineBootstrapStack.ssmParamKeys.repoName),
    tokenFor(scope, PipelineBootstrapStack.ssmParamKeys.repoBranch),
  );
}

export default CodeStarSource;
