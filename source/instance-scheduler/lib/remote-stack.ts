// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { Stack, StackProps } from "aws-cdk-lib";
import { ArnPrincipal } from "aws-cdk-lib/aws-iam";
import { Construct } from "constructs";
import { ParameterWithLabel, YesNoParameter, YesNoType, addParameterGroup, overrideLogicalId } from "./cfn";
import { SchedulerRole } from "./iam/scheduler-role";
import { roleArnFor } from "./iam/roles";
import { SchedulingRequestHandlerLambda } from "./lambda-functions/scheduling-request-handler";
import { AsgHandler } from "./lambda-functions/asg-handler";

import { AsgSchedulingRole } from "./iam/asg-scheduling-role";
import { RemoteRegistrationCustomResource } from "./lambda-functions/remote-registration";
import { FunctionFactory, PythonFunctionFactory } from "./lambda-functions/function-factory";

export interface SpokeStackProps extends StackProps {
  readonly solutionId: string;
  readonly solutionName: string;
  readonly solutionVersion: string;
  readonly factory?: FunctionFactory;
}

export class SpokeStack extends Stack {
  constructor(scope: Construct, id: string, props: SpokeStackProps) {
    super(scope, id, props);

    const instanceSchedulerAccount = new ParameterWithLabel(this, "InstanceSchedulerAccount", {
      label: "Hub Account ID",
      description:
        "Account ID of the Instance Scheduler Hub stack that should be allowed to schedule resources in this account.",
      allowedPattern: String.raw`^\d{12}$`,
      constraintDescription: "Account number is a 12 digit number",
    });
    const hubAccountId = instanceSchedulerAccount.valueAsString;

    const usingAWSOrganizations = new YesNoParameter(this, "UsingAWSOrganizations", {
      label: "Use AWS Organizations",
      description:
        "Use AWS Organizations to automate spoke account registration. " +
        "Must be set to the same value as the Hub stack",
      default: YesNoType.No,
    });

    const namespace = new ParameterWithLabel(this, "Namespace", {
      label: "Namespace",
      description:
        "Unique identifier used to differentiate between multiple solution deployments. " +
        "Must be set to the same value as the Hub stack. Must be non-empty for Organizations deployments.",
      default: "default",
    });

    addParameterGroup(this, {
      label: "Account structure",
      parameters: [instanceSchedulerAccount, usingAWSOrganizations, namespace],
    });

    const kmsKeyArns = new ParameterWithLabel(this, "KmsKeyArns", {
      label: "Kms Key Arns for EC2",
      description:
        "comma-separated list of kms arns to grant Instance Scheduler kms:CreateGrant permissions to provide the EC2 " +
        " service with Decrypt permissions for encrypted EBS volumes." +
        " This allows the scheduler to start EC2 instances with attached encrypted EBS volumes." +
        " provide just (*) to give limited access to all kms keys, leave blank to disable." +
        " For details on the exact policy created, refer to security section of the implementation guide" +
        " (https://aws.amazon.com/solutions/implementations/instance-scheduler-on-aws/)",
      type: "CommaDelimitedList",
      default: "",
    });

    addParameterGroup(this, {
      label: "Service-specific",
      parameters: [kmsKeyArns],
    });

    const USER_AGENT_EXTRA = `AwsSolution/${props.solutionId}/${props.solutionVersion}`;

    const schedulingRole = new SchedulerRole(this, "EC2SchedulerCrossAccountRole", {
      assumedBy: new ArnPrincipal(
        roleArnFor(hubAccountId, SchedulingRequestHandlerLambda.roleName(namespace.valueAsString)),
      ),
      namespace: namespace.valueAsString,
      kmsKeys: kmsKeyArns.valueAsList,
    });
    overrideLogicalId(schedulingRole, "EC2SchedulerCrossAccountRole");

    new AsgSchedulingRole(this, "AsgSchedulingRole", {
      assumedBy: new ArnPrincipal(roleArnFor(hubAccountId, AsgHandler.roleName(namespace.valueAsString))),
      namespace: namespace.valueAsString,
    });

    const factory = props.factory ?? new PythonFunctionFactory();

    new RemoteRegistrationCustomResource(this, "RemoteRegistrationCustomResource", {
      hubAccountId: hubAccountId,
      namespace: namespace.valueAsString,
      shouldRegisterSpokeAccountCondition: usingAWSOrganizations.getCondition(),
      factory: factory,
      USER_AGENT_EXTRA: USER_AGENT_EXTRA,
    });
  }
}
