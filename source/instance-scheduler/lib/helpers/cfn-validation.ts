// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Disables the CloudFormation validator that aws-cdk-lib runs during synthesis.
 *
 * aws-cdk-lib 2.273.0 bundles @aws/cloudformation-validate 1.12.1, which does
 * not terminate on the hub template. It runs away on CPU inside its wasm
 * binary: 10m35s of wall clock consuming 48m51s of CPU across ~4.7 cores,
 * killed without completing and without an error. It reproduces outside jest,
 * so it affects `cdk synth` and `cdk deploy` as well as the test suite. Under
 * jest there is no failure to read, because the synthesis happens at module
 * scope where the per-test timeout does not apply. aws-cdk-lib 2.265.0 bundled
 * 1.7.0-beta and validated the same template in ~25s.
 *
 * The trigger is this template, not the validator version alone: 1.12.1
 * validates the spoke template in ~1s and other solutions' templates without
 * trouble. Removing the cdk-nag aspects does not avoid the hang. Disabling is
 * app-wide because validation runs per App/Stage and the app holds both stacks.
 *
 * The bundled copy cannot be pinned separately: npm records it as `inBundle`,
 * so `overrides` do not reach it.
 *
 * What this gives up: the validator's warnings (unreferenced parameters,
 * missing UpdateReplacePolicy, and similar) and the validation-report.json it
 * writes into cdk.out. Nothing gates on either today, because the
 * `@aws-cdk/core:validateAgainstDefaultRules` feature flag is not set and
 * aws-cdk-lib downgrades the validator's errors to warnings while it is unset.
 * cdk-nag runs as an Aspect and is unaffected.
 *
 * Caveat for whoever enables `@aws-cdk/core:validateAgainstDefaultRules` later:
 * it will have no effect while this is in place. Remove this once aws-cdk-lib
 * ships a validator without the hang.
 *
 * Must run before App synthesis; aws-cdk-lib reads the variable at synth time.
 */
export function disableBundledCfnValidation(): void {
  process.env.CDK_VALIDATION = "false";
}
