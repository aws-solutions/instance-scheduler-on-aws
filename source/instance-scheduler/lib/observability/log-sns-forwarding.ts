// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { Construct } from "constructs";
import { Topic } from "aws-cdk-lib/aws-sns";
import { KmsKeys } from "../helpers/kms";
import { overrideLogicalId } from "../cfn";
import { FunctionFactory } from "../lambda-functions/function-factory";
import { Role, ServicePrincipal, PolicyStatement, Effect } from "aws-cdk-lib/aws-iam";
import { Function as LambdaFunction } from "aws-cdk-lib/aws-lambda";
import { Duration, Stack } from "aws-cdk-lib";
import { FilterPattern, SubscriptionFilter } from "aws-cdk-lib/aws-logs";
import { ISLogGroups } from "./log-groups";
import { LambdaDestination } from "aws-cdk-lib/aws-logs-destinations";

export interface SnsLogSubscriberProps {
  readonly factory: FunctionFactory;
  readonly USER_AGENT_EXTRA: string;
}

export class SnsLogSubscriber extends Construct {
  readonly snsTopic: Topic;
  readonly logHandler: LambdaFunction;

  constructor(scope: Construct, id: string, props: SnsLogSubscriberProps) {
    super(scope, id);

    this.snsTopic = new Topic(scope, "InstanceSchedulerSnsTopic", {
      masterKey: KmsKeys.get(scope),
      enforceSSL: true,
    });
    overrideLogicalId(this.snsTopic, "InstanceSchedulerSnsTopic");

    const lambdaRole = new Role(scope, "SnsLogForwarderRole", {
      assumedBy: new ServicePrincipal("lambda.amazonaws.com"),
    });

    lambdaRole.addToPolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
        resources: [Stack.of(this).formatArn({ service: "logs", resource: "log-group:/aws/lambda/*" })],
      }),
    );

    this.logHandler = props.factory.createFunction(scope, "SnsLogForwarder", {
      environment: {
        USER_AGENT_EXTRA: props.USER_AGENT_EXTRA,
        SNS_NOTIFICATION_TOPIC: this.snsTopic.topicArn,
      },
      handler: "handle_log_event",
      index: "instance_scheduler/handler/log_forwarding.py",
      memorySize: 512,
      role: lambdaRole,
      timeout: Duration.seconds(30),
      description: "Forwards InstanceScheduler Error/Warning logs to SNS",
    });

    this.snsTopic.grantPublish(lambdaRole);

    new SubscriptionFilter(this, "AdminLogSubscription", {
      logGroup: ISLogGroups.adminLogGroup(this),
      destination: new LambdaDestination(this.logHandler),
      filterPattern: FilterPattern.any(
        FilterPattern.stringValue("$.level", "=", "ERROR"),
        FilterPattern.stringValue("$.level", "=", "WARNING"),
      ),
    });

    new SubscriptionFilter(this, "SchedulingLogSubscription", {
      logGroup: ISLogGroups.schedulingLogGroup(this),
      destination: new LambdaDestination(this.logHandler),
      filterPattern: FilterPattern.any(
        FilterPattern.stringValue("$.level", "=", "ERROR"),
        FilterPattern.stringValue("$.level", "=", "WARNING"),
      ),
    });
  }
}
