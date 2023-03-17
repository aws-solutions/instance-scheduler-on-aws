// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
module.exports = {
  env: {
    jest: true,
    node: true,
    es2021: true
  },
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:prettier/recommended'
  ],
  overrides: [
  ],
  parserOptions: {
    ecmaVersion: 'latest',
    project: './tsconfig.json',
    sourceType: 'module'
  },
  plugins: [
    'header',
    'import'
  ],
  rules: {
    // '@typescript-eslint/semi': [
    //   'error',
    //   'always'
    // ],
    'header/header': [
      'error',
      'line',
      [
        ' Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.',
        ' SPDX-License-Identifier: Apache-2.0'
      ]
    ]
  }
};
