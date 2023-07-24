// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { CfnParameter, DefaultStackSynthesizer, Stack } from "aws-cdk-lib";
import * as ssm from "aws-cdk-lib/aws-ssm";
import { StringParameter } from "aws-cdk-lib/aws-ssm";
import { Construct } from "constructs";

export class PipelineBootstrapStack extends Stack {
  static readonly ssmParamKeys = {
    codestarArn: "/InstanceScheduler-build/connection/arn",
    repoOwner: "/InstanceScheduler-build/connection/owner",
    repoName: "/InstanceScheduler-build/connection/repo",
    repoBranch: "/InstanceScheduler-build/connection/branch",
  };

  constructor(scope: Construct, construct_id: string) {
    super(scope, construct_id, {
      synthesizer: new DefaultStackSynthesizer({
        generateBootstrapVersionRule: false,
      }),
    });

    const ssmInputs = {
      codestarArn: new CfnParameter(this, "CodestarArn", {
        type: "String",
        description: "CodeStar connection ARN (when sourcing from GitHub)",
        default: "----",
      }),
      repoOwner: new CfnParameter(this, "RepoOwner", {
        type: "String",
        description: "GitHub repo owner (when sourcing from GitHub)",
        default: "----",
      }),
      repoName: new CfnParameter(this, "RepoName", {
        type: "String",
        description: "repo name",
        default: "----",
      }),
      repoBranch: new CfnParameter(this, "RepoBranch", {
        type: "String",
        description: "repo branch",
        default: "----",
      }),
    };

    const stack = Stack.of(this);
    stack.templateOptions.metadata = {
      "AWS::CloudFormation::Interface": {
        ParameterGroups: [
          {
            Label: {
              default: "Required",
            },
            Parameters: ["RepoName", "RepoBranch"],
          },
          {
            Label: {
              default: "GitHub-Only",
            },
            Parameters: ["RepoOwner", "CodestarArn"],
          },
        ],
      },
    };

    new ssm.StringParameter(this, "code_arn", {
      description: "CodeStar connection ARN (if using github as source)",
      parameterName: PipelineBootstrapStack.ssmParamKeys.codestarArn,
      stringValue: ssmInputs.codestarArn.valueAsString,
    });

    new ssm.StringParameter(this, "repo_owner", {
      description: "Github repo owner (if using github as source)",
      parameterName: PipelineBootstrapStack.ssmParamKeys.repoOwner,
      stringValue: ssmInputs.repoOwner.valueAsString,
    });

    new ssm.StringParameter(this, "repo_name", {
      description: "repo name",
      parameterName: PipelineBootstrapStack.ssmParamKeys.repoName,
      stringValue: ssmInputs.repoName.valueAsString,
    });

    new ssm.StringParameter(this, "repo_branch", {
      description: "Github repo branch",
      parameterName: PipelineBootstrapStack.ssmParamKeys.repoBranch,
      stringValue: ssmInputs.repoBranch.valueAsString,
    });
  }
}

export function tokenFor(scope: Construct, ssmParamKey: string) {
  return StringParameter.valueForStringParameter(scope, ssmParamKey);
}
