import {Construct} from "constructs";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as cdk from "aws-cdk-lib";
import {NagSuppressions} from "cdk-nag";
import {TestResourceProvider} from "./index";


export const START_STOP_TEST_SCHEDULE_NAME = 'basic-start-stop-test-schedule'
export const START_STOP_TEST_INSTANCE_ID_OUT_PATH = 'basic-start-stop-instance-id'
export class EC2StartStopTestResources implements TestResourceProvider {
  createTestResources(scope: Construct) {

    const vpc = new ec2.Vpc(scope, "basic-start-stop-vpc", {
      ipAddresses: ec2.IpAddresses.cidr("10.0.0.0/16")
    })

    const testInstance = new ec2.Instance(scope, "basic-start-stop-instance", {
      instanceType: ec2.InstanceType.of(ec2.InstanceClass.T2, ec2.InstanceSize.MICRO),
      machineImage: ec2.MachineImage.latestAmazonLinux(),
      vpc: vpc
    })

    cdk.Tags.of(testInstance).add("Schedule", START_STOP_TEST_SCHEDULE_NAME)

    const startStopOut = new cdk.CfnOutput(scope, "SOSSO", {
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
      "SV_StartStop": startStopOut,
      "SV_VPC": new cdk.CfnOutput(scope, "SV_VPC", {
        value: vpc.vpcArn
      }),
      "SV_FixedTest": new cdk.CfnOutput(scope, "SV_FixedTest", {
        value: "searchable-value1",
        exportName: "exportName"
      })
    }
  }

}
