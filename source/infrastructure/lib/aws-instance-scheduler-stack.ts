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
import {Aws, RemovalPolicy} from 'aws-cdk-lib';
import * as kms from 'aws-cdk-lib/aws-kms';
import * as iam from 'aws-cdk-lib/aws-iam';
import {ArnPrincipal, Effect, PolicyStatement} from 'aws-cdk-lib/aws-iam';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as sns from 'aws-cdk-lib/aws-sns';
import * as events from 'aws-cdk-lib/aws-events';
import {Construct} from "constructs";
import {LambdaFunction} from "aws-cdk-lib/aws-events-targets";
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import {SUPPORTED_TIME_ZONES} from "./time-zones";
import { AppRegistryForInstanceScheduler } from './app-registry';
import {NagSuppressions} from "cdk-nag";
import {CoreScheduler} from "./core-scheduler";


export interface AwsInstanceSchedulerStackProps extends cdk.StackProps {
  readonly description: string,
  readonly solutionId: string,
  readonly solutionTradeMarkName: string,
  readonly solutionProvider: string,
  readonly solutionName: string,
  readonly solutionVersion: string,
  readonly appregApplicationName: string,
  readonly appregSolutionName: string,
}

/*
* AWS instance scheduler stack, utilizes two cdk constructs, aws-lambda-dynamodb and aws-events-rule-lambda.
* The stack has three dynamoDB tables defined for storing the state, configuration and maintenance information.
* The stack also includes one lambda, which is scheduled using an AWS CloudWatch Event Rule.
* The stack also includes a cloudwatch log group for the entire solution, encryption key, encryption key alias and SNS topic,
* and the necessary AWS IAM Policies and IAM Roles. For more information on the architecture, refer to the documentation at
* https://aws.amazon.com/solutions/implementations/instance-scheduler/?did=sl_card&trk=sl_card
*/
export class AwsInstanceSchedulerStack extends cdk.Stack {

  constructor(scope: Construct, id: string, props: AwsInstanceSchedulerStackProps) {
    super(scope, id, props);

    //Start CFN Parameters for instance scheduler.

    const schedulingActive = new cdk.CfnParameter(this, 'SchedulingActive', {
      description: 'Activate or deactivate scheduling.',
      type: "String",
      allowedValues: ["Yes", "No"],
      default: "Yes"
    });

    const scheduledServices = new cdk.CfnParameter(this, 'ScheduledServices', {
      description: 'Scheduled Services.',
      type: "String",
      allowedValues: ["EC2", "RDS", "Both"],
      default: "EC2"
    });

    const scheduleRdsClusters = new cdk.CfnParameter(this, 'ScheduleRdsClusters', {
      description: 'Enable scheduling of Aurora clusters for RDS Service.',
      type: "String",
      allowedValues: ["Yes", "No"],
      default: "No"
    });

    const createRdsSnapshot = new cdk.CfnParameter(this, 'CreateRdsSnapshot', {
      description: 'Create snapshot before stopping RDS instances (does not apply to Aurora Clusters).',
      type: "String",
      allowedValues: ["Yes", "No"],
      default: "No"
    });

    const memorySize = new cdk.CfnParameter(this, 'MemorySize', {
      description: 'Size of the Lambda function running the scheduler, increase size when processing large numbers of instances.',
      type: "Number",
      allowedValues: ["128", "384", "512", "640", "768", "896", "1024", "1152", "1280", "1408", "1536"],
      default: 128
    });

    const useCloudWatchMetrics = new cdk.CfnParameter(this, 'UseCloudWatchMetrics', {
      description: 'Collect instance scheduling data using CloudWatch metrics.',
      type: "String",
      allowedValues: ["Yes", "No"],
      default: "No"
    });

    const logRetention = new cdk.CfnParameter(this, 'LogRetentionDays', {
      description: 'Retention days for scheduler logs.',
      type: "Number",
      allowedValues: ["1", "3", "5", "7", "14", "14", "30", "60", "90", "120", "150", "180", "365", "400", "545", "731", "1827", "3653"],
      default: 30
    });

    const trace = new cdk.CfnParameter(this, 'Trace', {
      description: 'Enable logging of detailed information in CloudWatch logs.',
      type: 'String',
      allowedValues: ["Yes", "No"],
      default: "No"
    });
    
    const enableSSMMaintenanceWindows = new cdk.CfnParameter(this, 'EnableSSMMaintenanceWindows', {
      description: 'Enable the solution to load SSM Maintenance Windows, so that they can be used for EC2 instance Scheduling.',
      type: 'String',
      allowedValues: ["Yes", "No"],
      default: "No"
    });

    const tagName = new cdk.CfnParameter(this, 'TagName', {
      description: 'Name of tag to use for associating instance schedule schemas with service instances.',
      type: 'String',
      default: "Schedule",
      minLength: 1,
      maxLength: 127
    });

    const defaultTimezone = new cdk.CfnParameter(this, 'DefaultTimezone', {
      description: 'Choose the default Time Zone. Default is \'UTC\'.',
      type: 'String',
      default: 'UTC',
      allowedValues: SUPPORTED_TIME_ZONES
    })

    const regions = new cdk.CfnParameter(this, 'Regions', {
      type: 'CommaDelimitedList',
      description: 'List of regions in which instances are scheduled, leave blank for current region only.',
      default: ''
    })

    const crossAccountRoles = new cdk.CfnParameter(this, 'CrossAccountRoles', {
      type: 'CommaDelimitedList',
      description: 'Comma separated list of ARN\'s for cross account access roles. These roles must be created in all checked accounts the scheduler to start and stop instances.',
      default: ''
    })

    const startedTags = new cdk.CfnParameter(this, 'StartedTags', {
      type: 'String',
      description: 'Comma separated list of tagname and values on the formt name=value,name=value,.. that are set on started instances',
      default: ''
    })

    const stoppedTags = new cdk.CfnParameter(this, 'StoppedTags', {
      type: 'String',
      description: 'Comma separated list of tagname and values on the formt name=value,name=value,.. that are set on stopped instances',
      default: ''
    })

    const schedulerFrequency = new cdk.CfnParameter(this, 'SchedulerFrequency', {
      type: 'String',
      description: 'Scheduler running frequency in minutes.',
      allowedValues: [
        "1",
        "2",
        "5",
        "10",
        "15",
        "30",
        "60"
      ],
      default: "5"
    })

    const scheduleLambdaAccount = new cdk.CfnParameter(this, 'ScheduleLambdaAccount', {
      type: "String",
      allowedValues: ["Yes", "No"],
      default: "Yes",
      description: "Schedule instances in this account."
    })

    //End CFN parameters for instance scheduler.

    //Start Mappings for instance scheduler. 

    const mappings = new cdk.CfnMapping(this, "mappings")
    mappings.setValue("TrueFalse", "Yes", "True")
    mappings.setValue("TrueFalse", "No", "False")
    mappings.setValue("EnabledDisabled", "Yes", "ENABLED")
    mappings.setValue("EnabledDisabled", "No", "DISABLED")
    mappings.setValue("Services", "EC2", "ec2")
    mappings.setValue("Services", "RDS", "rds")
    mappings.setValue("Services", "Both", "ec2,rds")
    mappings.setValue("Timeouts", "1", "cron(0/1 * * * ? *)")
    mappings.setValue("Timeouts", "2", "cron(0/2 * * * ? *)")
    mappings.setValue("Timeouts", "5", "cron(0/5 * * * ? *)")
    mappings.setValue("Timeouts", "10", "cron(0/10 * * * ? *)")
    mappings.setValue("Timeouts", "15", "cron(0/15 * * * ? *)")
    mappings.setValue("Timeouts", "30", "cron(0/30 * * * ? *)")
    mappings.setValue("Timeouts", "60", "cron(0 0/1 * * ? *)")
    mappings.setValue("Settings", "MetricsUrl", "https://metrics.awssolutionsbuilder.com/generic")
    mappings.setValue("Settings", "MetricsSolutionId", "S00030")

    const send = new cdk.CfnMapping(this, 'Send')
    send.setValue('AnonymousUsage', 'Data', 'Yes')
    send.setValue('ParameterKey', 'UniqueId', `/Solutions/${props.solutionName}/UUID/`)

    //End Mappings for instance scheduler.


    new AppRegistryForInstanceScheduler(this, "AppRegistryForInstanceScheduler", {
      solutionId: props.solutionId,
      solutionName: props.solutionName,
      solutionVersion: props.solutionVersion,
      appregSolutionName: props.appregSolutionName,
      appregAppName: props.appregApplicationName
    })

    /*
    * Instance Scheduler solutions log group reference.
    */
    const schedulerLogGroup = new logs.LogGroup(this, 'SchedulerLogGroup', {
      logGroupName: Aws.STACK_NAME + '-logs',
      removalPolicy: RemovalPolicy.DESTROY
    });

    const schedulerLogGroup_ref = schedulerLogGroup.node.defaultChild as logs.CfnLogGroup
    schedulerLogGroup_ref.addPropertyOverride('RetentionInDays', logRetention.valueAsNumber)
    schedulerLogGroup_ref.cfnOptions.metadata = {
      "cfn_nag": {
        "rules_to_suppress": [
          {
            "id": "W84",
            "reason": "CloudWatch log groups only have transactional data from the Lambda function, this template has to be supported in gov cloud which doesn't yet have the feature to provide kms key id to cloudwatch log group."
          }
        ]
      }
    }

    //Start scheduler role reference and related references of principle, policy statement, and policy document.
    const compositePrincipal = new iam.CompositePrincipal(new iam.ServicePrincipal('events.amazonaws.com'), new iam.ServicePrincipal('lambda.amazonaws.com'))

    const schedulerRole = new iam.Role(this, "SchedulerRole", {
      assumedBy: compositePrincipal,
      path: '/'
    })
    //End scheduler role reference

    //Start instance scheduler encryption key and encryption key alias.
    const instanceSchedulerEncryptionKey = new kms.Key(this, "InstanceSchedulerEncryptionKey", {
      description: 'Key for SNS',
      enabled: true,
      enableKeyRotation: true,
      policy: new iam.PolicyDocument({
        statements: [
          new iam.PolicyStatement({
            actions: ["kms:*"],
            effect: Effect.ALLOW,
            resources: ['*'],
            principals: [new ArnPrincipal("arn:" + this.partition + ":iam::" + this.account + ":root")],
            sid: 'default'
          }),
          new iam.PolicyStatement({
            sid: 'Allows use of key',
            effect: Effect.ALLOW,
            actions: [
              'kms:GenerateDataKey*',
              'kms:Decrypt'
            ],
            resources: ['*'],
            principals: [new ArnPrincipal(schedulerRole.roleArn)]
          })
        ]
      }),
      removalPolicy: RemovalPolicy.DESTROY
    })

    const keyAlias = new kms.Alias(this, "InstanceSchedulerEncryptionKeyAlias", {
      aliasName: `alias/${Aws.STACK_NAME}-instance-scheduler-encryption-key`,
      targetKey: instanceSchedulerEncryptionKey
    })
    //End instance scheduler encryption key and encryption key alias.

    /*
    * Instance scheduler SNS Topic reference. 
    */
    const snsTopic = new sns.Topic(this, 'InstanceSchedulerSnsTopic', {
      masterKey: instanceSchedulerEncryptionKey
    });

    //instance scheduler core scheduler construct reference.
    const coreScheduler = new CoreScheduler(this,  {
      solutionVersion: props.solutionVersion,
      solutionTradeMarkName: props.solutionTradeMarkName,
      memorySize: memorySize.valueAsNumber,
      schedulerRole: schedulerRole,
      kmsEncryptionKey: instanceSchedulerEncryptionKey,
      environment: {
        SCHEDULER_FREQUENCY: schedulerFrequency.valueAsString,
        TAG_NAME: tagName.valueAsString,
        LOG_GROUP: schedulerLogGroup.logGroupName,
        ACCOUNT: this.account,
        ISSUES_TOPIC_ARN: snsTopic.topicArn,
        STACK_NAME: Aws.STACK_NAME,
        SEND_METRICS: mappings.findInMap('TrueFalse', send.findInMap('AnonymousUsage', 'Data')),
        SOLUTION_ID: mappings.findInMap('Settings', 'MetricsSolutionId'),
        TRACE: mappings.findInMap('TrueFalse', trace.valueAsString),
        ENABLE_SSM_MAINTENANCE_WINDOWS: mappings.findInMap('TrueFalse', enableSSMMaintenanceWindows.valueAsString),
        USER_AGENT: 'InstanceScheduler-' + Aws.STACK_NAME + '-' + props.solutionVersion,
        USER_AGENT_EXTRA: `AwsSolution/${props.solutionId}/${props.solutionVersion}`,
        METRICS_URL: mappings.findInMap('Settings', 'MetricsUrl'),
        STACK_ID: `${cdk.Aws.STACK_ID}`,
        UUID_KEY: send.findInMap('ParameterKey', 'UniqueId'),
        START_EC2_BATCH_SIZE: '5'
      }
    })

    //PolicyStatement for SSM Get and Put Parameters
    const ssmParameterPolicyStatement = new PolicyStatement({
      actions: [
        "ssm:PutParameter",
        "ssm:GetParameter",
      ],
      effect: Effect.ALLOW,
      resources: [
        cdk.Fn.sub("arn:${AWS::Partition}:ssm:${AWS::Region}:${AWS::AccountId}:parameter/Solutions/aws-instance-scheduler/UUID/*")
      ]
    })
    coreScheduler.lambdaFunction.addToRolePolicy(ssmParameterPolicyStatement)
    //End instance scheduler database policy statement for lambda.


    const schedulerRule = new events.Rule(this, 'SchedulerEventRule', {
      description: 'Instance Scheduler - Rule to trigger instance for scheduler function version ' + props["solutionVersion"],
      schedule: events.Schedule.expression(mappings.findInMap('Timeouts', schedulerFrequency.valueAsString))
    })

    schedulerRule.addTarget(new LambdaFunction(coreScheduler.lambdaFunction))

    const eventRule_cfn_ref = schedulerRule.node.defaultChild as events.CfnRule
    eventRule_cfn_ref.addPropertyOverride('State', mappings.findInMap('EnabledDisabled', schedulingActive.valueAsString));

    //End instance scheduler aws-event-lambda construct reference.


    /*
    * Instance scheduler custom resource reference.
    */
    let customService = new cdk.CustomResource(this, 'ServiceSetup', {
      serviceToken: coreScheduler.lambdaFunction.functionArn,
      resourceType: 'Custom::ServiceSetup',
      properties: {
        timeout: 120,
        config_table: (coreScheduler.configTable.node.defaultChild as dynamodb.CfnTable).ref,
        tagname: tagName,
        default_timezone: defaultTimezone,
        use_metrics: mappings.findInMap('TrueFalse', useCloudWatchMetrics.valueAsString),
        scheduled_services: cdk.Fn.split(",", mappings.findInMap('Services', scheduledServices.valueAsString)),
        schedule_clusters: mappings.findInMap('TrueFalse', scheduleRdsClusters.valueAsString),
        create_rds_snapshot: mappings.findInMap('TrueFalse', createRdsSnapshot.valueAsString),
        regions: regions,
        cross_account_roles: crossAccountRoles,
        schedule_lambda_account: mappings.findInMap('TrueFalse', scheduleLambdaAccount.valueAsString),
        trace: mappings.findInMap('TrueFalse', trace.valueAsString),
        enable_SSM_maintenance_windows: mappings.findInMap('TrueFalse', enableSSMMaintenanceWindows.valueAsString),
        log_retention_days: logRetention.valueAsNumber,
        started_tags: startedTags.valueAsString,
        stopped_tags: stoppedTags.valueAsString,
        stack_version: props.solutionVersion
      }
    })

    const customServiceCfn = customService.node.defaultChild as cdk.CfnCustomResource
    customServiceCfn.addDependency(schedulerLogGroup_ref)

    //Instance scheduler Cloudformation Output references.
    new cdk.CfnOutput(this, 'AccountId', {
      value: this.account,
      description: 'Account to give access to when creating cross-account access role for cross account scenario '
    })

    new cdk.CfnOutput(this, 'ConfigurationTable', {
      value: (coreScheduler.configTable.node.defaultChild as dynamodb.CfnTable).attrArn,
      description: 'Name of the DynamoDB configuration table'
    })

    new cdk.CfnOutput(this, 'IssueSnsTopicArn', {
      value: snsTopic.topicArn,
      description: 'Topic to subscribe to for notifications of errors and warnings'
    })

    new cdk.CfnOutput(this, 'SchedulerRoleArn', {
      value: schedulerRole.roleArn,
      description: 'Role for the instance scheduler lambda function'
    })

    new cdk.CfnOutput(this, 'ServiceInstanceScheduleServiceToken', {
      value: coreScheduler.lambdaFunction.functionArn,
      description: 'Arn to use as ServiceToken property for custom resource type Custom::ServiceInstanceSchedule'
    })

    //Instance scheduler ec2 policy statement, policy documents and role references.
    const ec2PolicyStatementForLogs = new PolicyStatement({
      actions: [
        'logs:CreateLogGroup',
        'logs:CreateLogStream',
        'logs:PutLogEvents',
        'logs:PutRetentionPolicy'],
      resources: [
        cdk.Fn.sub("arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:log-group:/aws/lambda/*"),
        schedulerLogGroup.logGroupArn
      ],
      effect: Effect.ALLOW
    })

    const ec2PolicyStatementforMisc = new PolicyStatement({
      actions: [
        'logs:DescribeLogStreams',
        'rds:DescribeDBClusters',
        'rds:DescribeDBInstances',
        'ec2:DescribeInstances',
        'ec2:DescribeRegions',
        'cloudwatch:PutMetricData',
        'ssm:DescribeMaintenanceWindows',
        'tag:GetResources'],
      effect: Effect.ALLOW,
      resources: ['*']
    })

    const ec2PolicyAssumeRoleStatement = new PolicyStatement({
      actions: ['sts:AssumeRole'],
      resources: [cdk.Fn.sub("arn:${AWS::Partition}:iam::*:role/*EC2SchedulerCross*")],
      effect: Effect.ALLOW
    })

    const ec2PolicySSMStatement = new PolicyStatement({
      actions: [
        'ssm:GetParameter',
        'ssm:GetParameters'
      ],
      resources: [cdk.Fn.sub("arn:${AWS::Partition}:ssm:*:${AWS::AccountId}:parameter/*")],
      effect: Effect.ALLOW
    })

    const ec2Permissions = new iam.Policy(this, "Ec2Permissions", {
      statements: [
        new PolicyStatement({
          actions: [
            'ec2:ModifyInstanceAttribute',
          ],
          effect: Effect.ALLOW,
          resources: [
            cdk.Fn.sub("arn:${AWS::Partition}:ec2:*:${AWS::AccountId}:instance/*")
          ]
        }),
        ec2PolicyAssumeRoleStatement
      ],
      roles: [schedulerRole]
    })

    NagSuppressions.addResourceSuppressions(ec2Permissions, [{
      id: "AwsSolutions-IAM5",
      reason: "This Lambda function needs to be able to modify ec2 instances for scheduling purposes."
    }])

    const ec2DynamoDBPolicy = new iam.Policy(this, "EC2DynamoDBPolicy", {
      roles: [schedulerRole],
      policyName: 'EC2DynamoDBPolicy',
      statements: [
        ec2PolicySSMStatement, 
        ec2PolicyStatementforMisc, 
        ec2PolicyStatementForLogs
      ]
    })

    //Instance scheduler, scheduling policy statement, policy documents and role references.
    const schedulerPolicyStatement1 = new PolicyStatement({
      actions: [
        'rds:DeleteDBSnapshot',
        'rds:DescribeDBSnapshots',
        'rds:StopDBInstance'],
      effect: Effect.ALLOW,
      resources: [cdk.Fn.sub("arn:${AWS::Partition}:rds:*:${AWS::AccountId}:snapshot:*")]
    })

    const schedulerPolicyStatement2 = new PolicyStatement({
      actions: [
        'rds:AddTagsToResource',
        'rds:RemoveTagsFromResource',
        'rds:DescribeDBSnapshots',
        'rds:StartDBInstance',
        'rds:StopDBInstance'],
      effect: Effect.ALLOW,
      resources: [cdk.Fn.sub("arn:${AWS::Partition}:rds:*:${AWS::AccountId}:db:*")]
    })

    const schedulerPolicyStatement3 = new PolicyStatement({
      actions: [
        'ec2:StartInstances',
        'ec2:StopInstances',
        'ec2:CreateTags',
        'ec2:DeleteTags'],
      effect: Effect.ALLOW,
      resources: [cdk.Fn.sub("arn:${AWS::Partition}:ec2:*:${AWS::AccountId}:instance/*")]
    })

    const schedulerPolicyStatement4 = new PolicyStatement({
      actions: ['sns:Publish'],
      effect: Effect.ALLOW,
      resources: [snsTopic.topicArn]
    })

    const schedulerPolicyStatement5 = new PolicyStatement({
      actions: ['lambda:InvokeFunction'],
      effect: Effect.ALLOW,
      resources: [cdk.Fn.sub("arn:${AWS::Partition}:lambda:${AWS::Region}:${AWS::AccountId}:function:${AWS::StackName}-InstanceSchedulerMain")]
    })

    const schedulerPolicyStatement6 = new PolicyStatement({
      actions: [
        'kms:GenerateDataKey*',
        'kms:Decrypt'
      ],
      effect: Effect.ALLOW,
      resources: [instanceSchedulerEncryptionKey.keyArn]
    })

    const schedulerPolicyStatement7 = new PolicyStatement({
      actions: [
        'rds:AddTagsToResource',
        'rds:RemoveTagsFromResource',
        'rds:StartDBCluster',
        'rds:StopDBCluster'
      ],
      effect: Effect.ALLOW,
      resources: [cdk.Fn.sub("arn:${AWS::Partition}:rds:*:${AWS::AccountId}:cluster:*")]
    })

    
    const schedulerPolicy = new iam.Policy(this, "SchedulerPolicy", {
      roles: [schedulerRole],
      policyName: 'SchedulerPolicy',
      statements: [schedulerPolicyStatement2, schedulerPolicyStatement3, schedulerPolicyStatement4, schedulerPolicyStatement5, schedulerPolicyStatement6]
    })
    NagSuppressions.addResourceSuppressions(schedulerPolicy, [{
      id: "AwsSolutions-IAM5",
      reason: "All policies have been scoped to be as restrictive as possible. This solution needs to access ec2/rds resources across all regions."
    }])


    const schedulerRDSPolicy  = new iam.Policy(this, "SchedulerRDSPolicy", {
      roles:[schedulerRole],
      statements:[
        schedulerPolicyStatement1,
        schedulerPolicyStatement7
      ]
    })
    NagSuppressions.addResourceSuppressions(schedulerRDSPolicy, [{
      id: "AwsSolutions-IAM5",
      reason: "All policies have been scoped to be as restrictive as possible. This solution needs to access ec2/rds resources across all regions."
    }])

    //Adding the EC2 and scheduling policy dependencies to the lambda. 
    const lambdaFunction = coreScheduler.lambdaFunction.node.defaultChild as lambda.CfnFunction
    lambdaFunction.addDependency(ec2DynamoDBPolicy.node.defaultChild as iam.CfnPolicy)
    lambdaFunction.addDependency(ec2Permissions.node.defaultChild as iam.CfnPolicy)
    lambdaFunction.addDependency(schedulerPolicy.node.defaultChild as iam.CfnPolicy)
    lambdaFunction.addDependency(schedulerRDSPolicy.node.defaultChild as iam.CfnPolicy)
    lambdaFunction.cfnOptions.metadata = {
      "cfn_nag": {
        "rules_to_suppress": [
          {
            "id": "W89",
            "reason": "This Lambda function does not need to access any resource provisioned within a VPC."
          },
          {
            "id": "W58",
            "reason": "This Lambda function has permission provided to write to CloudWatch logs using the iam roles."
          },
          {
            "id": "W92",
            "reason": "Lambda function is only used by the event rule periodically, concurrent calls are very limited."
          }
        ]
      }
    }

    //Cloud Formation cfn references for ensuring the resource names are similar to earlier releases, and additional metadata for the cfn nag rules.
    const instanceSchedulerEncryptionKey_cfn_ref = instanceSchedulerEncryptionKey.node.defaultChild as kms.CfnKey
    instanceSchedulerEncryptionKey_cfn_ref.overrideLogicalId('InstanceSchedulerEncryptionKey')

    const keyAlias_cfn_ref = keyAlias.node.defaultChild as kms.CfnAlias
    keyAlias_cfn_ref.overrideLogicalId('InstanceSchedulerEncryptionKeyAlias')

    const ec2DynamoDBPolicy_cfn_ref = ec2DynamoDBPolicy.node.defaultChild as iam.CfnPolicy
    ec2DynamoDBPolicy_cfn_ref.overrideLogicalId('EC2DynamoDBPolicy')

    ec2DynamoDBPolicy_cfn_ref.cfnOptions.metadata = {
      "cfn_nag": {
        "rules_to_suppress": [
          {
            "id": "W12",
            "reason": "All policies have been scoped to be as restrictive as possible. This solution needs to access ec2/rds resources across all regions."
          }
        ]
      }
    }

    NagSuppressions.addResourceSuppressions(ec2DynamoDBPolicy_cfn_ref, [{
      id: "AwsSolutions-IAM5",
      reason: "All policies have been scoped to be as restrictive as possible. This solution needs to access ec2/rds resources across all regions."
    }])

    const schedulerPolicy_cfn_Ref = schedulerPolicy.node.defaultChild as iam.CfnPolicy
    schedulerPolicy_cfn_Ref.overrideLogicalId('SchedulerPolicy')

    const schedulerRole_cfn_ref = schedulerRole.node.defaultChild as iam.CfnRole
    schedulerRole_cfn_ref.overrideLogicalId('SchedulerRole')

    schedulerLogGroup_ref.overrideLogicalId('SchedulerLogGroup')

    const snsTopic_cfn_ref = snsTopic.node.defaultChild as sns.CfnTopic
    snsTopic_cfn_ref.overrideLogicalId('InstanceSchedulerSnsTopic')

    lambdaFunction.overrideLogicalId('Main')

    const rule_cfn_ref = schedulerRule.node.defaultChild as events.CfnRule
    rule_cfn_ref.overrideLogicalId('SchedulerRule')

    customServiceCfn.overrideLogicalId('SchedulerConfigHelper')

    const stack = cdk.Stack.of(this);

    stack.templateOptions.metadata =
    {
      "AWS::CloudFormation::Interface": {
        "ParameterGroups": [
          {
            "Label": {
              "default": "Scheduler (version " + props['solutionVersion'] + ")"
            },
            "Parameters": [
              "TagName",
              "ScheduledServices",
              "ScheduleRdsClusters",
              "CreateRdsSnapshot",
              "SchedulingActive",
              "Regions",
              "DefaultTimezone",
              "CrossAccountRoles",
              "ScheduleLambdaAccount",
              "SchedulerFrequency",
              "MemorySize"
            ]
          },
          {
            "Label": {
              "default": "Options"
            },
            "Parameters": [
              "UseCloudWatchMetrics",
              "Trace",
              "EnableSSMMaintenanceWindows"
            ]
          },
          {
            "Label": {
              "default": "Other parameters"
            },
            "Parameters": [
              "LogRetentionDays",
              "StartedTags",
              "StoppedTags"
            ]
          }
        ],
        "ParameterLabels": {
          "LogRetentionDays": {
            "default": "Log retention days"
          },
          "StartedTags": {
            "default": "Started tags"
          },
          "StoppedTags": {
            "default": "Stopped tags"
          },
          "SchedulingActive": {
            "default": "Scheduling enabled"
          },
          "CrossAccountRoles": {
            "default": "Cross-account roles"
          },
          "ScheduleLambdaAccount": {
            "default": "This account"
          },
          "UseCloudWatchMetrics": {
            "default": "Enable CloudWatch Metrics"
          },
          "Trace": {
            "default": "Enable CloudWatch Logs"
          },
          "EnableSSMMaintenanceWindows": {
            "default": "Enable SSM Maintenance windows"
          },
          "TagName": {
            "default": "Instance Scheduler tag name"
          },
          "ScheduledServices": {
            "default": "Service(s) to schedule"
          },
          "ScheduleRdsClusters": {
            "default": "Schedule Aurora Clusters"
          },
          "CreateRdsSnapshot": {
            "default": "Create RDS instance snapshot"
          },
          "DefaultTimezone": {
            "default": "Default time zone"
          },
          "SchedulerFrequency": {
            "default": "Frequency"
          },
          "Regions": {
            "default": "Region(s)"
          },
          "MemorySize": {
            "default": "Memory size"
          }
        }
      }
    }
    stack.templateOptions.templateFormatVersion = "2010-09-09"

  }
}
