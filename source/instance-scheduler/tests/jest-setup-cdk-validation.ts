// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { disableBundledCfnValidation } from "../lib/helpers/cfn-validation";

// Runs before the test modules load, so it lands before any stack is
// synthesized. See the helper for why the bundled validator is disabled.
disableBundledCfnValidation();
