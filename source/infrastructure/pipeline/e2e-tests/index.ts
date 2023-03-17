import {Construct} from "constructs";
import {EC2StartStopTestResources} from "./basic-ec2-start-stop.test.resources";

export interface TestResourceProvider {
  createTestResources(scope: Construct) : void
}

export const testResourceProviders : TestResourceProvider[] = [
  new EC2StartStopTestResources
]
