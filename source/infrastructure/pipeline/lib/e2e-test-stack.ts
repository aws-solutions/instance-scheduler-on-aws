
import * as cdk from "aws-cdk-lib"
import {Construct} from "constructs";
export interface E2ETest {
  createTestResources(scope: Construct) : void
  runTests() : void
}

export class E2eTestStack extends cdk.Stack {
  constructor(scope: Construct, id: string) {
    super(scope, id);

    for (const testResourceProviderFunc of E2ETestResources.getAll()) {
      testResourceProviderFunc(this);
    }

    cdk.Stack.of(this);
  }
}

export namespace E2ETestResources {

  const testResourceProviders: ((scope: Construct) => void)[] = []

  export function register(createTestResourcesFunc: (scope: Construct) => void) {
    testResourceProviders.push(createTestResourcesFunc)
  }

  export function getAll() {
    return testResourceProviders;
  }
}
