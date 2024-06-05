// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import {
  AutomationDocument,
  DocumentFormat,
  Input,
  HardCodedString,
  InvokeLambdaFunctionStep,
  StringVariable,
  HardCodedStringMap,
} from "@cdklabs/cdk-ssm-documents";
import { Stack } from "aws-cdk-lib";
import { Role, ServicePrincipal } from "aws-cdk-lib/aws-iam";
import { Function as LambdaFunction } from "aws-cdk-lib/aws-lambda";
import { InvocationType } from "aws-cdk-lib/triggers";
import { NagSuppressions } from "cdk-nag";

export interface SpokeDeregistrationRunbookProperties {
  lambdaFunction: LambdaFunction;
  namespace: string;
}

export class SpokeDeregistrationRunbook {
  constructor(scope: Stack, props: SpokeDeregistrationRunbookProperties) {
    const role = new Role(scope, "SpokeDeregistrationRunbookRole", {
      assumedBy: new ServicePrincipal("ssm.amazonaws.com"),
      description: "Role assumed by SSM Automation to call the spoke registration lambda",
    });
    props.lambdaFunction.grantInvoke(role);

    const automationDocument = new AutomationDocument(scope, "SpokeDeregistrationRunbook", {
      description: "Deregister a spoke account from Instance Scheduler on AWS on demand",
      documentFormat: DocumentFormat.YAML,
      assumeRole: HardCodedString.of(role.roleArn),
      docInputs: [
        Input.ofTypeString("AccountId", {
          description: "Spoke Account ID used for registration",
          allowedPattern: "^\\d{12}$",
        }),
      ],
    });

    automationDocument.addStep(
      new InvokeLambdaFunctionStep(scope, "InvokeSpokeRegistrationLambdaStep", {
        name: "InvokeSpokeRegistrationLambda",
        description:
          "Invokes the Instance Scheduler on AWS spoke registration lambda to deregister a given AWS Account ID",
        functionName: HardCodedString.of(props.lambdaFunction.functionArn),
        invocationType: HardCodedString.of(InvocationType.REQUEST_RESPONSE),
        payload: HardCodedStringMap.of({
          account: StringVariable.of("AccountId"),
          operation: "Deregister",
        }),
      }),
    );

    const defaultPolicy = role.node.tryFindChild("DefaultPolicy");
    if (!defaultPolicy) {
      throw Error("Unable to find default policy on role");
    }

    NagSuppressions.addResourceSuppressions(defaultPolicy, [
      {
        id: "AwsSolutions-IAM5",
        appliesTo: ["Resource::<SpokeRegistrationHandler923F17AC.Arn>:*"],
        reason: "permissions to invoke all versions of the spoke registration lambda",
      },
    ]);
  }
}
