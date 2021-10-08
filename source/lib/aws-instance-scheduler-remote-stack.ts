#!/usr/bin/env node
/*****************************************************************************
 *  Copyright 2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.   *
 *                                                                            *
 *  Licensed under the Apache License, Version 2.0 (the "License"). You may   *
 *  not use this file except in compliance with the License. A copy of the    *
 *  License is located at                                                     *
 *                                                                            *
 *      http://www.apache.org/licenses/LICENSE-2.0                            *
 *                                                                            *
 *  or in the 'license' file accompanying this file. This file is distributed *
 *  on an 'AS IS' BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND,        *
 *  express or implied. See the License for the specific language governing   *
 *  permissions and limitations under the License.                            *
 *****************************************************************************/

import * as cdk from '@aws-cdk/core';
import * as iam from '@aws-cdk/aws-iam';
import * as ssm from '@aws-cdk/aws-ssm';
import * as events from "@aws-cdk/aws-events";

export interface AwsInstanceSchedulerRemoteStackProps extends cdk.StackProps {
    readonly description: string,
    readonly solutionId: string,
    readonly solutionTradeMarkName: string,
    readonly solutionProvider: string,
    readonly solutionBucket: string,
    readonly solutionName: string,
    readonly solutionVersion: string
  }

export class AwsInstanceSchedulerRemoteStack extends cdk.Stack {

    constructor(scope: cdk.Construct, id: string, props: AwsInstanceSchedulerRemoteStackProps) {
        super(scope, id, props);

        //CFN Parameters
        const instanceSchedulerAccount = new cdk.CfnParameter(this, 'InstanceSchedulerAccount', {
            description: 'Instance Scheduler Hub Account number to manage EC2 and RDS Resources in this account.',
            type: "String",
            allowedPattern: '(^[0-9]{12}$)',
            constraintDescription: 'Account number is a 12 digit number'
        });

        const namespace = new cdk.CfnParameter(this, "Namespace", {
            type: "String",
            description: "Unique identifier used to differentiate between multiple solution deployments. Example: Test or Prod"
        });

        const usingAWSOrganizations = new cdk.CfnParameter(this, 'UsingAWSOrganizations', {
            type: 'String',
            description: 'Use this setting to automate spoke account enrollment if using AWS Organizations.',
            allowedValues: ["Yes", "No"],
            default: "No"
        })

        // CFN Conditions
        const isMemberOfOrganization = new cdk.CfnCondition(this,
          "IsMemberOfOrganization",
          {
              expression: cdk.Fn.conditionEquals(usingAWSOrganizations, 'Yes')
          })

        const isSpokeAccountEqualToHubAccount = new cdk.CfnCondition(this,
          "IsSpokeAccountEqualToHubAccount",
          {
              expression: cdk.Fn.conditionNot(cdk.Fn.conditionEquals(instanceSchedulerAccount, this.account))
          })

        const isUsingOrganizationAndNotHubAccount = new cdk.CfnCondition(this,
          "IsUsingOrganizationAndNotHubAccount",
          {
              expression: cdk.Fn.conditionAnd(isMemberOfOrganization, isSpokeAccountEqualToHubAccount)
          })


        const mappings = new cdk.CfnMapping(this, "mappings")
        mappings.setValue("Ec2StartSSMDocument", "Name", "Scheduler-StartTaggedEC2Instances-" + props["solutionVersion"])
        mappings.setValue("Ec2StopSSMDocument", "Name", "Scheduler-StopTaggedEC2Instances-" + props["solutionVersion"])
        mappings.setValue("RDSInstancesStartSSMDocument", "Name", "Scheduler-StartTaggedRDSInstances-" + props["solutionVersion"])
        mappings.setValue("RDSInstancesStopSSMDocument", "Name", "Scheduler-StopTaggedRDSInstances-" + props["solutionVersion"])
        mappings.setValue("RDSTaggedClustersStartSSMDocument", "Name", "Scheduler-StartTaggedRDSClusters-" + props["solutionVersion"])
        mappings.setValue("RDSTaggedClustersStopSSMDocument", "Name", "Scheduler-StopTaggedRDSClusters-" + props["solutionVersion"])
        mappings.setValue("SchedulerExecutionRole", "Name", "Scheduler-AutomationExecutionRole")
        mappings.setValue("SchedulerEventBusName", "Name", "scheduler-event-bus")

        let accountPrincipal = new iam.ArnPrincipal(cdk.Fn.sub('arn:${AWS::Partition}:iam::${accountId}:root', {
            accountId: instanceSchedulerAccount.valueAsString
        }));
        let servicePrincipal = new iam.ServicePrincipal('lambda.amazonaws.com')

        let principalPolicyStatement = new iam.PolicyStatement();
        principalPolicyStatement.addActions("sts:AssumeRole");
        principalPolicyStatement.effect = iam.Effect.ALLOW;

        let principals = new iam.CompositePrincipal(accountPrincipal, servicePrincipal, new iam.ServicePrincipal('ssm.amazonaws.com'));
        principals.addToPolicy(principalPolicyStatement);

        const ec2SchedulerCrossAccountRole = new iam.Role(this, 'EC2SchedulerCrossAccountRole', {
            roleName: cdk.Fn.sub('${Namespace}-${Name}-${AWS::Region}', {
                Name: mappings.findInMap("SchedulerExecutionRole", "Name")
            }),
            path: '/',
            assumedBy: principals,
            inlinePolicies: {
                'EC2InstanceSchedulerRemote': new iam.PolicyDocument({
                    statements: [
                        new iam.PolicyStatement({
                            actions: [
                                'rds:DeleteDBSnapshot',
                                'rds:DescribeDBSnapshots',
                                'rds:StopDBInstance'
                            ],
                            effect: iam.Effect.ALLOW,
                            resources: [
                                cdk.Fn.sub("arn:${AWS::Partition}:rds:*:${AWS::AccountId}:snapshot:*")
                            ]
                        }),
                        new iam.PolicyStatement({
                            actions: [
                                'rds:AddTagsToResource',
                                'rds:RemoveTagsFromResource',
                                'rds:DescribeDBSnapshots',
                                'rds:StartDBInstance',
                                'rds:StopDBInstance'
                            ],
                            effect: iam.Effect.ALLOW,
                            resources: [
                                cdk.Fn.sub("arn:${AWS::Partition}:rds:*:${AWS::AccountId}:db:*")
                            ]
                        }),
                        new iam.PolicyStatement({
                            actions: [
                                'rds:AddTagsToResource',
                                'rds:RemoveTagsFromResource',
                                'rds:StartDBCluster',
                                'rds:StopDBCluster'
                            ],
                            effect: iam.Effect.ALLOW,
                            resources: [
                                cdk.Fn.sub("arn:${AWS::Partition}:rds:*:${AWS::AccountId}:cluster:*")
                            ]
                        }),
                        new iam.PolicyStatement({
                            actions: [
                                'ec2:StartInstances',
                                'ec2:StopInstances',
                                'ec2:CreateTags',
                                'ec2:DeleteTags'
                            ],
                            effect: iam.Effect.ALLOW,
                            resources: [
                                cdk.Fn.sub("arn:${AWS::Partition}:ec2:*:${AWS::AccountId}:instance/*")
                            ]
                        }),
                        new iam.PolicyStatement({
                            actions: [
                                'rds:DescribeDBClusters',
                                'rds:DescribeDBInstances',
                                'ec2:DescribeInstances',
                                'ec2:DescribeInstanceStatus',
                                'ec2:DescribeRegions',
                                'ec2:DescribeTags',
                                'ssm:DescribeMaintenanceWindows',
                                'ssm:DescribeMaintenanceWindowExecutions',
                                'ssm:GetAutomationExecution',
                                'ssm:DescribeAutomationStepExecutions',
                                'tag:GetResources',
                                'tag:TagResources'
                            ],
                            effect: iam.Effect.ALLOW,
                            resources:[
                                '*'
                            ]
                        }),
                        new PolicyStatement({
                            actions: [
                                'kms:DescribeKey',
                                'kms:Encrypt',
                                'kms:Decrypt',
                                'kms:ReEncrypt*',
                                'kms:CreateGrant',
                                'kms:GenerateDataKey',
                                'kms:GenerateDataKeyWithoutPlaintext'
                            ],
                            effect: Effect.ALLOW,
                            resources:[
                                '*'
                            ]
                        }),                 
                        new iam.PolicyStatement({
                            actions: [
                              "ssm:StartAutomationExecution"
                            ],
                            resources: [
                                cdk.Fn.sub("arn:${AWS::Partition}:ssm:*:${AWS::AccountId}:automation-definition/")+ mappings.findInMap("Ec2StartSSMDocument","Name") + ":*",
                                cdk.Fn.sub("arn:${AWS::Partition}:ssm:*:${AWS::AccountId}:automation-definition/")+ mappings.findInMap("Ec2StopSSMDocument","Name") + ":*",
                                cdk.Fn.sub("arn:${AWS::Partition}:ssm:*:${AWS::AccountId}:automation-definition/")+ mappings.findInMap("RDSInstancesStartSSMDocument","Name") + ":*",
                                cdk.Fn.sub("arn:${AWS::Partition}:ssm:*:${AWS::AccountId}:automation-definition/")+ mappings.findInMap("RDSInstancesStopSSMDocument","Name") + ":*",
                                cdk.Fn.sub("arn:${AWS::Partition}:ssm:*:${AWS::AccountId}:automation-definition/")+ mappings.findInMap("RDSTaggedClustersStartSSMDocument","Name") + ":*",
                                cdk.Fn.sub("arn:${AWS::Partition}:ssm:*:${AWS::AccountId}:automation-definition/")+ mappings.findInMap("RDSTaggedClustersStopSSMDocument","Name") + ":*",
                                cdk.Fn.sub("arn:${AWS::Partition}:ssm:*::automation-definition/AWS-StartRdsInstance:*"),
                                cdk.Fn.sub("arn:${AWS::Partition}:ssm:*::automation-definition/AWS-StopRdsInstance:*"),
                                cdk.Fn.sub("arn:${AWS::Partition}:ssm:*::automation-definition/AWS-SetRequiredTags:*"),
                                cdk.Fn.sub("arn:${AWS::Partition}:ssm:*::automation-definition/AWS-StartStopAuroraCluster:*")
                            ],
                            effect: iam.Effect.ALLOW
                          })
                    ]
                })
            }
        })

        new iam.Policy(this, "Ec2ModifyInstanceAttrPolicy", {
            roles: [ec2SchedulerCrossAccountRole],
            statements: [
                new iam.PolicyStatement({
                    actions: [
                        'ec2:ModifyInstanceAttribute'
                    ],
                    effect: iam.Effect.ALLOW,
                    resources: [
                        cdk.Fn.sub("arn:${AWS::Partition}:ec2:*:${AWS::AccountId}:instance/*")
                    ]
                }),
                new iam.PolicyStatement({
                    actions:[
                        "iam:PassRole"
                    ],
                    effect: iam.Effect.ALLOW,
                    resources: [
                        ec2SchedulerCrossAccountRole.roleArn
                    ]
                })
            ]
        })

        // Event Rule to capture SSM Parameter Store creation by this stack
        // SSM parameter to invoke event rule
        const ssmParameterNamespace = new ssm.StringParameter(this, 'SSMParameterNamespace', {
            description: 'This parameter is for Instance Scheduler solution to support accounts in AWS Organizations.',
            stringValue: namespace.valueAsString,
            parameterName: "/instance-scheduler/do-not-delete-manually"
        })

        const ssmParameterNamespace_ref = ssmParameterNamespace.node.defaultChild as ssm.CfnParameter

        // Event Delivery Role and Policy necessary to migrate a sender-receiver relationship to Use AWS Organizations
        const schedulerEventDeliveryPolicy = new iam.Policy(this, "SchedulerEventDeliveryPolicy", {
            statements: [
                new iam.PolicyStatement({
                    actions:[
                        "events:PutEvents"
                    ],
                    effect: iam.Effect.ALLOW,
                    resources: [
                        cdk.Fn.sub(
                          'arn:${AWS::Partition}:events:${AWS::Region}:${InstanceSchedulerAccount}:event-bus/${Namespace}-${EventBusName}',
                          {
                              EventBusName: mappings.findInMap("SchedulerEventBusName", "Name")
                          })
                    ]
                })
            ]
        })

        const schedulerEventDeliveryRole = new iam.Role(this,
          "SchedulerEventDeliveryRole",
          {
            description: "Event Role to add the permissions necessary to migrate a sender-receiver relationship to Use AWS Organizations",
            assumedBy: new iam.ServicePrincipal('events.amazonaws.com'),
        })

        schedulerEventDeliveryRole.attachInlinePolicy(schedulerEventDeliveryPolicy)

        const parameterStoreEventRule = new events.CfnRule(this, 'scheduler-ssm-parameter-store-event', {
            description: "Event rule to invoke Instance Scheduler lambda function to store spoke account id in configuration.",
            state: 'ENABLED',
            targets: [{
                arn: cdk.Fn.sub(
                  'arn:${AWS::Partition}:events:${AWS::Region}:${InstanceSchedulerAccount}:event-bus/${Namespace}-${EventBusName}',
                  {
                      EventBusName: mappings.findInMap("SchedulerEventBusName", "Name")
                  }),
                id: 'Spoke-SSM-Parameter-Event',
                roleArn: schedulerEventDeliveryRole.roleArn
            }],
            eventPattern: {
                "account": [
                    this.account
                ],
                "source": [
                    "aws.ssm"
                ],
                "detail-type": [
                    "Parameter Store Change"
                ],
                "detail": {
                    "name": [
                        "/instance-scheduler/do-not-delete-manually"
                    ],
                    "operation": [
                        "Create",
                        "Delete"
                    ],
                    "type": [
                        "String"
                    ]
                }
            }
        })

        // wait for the events rule to be created before creating the SSM parameter
        ssmParameterNamespace_ref.addDependsOn(parameterStoreEventRule)

        // add condition to skip creation of these resources if deployed in hub account - Event Bus in the same account can not be used as target
        const schedulerEventDeliveryRole_ref = schedulerEventDeliveryRole.node.findChild('Resource') as iam.CfnRole
        const schedulerEventDeliveryPolicy_ref = schedulerEventDeliveryPolicy.node.findChild('Resource') as iam.CfnPolicy
        schedulerEventDeliveryPolicy_ref.cfnOptions.condition = isUsingOrganizationAndNotHubAccount
        schedulerEventDeliveryRole_ref.cfnOptions.condition = isUsingOrganizationAndNotHubAccount
        parameterStoreEventRule.cfnOptions.condition = isUsingOrganizationAndNotHubAccount
        ssmParameterNamespace_ref.cfnOptions.condition = isUsingOrganizationAndNotHubAccount

        //CFN Output
        new cdk.CfnOutput(this, 'CrossAccountRole', {
            value: ec2SchedulerCrossAccountRole.roleArn,
            description: 'Arn for cross account role for Instance scheduler, add this arn to the list of crossaccount roles (CrossAccountRoles) parameter of the Instance Scheduler template.'
        })

        const ec2SchedulerCrossAccountRole_cfn_ref = ec2SchedulerCrossAccountRole.node.defaultChild as iam.CfnRole
        ec2SchedulerCrossAccountRole_cfn_ref.overrideLogicalId('EC2SchedulerCrossAccountRole')
        ec2SchedulerCrossAccountRole_cfn_ref.cfnOptions.metadata = {
            "cfn_nag": {
                "rules_to_suppress": [
                    {
                        "id": "W11",
                        "reason": "All policies have been scoped to be as restrictive as possible. This solution needs to access ec2/rds resources across all regions."
                    },
                    {
                        "id": "W28",
                        "reason": "The role name is defined to allow cross account access from the hub account."
                    },
                    {
                        "id": "W76",
                        "reason": "All policies have been scoped to be as restrictive as possible. This solution needs to access ec2/rds resources across all regions."
                    }
                ]
            }
        }

        const stack = cdk.Stack.of(this)

        stack.templateOptions.metadata =
        {
            "AWS::CloudFormation::Interface": {
                "ParameterGroups": [
                    {
                        "Label": {"default": "Namespace Configuration"},
                        "Parameters": ["Namespace"]
                    },
                    {
                        "Label": { "default": "Instance Scheduler Hub Account Configuration"},
                        "Parameters": ["InstanceSchedulerAccount", "UsingAWSOrganizations"]
                    }],
                "ParameterLabels": {
                    "Namespace": {
                        "default": "Provide the same unique namespace value defined in the hub stack.",
                    },
                    "InstanceSchedulerAccount": {
                        "default": "Instance Scheduler Hub Account ID"
                    },
                    "UsingAWSOrganizations": {
                        "default": "Set this value to match hub stack CloudFormation parameter."
                    },
                }
            }
        }
        stack.templateOptions.templateFormatVersion = '2010-09-09'
    }
}