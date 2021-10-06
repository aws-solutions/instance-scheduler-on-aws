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

import * as events from '@aws-cdk/aws-events'
import * as cdk from "@aws-cdk/core";

export interface SchedulerEventBusProps {
        organizationId: string[];
        namespace: string;
        lambdaFunctionArn: string;
        eventBusName: string;
        isMemberOfOrganizationsCondition: cdk.CfnCondition;
}

export class SchedulerEventBusResources extends cdk.Construct {
        readonly eventRuleCrossAccount: events.CfnRule;
        constructor(scope: cdk.Stack, id: string, props: SchedulerEventBusProps) {
        super(scope, id);

        const schedulerEventBus = new events.CfnEventBus(this, 'scheduler-event-bus', {
                name: props.namespace+'-'+props.eventBusName
        })

        const eventBusPolicy = new events.CfnEventBusPolicy(this, 'scheduler-event-bus-policy', {
                eventBusName: schedulerEventBus.attrName,
                statementId: schedulerEventBus.attrName,
                action: 'events:PutEvents',
                principal: '*',
                condition: {
                        type: 'StringEquals',
                        key: 'aws:PrincipalOrgID',
                        value: cdk.Fn.select(0,props.organizationId)
                }
        })

         this.eventRuleCrossAccount = new events.CfnRule(this, 'scheduler-ssm-parameter-cross-account-events', {
                description: "Event rule to invoke Instance Scheduler lambda function to store spoke account id(s) in configuration.",
                eventBusName: schedulerEventBus.attrName,
                state: 'ENABLED',
                targets: [{
                        arn: props.lambdaFunctionArn,
                        id: 'Scheduler-Lambda-Function'
                }],
                eventPattern: {
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

        schedulerEventBus.cfnOptions.condition = props.isMemberOfOrganizationsCondition
        eventBusPolicy.cfnOptions.condition = props.isMemberOfOrganizationsCondition
        this.eventRuleCrossAccount.cfnOptions.condition = props.isMemberOfOrganizationsCondition
}}

