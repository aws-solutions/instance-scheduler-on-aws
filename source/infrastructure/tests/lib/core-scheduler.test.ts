import { Stack } from "aws-cdk-lib";
import { Template } from "aws-cdk-lib/assertions";
import {
  CompositePrincipal,
  Role,
  ServicePrincipal,
} from "aws-cdk-lib/aws-iam";
import { Key } from "aws-cdk-lib/aws-kms";
import { Bucket } from "aws-cdk-lib/aws-s3";
import { CoreScheduler } from "../../lib/core-scheduler";

describe("core scheduler", function () {
  const stack = new Stack();
  const key = new Key(stack, "Key");
  const role = new Role(stack, "Role", {
    assumedBy: new CompositePrincipal(
      new ServicePrincipal("events.amazonaws.com"),
      new ServicePrincipal("lambda.amazonaws.com")
    ),
  });

  const bucket = Bucket.fromBucketName(stack, "DistBucket", "my-bucket");

  new CoreScheduler(stack, {
    kmsEncryptionKey: key,
    memorySize: 128,
    schedulerRole: role,
    solutionsBucket: bucket,
    solutionVersion: "v9.9.9",
  });
  const template = Template.fromStack(stack);

  it("matches snapshot", function () {
    expect(template).toMatchSnapshot();
  });

  const stateTableLogicalId = "StateTable";

  describe("state table", function () {
    const table: any = template.findResources("AWS::DynamoDB::Table")[
      stateTableLogicalId
    ];

    it("partition key is service", function () {
      const key = "service";

      expect(table.Properties.KeySchema).toEqual(
        expect.arrayContaining([
          {
            AttributeName: key,
            KeyType: "HASH",
          },
        ])
      );
      expect(table.Properties.AttributeDefinitions).toEqual(
        expect.arrayContaining([
          {
            AttributeName: key,
            AttributeType: "S",
          },
        ])
      );
    });

    it("sort key is account-region", function () {
      const key = "account-region";

      expect(table.Properties.KeySchema).toEqual(
        expect.arrayContaining([
          {
            AttributeName: key,
            KeyType: "RANGE",
          },
        ])
      );
      expect(table.Properties.AttributeDefinitions).toEqual(
        expect.arrayContaining([
          {
            AttributeName: key,
            AttributeType: "S",
          },
        ])
      );
    });

    it("is billed per-request", function () {
      expect(table.Properties.BillingMode).toStrictEqual("PAY_PER_REQUEST");
    });

    it("has point-in-time recovery enabled", function () {
      expect(table.Properties.PointInTimeRecoverySpecification).toStrictEqual({
        PointInTimeRecoveryEnabled: true,
      });
    });

    it.skip("is encrypted with KMS key", function () {
      const keys = template.findResources("AWS::KMS::Key");
      const keyIds = Object.getOwnPropertyNames(keys);
      expect(keyIds).toHaveLength(1);
      expect(table.Properties.SSESpecification).toStrictEqual({
        KMSMasterKeyId: { Ref: keyIds[0] },
        SSEEnabled: true,
        SSEType: "KMS",
      });
    });

    it("is not retained", function () {
      expect(table.DeletionPolicy).toStrictEqual("Delete");
      expect(table.UpdateReplacePolicy).toStrictEqual("Delete");
    });
  });

  const configTableLogicalId = "ConfigTable";

  describe("config table", function () {
    const table: any = template.findResources("AWS::DynamoDB::Table")[
      configTableLogicalId
    ];

    it("partition key is type", function () {
      const key = "type";

      expect(table.Properties.KeySchema).toEqual(
        expect.arrayContaining([
          {
            AttributeName: key,
            KeyType: "HASH",
          },
        ])
      );
      expect(table.Properties.AttributeDefinitions).toEqual(
        expect.arrayContaining([
          {
            AttributeName: key,
            AttributeType: "S",
          },
        ])
      );
    });

    it("sort key is name", function () {
      const key = "name";

      expect(table.Properties.KeySchema).toEqual(
        expect.arrayContaining([
          {
            AttributeName: key,
            KeyType: "RANGE",
          },
        ])
      );
      expect(table.Properties.AttributeDefinitions).toEqual(
        expect.arrayContaining([
          {
            AttributeName: key,
            AttributeType: "S",
          },
        ])
      );
    });

    it("is billed per-request", function () {
      expect(table.Properties.BillingMode).toStrictEqual("PAY_PER_REQUEST");
    });

    it("has point-in-time recovery enabled", function () {
      expect(table.Properties.PointInTimeRecoverySpecification).toStrictEqual({
        PointInTimeRecoveryEnabled: true,
      });
    });

    it("is encrypted with KMS key", function () {
      const keys = template.findResources("AWS::KMS::Key");
      const keyIds = Object.getOwnPropertyNames(keys);
      expect(keyIds).toHaveLength(1);
      expect(table.Properties.SSESpecification).toStrictEqual({
        KMSMasterKeyId: { Ref: keyIds[0] },
        SSEEnabled: true,
        SSEType: "KMS",
      });
    });

    it("is not retained", function () {
      expect(table.DeletionPolicy).toStrictEqual("Delete");
      expect(table.UpdateReplacePolicy).toStrictEqual("Delete");
    });
  });

  const maintenanceWindowTableLogicalId = "MaintenanceWindowTable";

  describe("maintenance window table", function () {
    const table: any = template.findResources("AWS::DynamoDB::Table")[
      maintenanceWindowTableLogicalId
    ];

    it("partition key is Name", function () {
      const key = "Name";

      expect(table.Properties.KeySchema).toEqual(
        expect.arrayContaining([
          {
            AttributeName: key,
            KeyType: "HASH",
          },
        ])
      );
      expect(table.Properties.AttributeDefinitions).toEqual(
        expect.arrayContaining([
          {
            AttributeName: key,
            AttributeType: "S",
          },
        ])
      );
    });

    it("sort key is account-region", function () {
      const key = "account-region";

      expect(table.Properties.KeySchema).toEqual(
        expect.arrayContaining([
          {
            AttributeName: key,
            KeyType: "RANGE",
          },
        ])
      );
      expect(table.Properties.AttributeDefinitions).toEqual(
        expect.arrayContaining([
          {
            AttributeName: key,
            AttributeType: "S",
          },
        ])
      );
    });

    it("is billed per-request", function () {
      expect(table.Properties.BillingMode).toStrictEqual("PAY_PER_REQUEST");
    });

    it("has point-in-time recovery enabled", function () {
      expect(table.Properties.PointInTimeRecoverySpecification).toStrictEqual({
        PointInTimeRecoveryEnabled: true,
      });
    });

    it.skip("is encrypted with KMS key", function () {
      const keys = template.findResources("AWS::KMS::Key");
      const keyIds = Object.getOwnPropertyNames(keys);
      expect(keyIds).toHaveLength(1);
      expect(table.Properties.SSESpecification).toStrictEqual({
        KMSMasterKeyId: { Ref: keyIds[0] },
        SSEEnabled: true,
        SSEType: "KMS",
      });
    });

    it("is not retained", function () {
      expect(table.DeletionPolicy).toStrictEqual("Delete");
      expect(table.UpdateReplacePolicy).toStrictEqual("Delete");
    });
  });

  describe("function", function () {
    const functions = template.findResources("AWS::Lambda::Function");
    const functionIds = Object.getOwnPropertyNames(functions);
    expect(functionIds).toHaveLength(1);
    const lambdaFunction = functions[functionIds[0]];

    describe("environment", function () {
      const env = lambdaFunction.Properties.Environment.Variables;

      it("has state table name", function () {
        expect(env).toEqual(
          expect.objectContaining({
            STATE_TABLE: { Ref: stateTableLogicalId },
          })
        );
      });

      it("has config table name", function () {
        expect(env).toEqual(
          expect.objectContaining({
            CONFIG_TABLE: { Ref: configTableLogicalId },
          })
        );
      });

      it("has maintenance window table name", function () {
        expect(env).toEqual(
          expect.objectContaining({
            MAINTENANCE_WINDOW_TABLE: { Ref: maintenanceWindowTableLogicalId },
          })
        );
      });
    });

    describe("role", function () {
      const roleId = lambdaFunction.Properties.Role["Fn::GetAtt"][0];
      const roles = template.findResources("AWS::IAM::Role");
      const role = roles[roleId];

      describe("trust relationship", function () {
        it("includes lambda", function () {
          expect(role.Properties.AssumeRolePolicyDocument.Statement).toEqual(
            expect.arrayContaining([
              {
                Action: "sts:AssumeRole",
                Effect: "Allow",
                Principal: { Service: "lambda.amazonaws.com" },
              },
            ])
          );
        });

        it("includes eventbridge", function () {
          expect(role.Properties.AssumeRolePolicyDocument.Statement).toEqual(
            expect.arrayContaining([
              {
                Action: "sts:AssumeRole",
                Effect: "Allow",
                Principal: { Service: "events.amazonaws.com" },
              },
            ])
          );
        });
      });

      describe("policy", function () {
        const policies = template.findResources("AWS::IAM::Policy", {
          Properties: {
            Roles: [{ Ref: roleId }],
          },
        });
        const policyIds = Object.getOwnPropertyNames(policies);
        expect(policyIds).toHaveLength(1);
        const policy = policies[policyIds[0]];

        it("has xray permissions", function () {
          expect(policy.Properties.PolicyDocument.Statement).toEqual(
            expect.arrayContaining([
              {
                Action: expect.arrayContaining([
                  "xray:PutTraceSegments",
                  "xray:PutTelemetryRecords",
                ]),
                Effect: "Allow",
                Resource: "*",
              },
            ])
          );
        });

        it("has state table permissions", function () {
          expect(policy.Properties.PolicyDocument.Statement).toEqual(
            expect.arrayContaining([
              {
                Action: expect.arrayContaining([
                  "dynamodb:BatchGetItem",
                  "dynamodb:GetRecords",
                  "dynamodb:GetShardIterator",
                  "dynamodb:Query",
                  "dynamodb:GetItem",
                  "dynamodb:Scan",
                  "dynamodb:ConditionCheckItem",
                  "dynamodb:BatchWriteItem",
                  "dynamodb:PutItem",
                  "dynamodb:UpdateItem",
                  "dynamodb:DeleteItem",
                  "dynamodb:DescribeTable",
                ]),
                Effect: "Allow",
                Resource: expect.arrayContaining([
                  {
                    ["Fn::GetAtt"]: [stateTableLogicalId, "Arn"],
                  },
                ]),
              },
            ])
          );
        });

        it("has config table permissions", function () {
          expect(policy.Properties.PolicyDocument.Statement).toEqual(
            expect.arrayContaining([
              {
                Action: expect.arrayContaining([
                  "dynamodb:DeleteItem",
                  "dynamodb:GetItem",
                  "dynamodb:PutItem",
                  "dynamodb:Query",
                  "dynamodb:Scan",
                  "dynamodb:BatchWriteItem",
                ]),
                Effect: "Allow",
                Resource: expect.arrayContaining([
                  {
                    ["Fn::GetAtt"]: [configTableLogicalId, "Arn"],
                  },
                ]),
              },
            ])
          );
        });

        it("has maintenance window table permissions", function () {
          expect(policy.Properties.PolicyDocument.Statement).toEqual(
            expect.arrayContaining([
              {
                Action: expect.arrayContaining([
                  "dynamodb:DeleteItem",
                  "dynamodb:GetItem",
                  "dynamodb:PutItem",
                  "dynamodb:Query",
                  "dynamodb:Scan",
                  "dynamodb:BatchWriteItem",
                ]),
                Effect: "Allow",
                Resource: expect.arrayContaining([
                  {
                    ["Fn::GetAtt"]: [maintenanceWindowTableLogicalId, "Arn"],
                  },
                ]),
              },
            ])
          );
        });
      });
    });
  });
});
