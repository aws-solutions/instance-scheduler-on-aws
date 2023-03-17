
import * as cdk from "aws-cdk-lib"
import {Construct} from "constructs";
import {testResourceProviders} from "../e2e-tests";
export interface E2ETest {
  createTestResources(scope: Construct) : void
  runTests() : void
}

export class E2eTestStack extends cdk.Stack {
  constructor(scope: Construct, id: string) {
    super(scope, id);

    for (const testResourceProvider of testResourceProviders) {
      testResourceProvider.createTestResources(this);
    }

    cdk.Stack.of(this);
  }
}
