import {Construct} from "constructs";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as cdk from "aws-cdk-lib";
import {NagSuppressions} from "cdk-nag";
import {TestResourceProvider} from "./index";


const startStopTestScheduleName = 'ec2_basic_start_stop_test_schedule'
const ec2InstanceEnvKey = 'basic_start_stop_instance_id'
export const RESOURCES = {
  EC2InstanceID: {
    envKey: ec2InstanceEnvKey,
    get: ()=> {
      return process.env[ec2InstanceEnvKey];
    }
  },
  StartStopTestScheduleName: {
    get: ()=> {
      return startStopTestScheduleName;
    }
  }
}
export class EC2StartStopTestResources implements TestResourceProvider {
  createTestResources(scope: Construct) {

    const vpc = new ec2.Vpc(scope, "basic-start-stop-vpc", {
      ipAddresses: ec2.IpAddresses.cidr("10.0.0.0/16")
    })

    const testInstance = new ec2.Instance(scope, "basic-start-stop-instance", {
      instanceType: ec2.InstanceType.of(ec2.InstanceClass.T2, ec2.InstanceSize.MICRO),
      machineImage: ec2.MachineImage.latestAmazonLinux(),
      vpc: vpc,
    })

    cdk.Tags.of(testInstance).add("Schedule", RESOURCES.StartStopTestScheduleName.get())

    const startStopOut = new cdk.CfnOutput(scope, RESOURCES.EC2InstanceID.envKey, {
      value: testInstance.instanceId,
    })

    NagSuppressions.addResourceSuppressions(testInstance, [
      {
        id: "AwsSolutions-EC28",
        reason: "test instance"
      },
      {
        id: "AwsSolutions-EC29",
        reason: "test instance"
      },
    ])

    NagSuppressions.addResourceSuppressions(vpc, [
      {
        id: "AwsSolutions-VPC7",
        reason: "testing resource"
      },
    ])

    return {
      [RESOURCES.EC2InstanceID.envKey]: startStopOut,
    }
  }

}
