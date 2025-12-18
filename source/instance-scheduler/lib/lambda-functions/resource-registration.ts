// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { Construct } from "constructs";
import { EventBus, EventPattern, Rule } from "aws-cdk-lib/aws-events";
import * as targets from "aws-cdk-lib/aws-events-targets";
import { Aws, CfnCondition, CfnResource, CustomResource, Duration, Fn } from "aws-cdk-lib";
import { AnyPrincipal, Effect, PolicyStatement, Role, ServicePrincipal } from "aws-cdk-lib/aws-iam";
import { Queue, QueueEncryption } from "aws-cdk-lib/aws-sqs";
import { FunctionFactory } from "./function-factory";
import { NagSuppressions } from "cdk-nag";
import { ISLogGroups } from "../observability/log-groups";
import { Table } from "aws-cdk-lib/aws-dynamodb";
import { Function as LambdaFunction } from "aws-cdk-lib/aws-lambda";
import { addCfnGuardSuppression } from "../helpers/cfn-guard";
import { RegionEventRulesCustomResource } from "./region-event-rules";
import { TargetStack } from "../stack-types";
import { RegionRegistrationCustomResource } from "./region-registration";

interface ResourceRegistrationProps {
  readonly namespace: string;
  readonly scheduleTagKey: string;
  readonly factory: FunctionFactory;
  readonly organizationsMode: CfnCondition;
  readonly principals: string[]; //[orgId] if orgs mode enabled, list of accountIds otherwise
  readonly configTable: Table;
  readonly registryTable: Table;
  readonly stackId: string;
  readonly stackName: string;
  readonly USER_AGENT_EXTRA: string;
  readonly schedulerRoleName: string;
  readonly schedulingIntervalMinutes: number;
  readonly asgScheduledRulesPrefix: string;
  readonly asgMetadataTagKey: string;
  readonly solutionVersion: string;
  readonly regions: string[];
  readonly regionalEventBusName: string;
  readonly spokeRegistrationLambda: LambdaFunction;
  readonly spokeRegistrationLambdaRoleName: string;
  readonly globalEventBus: EventBus;
}

function registrationEventBusName(namespace: string) {
  return `${namespace}-RegistrationEvents`;
}

function taggingEventPattern(scheduleTagKey: string): EventPattern {
  return {
    source: ["aws.tag"],
    detail: {
      "changed-tag-keys": [scheduleTagKey],
    },
  };
}

function asgTaggingEventPattern(scheduleTagKey: string): EventPattern {
  return {
    source: ["aws.autoscaling"],
    detailType: ["AWS API Call via CloudTrail"],
    detail: {
      eventSource: ["autoscaling.amazonaws.com"],
      eventName: ["CreateOrUpdateTags", "DeleteTags"],
      requestParameters: {
        tags: {
          key: [scheduleTagKey],
        },
      },
    },
  };
}

export class HubResourceRegistration extends Construct {
  readonly registrationLambda: LambdaFunction;
  readonly regionalEventBusName: string;
  readonly regionRegistrationCfnResource: CfnResource;

  static roleName(namespace: string) {
    return `${namespace}-ResourceRegistrationHandler-Role`;
  }

  static registrationEventBusName(namespace: string) {
    return `${namespace}-RegistrationEvents`;
  }

  constructor(scope: Construct, id: string, props: ResourceRegistrationProps) {
    super(scope, id);

    const registrationEventsDLQ = new Queue(this, "RegistrationEventsDLQ", {
      encryption: QueueEncryption.SQS_MANAGED,
    });

    addCfnGuardSuppression(registrationEventsDLQ, ["SQS_QUEUE_KMS_MASTER_KEY_ID_RULE"]);

    const taggingEventBus = new EventBus(this, "RegistrationEvents", {
      eventBusName: registrationEventBusName(props.namespace),
      deadLetterQueue: registrationEventsDLQ,
    });
    // Add the resource policy with conditional statement
    taggingEventBus.addToResourcePolicy(
      new PolicyStatement({
        sid: "AllowCrossAccountEventBridgeAccess",
        effect: Effect.ALLOW,
        principals: [new AnyPrincipal()], //NOSONAR - the principals have to be from known accounts as defined in the conditions.
        actions: ["events:PutEvents"],
        resources: [taggingEventBus.eventBusArn],
        conditions: {
          StringEquals: Fn.conditionIf(
            props.organizationsMode.logicalId,
            {
              "aws:PrincipalOrgId": Fn.select(0, props.principals),
            },
            {
              "aws:SourceAccount": props.principals,
            },
          ),
        },
      }),
    );

    const regionEventRulesCustomResource = new RegionEventRulesCustomResource(this, "RegionEventRulesCustomResource", {
      hubAccountId: Aws.ACCOUNT_ID,
      namespace: props.namespace,
      factory: props.factory,
      scheduleTagKey: props.scheduleTagKey,
      USER_AGENT_EXTRA: props.USER_AGENT_EXTRA,
      taggingEventBusName: registrationEventBusName(props.namespace),
      version: props.solutionVersion,
      regionalEventBusName: props.regionalEventBusName,
    });

    const regionsCustomResource = new CustomResource(this, "CreateRegionalEventRules", {
      serviceToken: regionEventRulesCustomResource.regionalEventsCustomResourceLambda.functionArn,
      resourceType: "Custom::SetupRegionalEvents",
      properties: {
        regions: props.regions,
      },
    });
    const regionsCustomResourceCfnResource = regionsCustomResource.node.defaultChild as CfnResource;
    regionsCustomResourceCfnResource.addOverride("UpdateReplacePolicy", "Retain");

    this.regionalEventBusName = regionsCustomResource.getAtt("REGIONAL_BUS_NAME").toString();

    //lambda to handle events
    const registrationLambdaRole = new Role(this, "ResourceRegistrationLambdaRole", {
      roleName: HubResourceRegistration.roleName(props.namespace),
      assumedBy: new ServicePrincipal("lambda.amazonaws.com"),
    });
    addCfnGuardSuppression(registrationLambdaRole, ["CFN_NO_EXPLICIT_RESOURCE_NAMES"]);

    registrationLambdaRole.addToPolicy(
      //assume scheduler role in hub/spoke accounts
      new PolicyStatement({
        actions: ["sts:AssumeRole"],
        effect: Effect.ALLOW,
        resources: [`arn:${Aws.PARTITION}:iam::*:role/${props.schedulerRoleName}`],
      }),
    );

    this.registrationLambda = props.factory.createFunction(scope, "ResourceRegistrationLambda", {
      description: "Handles tag events for registration updates of managed resources",
      index: "instance_scheduler/handler/resource_registration_handler.py",
      handler: "lambda_handler",
      memorySize: 512,
      role: registrationLambdaRole,
      timeout: Duration.minutes(5),
      logGroup: ISLogGroups.adminLogGroup(this),
      reservedConcurrentExecutions: 1, //tagging events can often double up (ASG delete + create event). This ensures no race cases are possible
      environment: {
        USER_AGENT_EXTRA: props.USER_AGENT_EXTRA,
        CONFIG_TABLE: props.configTable.tableName,
        REGISTRY_TABLE: props.registryTable.tableName,
        HUB_STACK_NAME: props.stackName,
        SCHEDULER_ROLE_NAME: props.schedulerRoleName,
        SCHEDULE_TAG_KEY: props.scheduleTagKey,
        SCHEDULING_INTERVAL_MINUTES: props.schedulingIntervalMinutes.toString(),
        ASG_SCHEDULED_RULES_PREFIX: props.asgScheduledRulesPrefix,
        ASG_METADATA_TAG_KEY: props.asgMetadataTagKey,
        LOCAL_EVENT_BUS_NAME: props.regionalEventBusName,
        GLOBAL_EVENT_BUS_NAME: props.globalEventBus.eventBusName,
      },
    });

    NagSuppressions.addResourceSuppressions(
      registrationLambdaRole,
      [
        {
          id: "AwsSolutions-IAM5",
          appliesTo: ["Resource::*"],
          reason: "required for xray",
        },
      ],
      true,
    );
    ISLogGroups.adminLogGroup(this).grantWrite(registrationLambdaRole);
    props.registryTable.grantReadWriteData(registrationLambdaRole);
    props.configTable.grantReadWriteData(registrationLambdaRole);
    props.globalEventBus.grantPutEventsTo(registrationLambdaRole);

    const resourceRegistrationDLQ = new Queue(this, "ResourceRegistrationDLQ", {
      encryption: QueueEncryption.SQS_MANAGED,
    });

    addCfnGuardSuppression(resourceRegistrationDLQ, ["SQS_QUEUE_KMS_MASTER_KEY_ID_RULE"]);

    const lambdaTarget = new targets.LambdaFunction(this.registrationLambda, {
      deadLetterQueue: resourceRegistrationDLQ,
    });

    new Rule(this, "TaggingEventsToLambda", {
      eventBus: taggingEventBus,
      eventPattern: taggingEventPattern(props.scheduleTagKey),
      targets: [lambdaTarget],
    });
    new Rule(this, "AsgTaggingEventsToLambda", {
      eventBus: taggingEventBus,
      eventPattern: asgTaggingEventPattern(props.scheduleTagKey),
      targets: [lambdaTarget],
    });

    const regionRegistrationCustomResource = new RegionRegistrationCustomResource(
      this,
      "RegionRegistrationCustomResource",
      {
        hubAccountId: Aws.ACCOUNT_ID,
        namespace: props.namespace,
        factory: props.factory,
        USER_AGENT_EXTRA: props.USER_AGENT_EXTRA,
        version: props.solutionVersion,
        targetStack: TargetStack.HUB,
        hubRegisterRegionFunctionName: props.spokeRegistrationLambda.functionName,
        hubRegisterRegionRoleName: props.spokeRegistrationLambdaRoleName,
      },
    );

    const regionRegistration = new CustomResource(this, "RegisterRegions", {
      serviceToken: regionRegistrationCustomResource.regionRegistrationCustomResourceProvider.serviceToken,
      resourceType: "Custom::RegisterRegion",
      properties: {
        regions: props.regions,
      },
    });
    const regionRegistrationCfnResource = regionRegistration.node.defaultChild as CfnResource;
    this.regionRegistrationCfnResource = regionRegistrationCfnResource;

    regionRegistrationCfnResource.addDependency(
      regionRegistrationCustomResource.regionRegistrationWaitLambdaRoleCfnResource,
    );
    regionRegistrationCfnResource.addDependency(
      regionRegistrationCustomResource.regionRegistrationCustomResourceLambdaRoleCfnResource,
    );
    regionRegistrationCfnResource.addOverride("UpdateReplacePolicy", "Retain");
  }
}
