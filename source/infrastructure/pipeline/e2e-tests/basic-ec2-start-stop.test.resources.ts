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
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as cdk from "aws-cdk-lib";

import {Construct} from "constructs";
import {NagSuppressions} from "cdk-nag";
import {TestResourceProvider} from "./index";



const envKeys = {
  ec2InstanceId: 'basic_start_stop_instance_id',
}
export const resourceParams = {
  ec2InstanceId: process.env[envKeys.ec2InstanceId]!,
  startStopTestScheduleName: 'ec2_basic_start_stop_test_schedule'
}
export class EC2StartStopTestResources implements TestResourceProvider {
  createTestResources(scope: Construct) {

    const vpc = new ec2.Vpc(scope, "basic-start-stop-vpc", {
      natGateways: 0,
      ipAddresses: ec2.IpAddresses.cidr("10.0.0.0/16")
    })

    const testInstance = new ec2.Instance(scope, "basic-start-stop-instance", {
      instanceType: ec2.InstanceType.of(ec2.InstanceClass.T2, ec2.InstanceSize.MICRO),
      machineImage: ec2.MachineImage.latestAmazonLinux(),
      vpc: vpc,
    })

    cdk.Tags.of(testInstance).add("Schedule", resourceParams.startStopTestScheduleName )

    const startStopOut = new cdk.CfnOutput(scope, envKeys.ec2InstanceId, {
      value: testInstance.instanceId,
    })

    NagSuppressions.addResourceSuppressions(testInstance, [
      {
        id: "AwsSolutions-EC28",
        reason: "This is a test instance that only ever needs to be started/stopped (work workloads)"
      },
      {
        id: "AwsSolutions-EC29",
        reason: "This is an automated test instance without any need for termination protection"
      },
    ])

    NagSuppressions.addResourceSuppressions(vpc, [
      {
        id: "AwsSolutions-VPC7",
        reason: "The VPC  is for a test instance that only ever needs to be started/stopped (no traffic)"
      },
    ])

    return {
      [envKeys.ec2InstanceId]: startStopOut,
    }
  }

}
