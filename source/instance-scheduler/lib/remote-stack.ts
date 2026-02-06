// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { CfnOutput, CfnResource, CustomResource, Stack, StackProps } from "aws-cdk-lib";
import { ArnPrincipal, CfnRole, CompositePrincipal } from "aws-cdk-lib/aws-iam";
import { Construct } from "constructs";
import { ParameterWithLabel, YesNoParameter, YesNoType, addParameterGroup, overrideLogicalId } from "./cfn";
import { SchedulerRole } from "./iam/scheduler-role";
import { roleArnFor } from "./iam/roles";
import { SchedulingRequestHandlerLambda } from "./lambda-functions/scheduling-request-handler";
import { FunctionFactory, PythonFunctionFactory } from "./lambda-functions/function-factory";
import { addCfnGuardSuppression } from "./helpers/cfn-guard";
import { HubResourceRegistration } from "./lambda-functions/resource-registration";
import { IceErrorRetry } from "./lambda-functions/ice-error-retry";
import { RegionEventRulesCustomResource } from "./lambda-functions/region-event-rules";
import { RegionRegistrationCustomResource } from "./lambda-functions/region-registration";
import { TargetStack } from "./stack-types";
import { SpokeRegistrationLambda } from "./lambda-functions/spoke-registration";
import { SequencingGates } from "./helpers/deployment-sequencing";

export interface SpokeStackProps extends StackProps {
  readonly solutionId: string;
  readonly solutionName: string;
  readonly solutionVersion: string;
  readonly factory?: FunctionFactory;
}

export class SpokeStack extends Stack {
  public static sharedConfig: {
    namespace: string;
  };

  constructor(scope: Construct, id: string, props: SpokeStackProps) {
    super(scope, id, props);

    const namespace = new ParameterWithLabel(this, "Namespace", {
      label: "Namespace",
      description:
        "Unique identifier used to differentiate between multiple solution deployments. " +
        "Must be set to the same value as the Hub stack. Must be non-empty for Organizations deployments.",
      default: "default",
    });

    const usingAWSOrganizations = new YesNoParameter(this, "UsingAWSOrganizations", {
      label: "Use AWS Organizations",
      description:
        "Use AWS Organizations to automate spoke account registration. " +
        "Must be set to the same value as the Hub stack",
      default: YesNoType.No,
    });

    const instanceSchedulerAccount = new ParameterWithLabel(this, "InstanceSchedulerAccount", {
      label: "Hub Account ID",
      description:
        "Account ID of the Instance Scheduler Hub stack that should be allowed to schedule resources in this account.",
      allowedPattern: String.raw`^\d{12}$`,
      constraintDescription: "Account number is a 12 digit number",
    });
    const hubAccountId = instanceSchedulerAccount.valueAsString;

    const scheduleTagKey = new ParameterWithLabel(this, "ScheduleTagKey", {
      label: "Schedule tag key",
      description:
        "The tag key Instance Scheduler will read to determine the schedule for a resource. Must be set to the same value as the Hub stack. ",
      default: "Schedule",
      minLength: 1,
      maxLength: 127,
    });

    addParameterGroup(this, {
      label: "Infrastructure",
      parameters: [namespace, usingAWSOrganizations, instanceSchedulerAccount, scheduleTagKey],
    });

    const regions = new ParameterWithLabel(this, "Regions", {
      label: "Region(s)",
      type: "CommaDelimitedList",
      description:
        "Comma-separated List of regions in which resources should be scheduled. Leave blank for current region only.",
      default: "",
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

    const licenseManagerArns = new ParameterWithLabel(this, "LicenseManagerArns", {
      label: "License Manager Arns for EC2",
      description:
        "comma-separated list of license manager arns to grant Instance Scheduler ec2:StartInstance permissions to provide the EC2 " +
        " service with license manager permissions to start the instances." +
        " This allows the scheduler to start EC2 instances with license manager configuration enabled." +
        " Leave blank to disable." +
        " For details on the exact policy created, refer to security section of the implementation guide" +
        " (https://aws.amazon.com/solutions/implementations/instance-scheduler-on-aws/)",
      type: "CommaDelimitedList",
      default: "",
    });

    addParameterGroup(this, {
      label: "Member-Account Scheduling",
      parameters: [regions, kmsKeyArns, licenseManagerArns],
    });

    SpokeStack.sharedConfig = {
      namespace: namespace.valueAsString,
    };

    const USER_AGENT_EXTRA = `AwsSolution/${props.solutionId}/${props.solutionVersion}`;
    const REGIONAL_EVENT_BUS_NAME = `IS-LocalEvents-${namespace.valueAsString}`;

    const schedulingRole = new SchedulerRole(this, "EC2SchedulerCrossAccountRole", {
      assumedBy: new CompositePrincipal(
        new ArnPrincipal(roleArnFor(hubAccountId, SchedulingRequestHandlerLambda.roleName(namespace.valueAsString))),
        new ArnPrincipal(roleArnFor(hubAccountId, HubResourceRegistration.roleName(namespace.valueAsString))),
        new ArnPrincipal(roleArnFor(hubAccountId, IceErrorRetry.roleName(namespace.valueAsString))),
        new ArnPrincipal(roleArnFor(hubAccountId, SpokeRegistrationLambda.roleName(namespace.valueAsString))),
      ),
      namespace: namespace.valueAsString,
      kmsKeys: kmsKeyArns.valueAsList,
      licenseManagerArns: licenseManagerArns.valueAsList,
      regionalEventBusName: REGIONAL_EVENT_BUS_NAME,
    });
    addCfnGuardSuppression(schedulingRole, ["CFN_NO_EXPLICIT_RESOURCE_NAMES"]);
    overrideLogicalId(schedulingRole, "EC2SchedulerCrossAccountRole");

    const schedulerRoleCfnResource = schedulingRole.node.defaultChild as CfnRole;
    schedulerRoleCfnResource.addOverride("UpdateReplacePolicy", "Retain");

    const factory = props.factory ?? new PythonFunctionFactory();

    const regionEventRulesCustomResource = new RegionEventRulesCustomResource(this, "RegionEventRulesCustomResource", {
      hubAccountId: hubAccountId,
      namespace: namespace.valueAsString,
      factory: factory,
      scheduleTagKey: scheduleTagKey.valueAsString,
      USER_AGENT_EXTRA: USER_AGENT_EXTRA,
      taggingEventBusName: HubResourceRegistration.registrationEventBusName(namespace.valueAsString),
      version: props.solutionVersion,
      regionalEventBusName: REGIONAL_EVENT_BUS_NAME,
    });

    const regionsCustomResource = new CustomResource(this, "CreateRegionalEventRules", {
      serviceToken: regionEventRulesCustomResource.regionalEventsCustomResourceLambda.functionArn,
      resourceType: "Custom::SetupRegionalEvents",
      properties: {
        regions: regions.valueAsList,
        version: props.solutionVersion, // force an update when updating solution version
      },
    });
    const regionsCustomResourceCfnResource = regionsCustomResource.node.defaultChild as CfnResource;
    regionsCustomResourceCfnResource.addOverride("UpdateReplacePolicy", "Retain");

    const regionRegistrationCustomResource = new RegionRegistrationCustomResource(
      this,
      "RegionRegistrationCustomResource",
      {
        hubAccountId: hubAccountId,
        namespace: namespace.valueAsString,
        factory: factory,
        USER_AGENT_EXTRA: USER_AGENT_EXTRA,
        version: props.solutionVersion,
        targetStack: TargetStack.REMOTE,
        hubRegisterRegionFunctionName: SpokeRegistrationLambda.getFunctionName(namespace.valueAsString),
        hubRegisterRegionRoleName: SpokeRegistrationLambda.roleName(namespace.valueAsString),
      },
    );

    const regionRegistration = new CustomResource(this, "RegisterRegions", {
      serviceToken: regionRegistrationCustomResource.regionRegistrationCustomResourceProvider.serviceToken,
      resourceType: "Custom::RegisterRegion",
      properties: {
        regions: regions.valueAsList,
        version: props.solutionVersion, // force an update when updating solution version
      },
    });

    // resource dependencies to allow de-registering event to complete before removing IAM roles and permissions.
    const regionRegistrationCfnResource = regionRegistration.node.defaultChild as CfnResource;
    regionRegistrationCfnResource.addDependency(SequencingGates.afterAllLambdas(this));
    regionRegistrationCfnResource.addDependency(SequencingGates.afterAllRoles(this));
    regionRegistrationCfnResource.addDependency(SequencingGates.afterAllPolicies(this));
    regionRegistrationCfnResource.addOverride("UpdateReplacePolicy", "Retain");

    new CfnOutput(this, "RegionalEventBusName", {
      value: regionsCustomResource.getAtt("REGIONAL_BUS_NAME").toString(),
      description: "Regional event bus name.",
    });

    new CfnOutput(this, "SchedulerRoleArn", {
      value: schedulingRole.roleArn,
      description: "Scheduler role ARN",
    });
  }
}
