
import * as cdk from "aws-cdk-lib"
import {Construct} from "constructs";

export interface E2ETest {
  createTestResources(scope: Construct) : void
  runTests() : void
}

export class E2eTestStack extends cdk.Stack {
  constructor(scope: Construct, id: string) {
    super(scope, id);

    for(const e2eTest of listE2ETests()) {
      e2eTest.createTestResources(this);
    }

    cdk.Stack.of(this);
  }
}

function listE2ETests() : E2ETest[] {
  return [];
}
