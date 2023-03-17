import {E2ETest} from "../e2e-test-stack";
import {Construct} from "constructs";

import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as cdk from "aws-cdk-lib";
import {NagSuppressions} from "cdk-nag";
export class BasicEc2StartStopTest implements E2ETest {
  createTestResources(scope: Construct): void {

    const vpc = new ec2.Vpc(scope, "basic-start-stop-vpc", {
      ipAddresses: ec2.IpAddresses.cidr("10.0.0.0/16")
    })

    const testInstance = new ec2.Instance(scope, "basic-start-stop-instance", {
      instanceName: "basic-start-stop-instance",
      instanceType: ec2.InstanceType.of(ec2.InstanceClass.T2, ec2.InstanceSize.MICRO),
      machineImage: ec2.MachineImage.latestAmazonLinux(),
      vpc: vpc
    })

    cdk.Tags.of(testInstance).add("Schedule", "basic-start-stop-test-schedule")

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
  }

  runTests(): void {
  }

}

test('Print Environment', ()=> {
  console.log(process.env)
})
