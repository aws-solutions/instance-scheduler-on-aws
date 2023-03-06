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

import * as cdk from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import { ArnPrincipal, CompositePrincipal, Effect, PolicyStatement } from "aws-cdk-lib/aws-iam";
import { Construct } from "constructs";
import { AppRegistryForInstanceScheduler } from './app-registry';
import {NagSuppressions} from "cdk-nag";

export interface AwsInstanceSchedulerRemoteStackProps extends cdk.StackProps {
    readonly description: string,
    readonly solutionId: string,
    readonly solutionTradeMarkName: string,
    readonly solutionProvider: string,
    readonly solutionName: string,
    readonly solutionVersion: string,
    readonly appregApplicationName: string,
    readonly appregSolutionName: string,
  }

export class AwsInstanceSchedulerRemoteStack extends cdk.Stack {

    constructor(scope: Construct, id: string, props: AwsInstanceSchedulerRemoteStackProps) {
        super(scope, id, props);

        //CFN Parameters
        const instanceSchedulerAccount = new cdk.CfnParameter(this, 'InstanceSchedulerAccount', {
            description: 'Account number of Instance Scheduler account to give access to manage EC2 and RDS  Instances in this account.',
            type: "String",
            allowedPattern: '(^[0-9]{12}$)',
            constraintDescription: 'Account number is a 12 digit number'
        });

        new AppRegistryForInstanceScheduler(this, "AppRegistryForInstanceScheduler", {
            solutionId: props.solutionId,
            solutionName: props.solutionName,
            solutionVersion: props.solutionVersion,
            appregSolutionName: props.appregSolutionName,
            appregAppName: props.appregApplicationName
          })

        let accountPrincipal = new ArnPrincipal(cdk.Fn.sub('arn:${AWS::Partition}:iam::${accountId}:root', {
            accountId: instanceSchedulerAccount.valueAsString
        }));
        let servicePrincipal = new iam.ServicePrincipal('lambda.amazonaws.com')

        let principalPolicyStatement = new PolicyStatement();
        principalPolicyStatement.addActions("sts:AssumeRole");
        principalPolicyStatement.effect = Effect.ALLOW;

        let principals = new CompositePrincipal(accountPrincipal, servicePrincipal);
        principals.addToPolicy(principalPolicyStatement);

        const ec2SchedulerCrossAccountRole = new iam.Role(this, 'EC2SchedulerCrossAccountRole', {
            path: '/',
            assumedBy: principals,
            inlinePolicies: {
                'EC2InstanceSchedulerRemote': new iam.PolicyDocument({
                    statements: [
                        new PolicyStatement({
                            actions: [
                                'rds:DeleteDBSnapshot',
                                'rds:DescribeDBSnapshots',
                                'rds:StopDBInstance'
                            ],
                            effect: Effect.ALLOW,
                            resources: [
                                cdk.Fn.sub("arn:${AWS::Partition}:rds:*:${AWS::AccountId}:snapshot:*")
                            ]
                        }),
                        new PolicyStatement({
                            actions: [
                                'rds:AddTagsToResource',
                                'rds:RemoveTagsFromResource',
                                'rds:DescribeDBSnapshots',
                                'rds:StartDBInstance',
                                'rds:StopDBInstance'
                            ],
                            effect: Effect.ALLOW,
                            resources: [
                                cdk.Fn.sub("arn:${AWS::Partition}:rds:*:${AWS::AccountId}:db:*")
                            ]
                        }),
                        new PolicyStatement({
                            actions: [
                                'rds:AddTagsToResource',
                                'rds:RemoveTagsFromResource',
                                'rds:StartDBCluster',
                                'rds:StopDBCluster'
                            ],
                            effect: Effect.ALLOW,
                            resources: [
                                cdk.Fn.sub("arn:${AWS::Partition}:rds:*:${AWS::AccountId}:cluster:*")
                            ]
                        }),
                        new PolicyStatement({
                            actions: [
                                'ec2:StartInstances',
                                'ec2:StopInstances',
                                'ec2:CreateTags',
                                'ec2:DeleteTags'
                            ],
                            effect: Effect.ALLOW,
                            resources: [
                                cdk.Fn.sub("arn:${AWS::Partition}:ec2:*:${AWS::AccountId}:instance/*")
                            ]
                        }),
                        new PolicyStatement({
                            actions: [
                                'rds:DescribeDBClusters',
                                'rds:DescribeDBInstances',
                                'ec2:DescribeInstances',
                                'ec2:DescribeRegions',
                                'ssm:DescribeMaintenanceWindows',
                                'ssm:DescribeMaintenanceWindowExecutions',
                                'tag:GetResources'
                            ],
                            effect: Effect.ALLOW,
                            resources:[
                                '*'
                            ]
                        })
                    ]
                })
            }
        })

        const ec2ModifyInstancePolicy = new iam.Policy(this, "Ec2ModifyInstanceAttrPolicy", {
            roles: [ec2SchedulerCrossAccountRole],
            statements: [
                new PolicyStatement({
                    actions: [
                        'ec2:ModifyInstanceAttribute'
                    ],
                    effect: Effect.ALLOW,
                    resources: [
                        cdk.Fn.sub("arn:${AWS::Partition}:ec2:*:${AWS::AccountId}:instance/*")
                    ]
                })
            ]
        })

        NagSuppressions.addResourceSuppressions(ec2ModifyInstancePolicy, [{
            id: "AwsSolutions-IAM5",
            reason: "All policies have been scoped to be as restrictive as possible. This solution needs to access ec2/rds resources across all regions."
        }])

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
                    }
                ]
            }
        }
        NagSuppressions.addResourceSuppressions(
          ec2SchedulerCrossAccountRole_cfn_ref,
          [{
              id: "AwsSolutions-IAM5",
              reason: "All policies have been scoped to be as restrictive as possible. This solution needs to access ec2/rds resources across all regions."
          }]
        )

        const stack = cdk.Stack.of(this)

        stack.templateOptions.metadata =
        {
            "AWS::CloudFormation::Interface": {
                "ParameterGroups": [{
                    "Label": {
                        "default": "Account"
                    },
                    "Parameters": [
                        "InstanceSchedulerAccount"
                    ]
                }],
                "ParameterLabels": {
                    "InstanceSchedulerAccount": {
                        "default": "Primary account"
                    }
                }
            }
        }
        stack.templateOptions.templateFormatVersion = '2010-09-09'
    }
}
