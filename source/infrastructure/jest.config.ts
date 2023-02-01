module.exports = {
  "roots": [
    "<rootDir>/tests"
  ],
  testMatch: [ '**/*.test.ts'],
  transform: {
    '^.+\\.tsx?$': 'ts-jest'
  }
}