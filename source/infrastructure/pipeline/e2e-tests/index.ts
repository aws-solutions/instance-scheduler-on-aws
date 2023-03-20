import {Construct} from "constructs";
import {EC2StartStopTestResources} from "./basic-ec2-start-stop.test.resources";
import {CfnOutput} from "aws-cdk-lib";

export interface TestResourceProvider {
  createTestResources(scope: Construct) : Record<string, CfnOutput>
}

export const testResourceProviders : TestResourceProvider[] = [
  new EC2StartStopTestResources
]
