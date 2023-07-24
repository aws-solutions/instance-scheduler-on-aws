#!/usr/bin/env node
// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import * as cdk from "aws-cdk-lib";
import * as iam from "aws-cdk-lib/aws-iam";
import * as events from "aws-cdk-lib/aws-events";
import * as ssm from "aws-cdk-lib/aws-ssm";
import { ArnPrincipal, CompositePrincipal, Effect, PolicyStatement } from "aws-cdk-lib/aws-iam";
import { Construct } from "constructs";
import { AppRegistryForInstanceScheduler } from "./app-registry";
import { NagSuppressions } from "cdk-nag";

export interface InstanceSchedulerRemoteStackProps extends cdk.StackProps {
  readonly description: string;
  readonly solutionId: string;
  readonly solutionName: string;
  readonly solutionVersion: string;
  readonly appregApplicationName: string;
  readonly appregSolutionName: string;
}

export class InstanceSchedulerRemoteStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: InstanceSchedulerRemoteStackProps) {
    super(scope, id, props);

    //CFN Parameters
    const instanceSchedulerAccount = new cdk.CfnParameter(this, "InstanceSchedulerAccount", {
      description:
        "AccountID of the Instance Scheduler Hub stack that should be allowed to schedule resources in this account.",
      type: "String",
      allowedPattern: "(^[0-9]{12}$)",
      constraintDescription: "Account number is a 12 digit number",
    });

    const namespace = new cdk.CfnParameter(this, "Namespace", {
      type: "String",
      description:
        "Unique identifier used to differentiate between multiple solution deployments. " +
        "Must be set to the same value as the Hub stack",
    });

    const usingAWSOrganizations = new cdk.CfnParameter(this, "UsingAWSOrganizations", {
      type: "String",
      description:
        "Use AWS Organizations to automate spoke account registration. " +
        "Must be set to the same value as the Hub stack",
      allowedValues: ["Yes", "No"],
      default: "No",
    });

    // CFN Conditions
    const isMemberOfOrganization = new cdk.CfnCondition(this, "IsMemberOfOrganization", {
      expression: cdk.Fn.conditionEquals(usingAWSOrganizations, "Yes"),
    });

    const mappings = new cdk.CfnMapping(this, "mappings");
    mappings.setValue("SchedulerRole", "Name", "Scheduler-Role");
    mappings.setValue("SchedulerEventBusName", "Name", "scheduler-event-bus");

    new AppRegistryForInstanceScheduler(this, "AppRegistryForInstanceScheduler", {
      solutionId: props.solutionId,
      solutionName: props.solutionName,
      solutionVersion: props.solutionVersion,
      appregSolutionName: props.appregSolutionName,
      appregAppName: props.appregApplicationName,
    });

    const accountPrincipal = new ArnPrincipal(
      cdk.Fn.sub("arn:${AWS::Partition}:iam::${accountId}:root", {
        accountId: instanceSchedulerAccount.valueAsString,
      }),
    );
    const servicePrincipal = new iam.ServicePrincipal("lambda.amazonaws.com");

    const principalPolicyStatement = new PolicyStatement();
    principalPolicyStatement.addActions("sts:AssumeRole");
    principalPolicyStatement.effect = Effect.ALLOW;

    const principals = new CompositePrincipal(accountPrincipal, servicePrincipal);
    principals.addToPolicy(principalPolicyStatement);

    const ec2SchedulerCrossAccountRole = new iam.Role(this, "EC2SchedulerCrossAccountRole", {
      roleName: cdk.Fn.sub("${Namespace}-${Name}", {
        Name: mappings.findInMap("SchedulerRole", "Name"),
      }),
      path: "/",
      assumedBy: principals,
      inlinePolicies: {
        EC2InstanceSchedulerRemote: new iam.PolicyDocument({
          statements: [
            new PolicyStatement({
              actions: ["rds:DeleteDBSnapshot", "rds:DescribeDBSnapshots", "rds:StopDBInstance"],
              effect: Effect.ALLOW,
              resources: [cdk.Fn.sub("arn:${AWS::Partition}:rds:*:${AWS::AccountId}:snapshot:*")],
            }),
            new PolicyStatement({
              actions: [
                "rds:AddTagsToResource",
                "rds:RemoveTagsFromResource",
                "rds:DescribeDBSnapshots",
                "rds:StartDBInstance",
                "rds:StopDBInstance",
              ],
              effect: Effect.ALLOW,
              resources: [cdk.Fn.sub("arn:${AWS::Partition}:rds:*:${AWS::AccountId}:db:*")],
            }),
            new PolicyStatement({
              actions: [
                "rds:AddTagsToResource",
                "rds:RemoveTagsFromResource",
                "rds:StartDBCluster",
                "rds:StopDBCluster",
              ],
              effect: Effect.ALLOW,
              resources: [cdk.Fn.sub("arn:${AWS::Partition}:rds:*:${AWS::AccountId}:cluster:*")],
            }),
            new PolicyStatement({
              actions: ["ec2:StartInstances", "ec2:StopInstances", "ec2:CreateTags", "ec2:DeleteTags"],
              effect: Effect.ALLOW,
              resources: [cdk.Fn.sub("arn:${AWS::Partition}:ec2:*:${AWS::AccountId}:instance/*")],
            }),
            new PolicyStatement({
              actions: [
                "rds:DescribeDBClusters",
                "rds:DescribeDBInstances",
                "ec2:DescribeInstances",
                "ssm:DescribeMaintenanceWindows",
                "ssm:DescribeMaintenanceWindowExecutions",
                "tag:GetResources",
              ],
              effect: Effect.ALLOW,
              resources: ["*"],
            }),
          ],
        }),
      },
    });

    const ec2ModifyInstancePolicy = new iam.Policy(this, "Ec2ModifyInstanceAttrPolicy", {
      roles: [ec2SchedulerCrossAccountRole],
      statements: [
        new PolicyStatement({
          actions: ["ec2:ModifyInstanceAttribute"],
          effect: Effect.ALLOW,
          resources: [cdk.Fn.sub("arn:${AWS::Partition}:ec2:*:${AWS::AccountId}:instance/*")],
        }),
      ],
    });

    NagSuppressions.addResourceSuppressions(ec2ModifyInstancePolicy, [
      {
        id: "AwsSolutions-IAM5",
        reason:
          "All policies have been scoped to be as restrictive as possible. This solution needs to access ec2/rds resources across all regions.",
      },
    ]);

    // Event Rule to capture SSM Parameter Store creation by this stack
    // SSM parameter to invoke event rule
    const ssmParameterNamespace = new ssm.StringParameter(this, "SSMParameterNamespace", {
      description: "This parameter is for Instance Scheduler solution to support accounts in AWS Organizations.",
      stringValue: namespace.valueAsString,
      parameterName: "/instance-scheduler/do-not-delete-manually",
    });

    const ssmParameterNamespace_ref = ssmParameterNamespace.node.defaultChild as ssm.CfnParameter;

    // Event Delivery Role and Policy necessary to migrate a sender-receiver relationship to Use AWS Organizations
    const schedulerEventDeliveryRole = new iam.Role(this, "SchedulerEventDeliveryRole", {
      description:
        "Event Role to add the permissions necessary to migrate a sender-receiver relationship to Use AWS Organizations",
      assumedBy: new iam.ServicePrincipal("events.amazonaws.com"),
    });
    const schedulerEventDeliveryPolicy = new iam.Policy(this, "SchedulerEventDeliveryPolicy", {
      roles: [schedulerEventDeliveryRole],
      statements: [
        new iam.PolicyStatement({
          actions: ["events:PutEvents"],
          effect: iam.Effect.ALLOW,
          resources: [
            cdk.Fn.sub(
              "arn:${AWS::Partition}:events:${AWS::Region}:${InstanceSchedulerAccount}:event-bus/${Namespace}-${EventBusName}",
              {
                EventBusName: mappings.findInMap("SchedulerEventBusName", "Name"),
              },
            ),
          ],
        }),
      ],
    });

    const parameterStoreEventRule = new events.CfnRule(this, "scheduler-ssm-parameter-store-event", {
      description:
        "Event rule to invoke Instance Scheduler lambda function to store spoke account id in configuration.",
      state: "ENABLED",
      targets: [
        {
          arn: cdk.Fn.sub(
            "arn:${AWS::Partition}:events:${AWS::Region}:${InstanceSchedulerAccount}:event-bus/${Namespace}-${EventBusName}",
            {
              EventBusName: mappings.findInMap("SchedulerEventBusName", "Name"),
            },
          ),
          id: "Spoke-SSM-Parameter-Event",
          roleArn: schedulerEventDeliveryRole.roleArn,
        },
      ],
      eventPattern: {
        account: [this.account],
        source: ["aws.ssm"],
        "detail-type": ["Parameter Store Change"],
        detail: {
          name: ["/instance-scheduler/do-not-delete-manually"],
          operation: ["Create", "Delete"],
          type: ["String"],
        },
      },
    });

    const schedulerEventDeliveryRole_ref = schedulerEventDeliveryRole.node.findChild("Resource") as iam.CfnRole;
    const schedulerEventDeliveryPolicy_ref = schedulerEventDeliveryPolicy.node.findChild("Resource") as iam.CfnPolicy;

    // wait for the events rule to be created before creating/deleting the SSM parameter
    parameterStoreEventRule.addDependency(schedulerEventDeliveryRole_ref);
    ssmParameterNamespace_ref.addDependency(parameterStoreEventRule);
    schedulerEventDeliveryPolicy_ref.cfnOptions.condition = isMemberOfOrganization;
    schedulerEventDeliveryRole_ref.cfnOptions.condition = isMemberOfOrganization;
    parameterStoreEventRule.cfnOptions.condition = isMemberOfOrganization;
    ssmParameterNamespace_ref.cfnOptions.condition = isMemberOfOrganization;

    //CFN Output
    new cdk.CfnOutput(this, "CrossAccountRole", {
      value: ec2SchedulerCrossAccountRole.roleArn,
      description:
        "Arn for cross account role for Instance scheduler, add this arn to the list of crossaccount roles (CrossAccountRoles) parameter of the Instance Scheduler template.",
    });

    const ec2SchedulerCrossAccountRole_cfn_ref = ec2SchedulerCrossAccountRole.node.defaultChild as iam.CfnRole;
    ec2SchedulerCrossAccountRole_cfn_ref.overrideLogicalId("EC2SchedulerCrossAccountRole");
    ec2SchedulerCrossAccountRole_cfn_ref.cfnOptions.metadata = {
      cfn_nag: {
        rules_to_suppress: [
          {
            id: "W11",
            reason:
              "All policies have been scoped to be as restrictive as possible. This solution needs to access ec2/rds resources across all regions.",
          },
          {
            id: "W28",
            reason: "The role name is defined to allow cross account access from the hub account.",
          },
          {
            id: "W76",
            reason:
              "All policies have been scoped to be as restrictive as possible. This solution needs to access ec2/rds resources across all regions.",
          },
        ],
      },
    };
    NagSuppressions.addResourceSuppressions(ec2SchedulerCrossAccountRole_cfn_ref, [
      {
        id: "AwsSolutions-IAM5",
        reason:
          "All policies have been scoped to be as restrictive as possible. This solution needs to access ec2/rds resources across all regions.",
      },
    ]);

    const stack = cdk.Stack.of(this);

    stack.templateOptions.metadata = {
      "AWS::CloudFormation::Interface": {
        ParameterGroups: [
          {
            Label: { default: "Namespace Configuration" },
            Parameters: ["Namespace"],
          },
          {
            Label: { default: "Account Structure" },
            Parameters: ["InstanceSchedulerAccount", "UsingAWSOrganizations"],
          },
        ],
        ParameterLabels: {
          InstanceSchedulerAccount: {
            default: "Hub Account ID",
          },
          UsingAWSOrganizations: {
            default: "Use AWS Organizations",
          },
        },
      },
    };
    stack.templateOptions.templateFormatVersion = "2010-09-09";
  }
}
