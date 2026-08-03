/** @type {import('ts-jest').JestConfigWithTsJest} */
module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  roots: ['<rootDir>/__tests__', '<rootDir>/src'],
  moduleFileExtensions: ['ts', 'tsx', 'js', 'jsx'],
  transform: { '^.+\\.tsx?$': ['ts-jest', { tsconfig: { jsx: 'react-jsx', noImplicitAny: false, strict: false }, diagnostics: false }] },
  testMatch: ['**/__tests__/*.test.ts'],
  moduleNameMapper: {
    '^react-native$': '<rootDir>/__tests__/__mocks__/react-native.ts',
    '^expo-audio$': '<rootDir>/__tests__/__mocks__/expo-audio.ts',
    '^react-native-track-player$': '<rootDir>/__tests__/__mocks__/react-native-track-player.ts',
    '^axios$': '<rootDir>/__tests__/__mocks__/axios.ts',
    '^expo-secure-store$': '<rootDir>/__tests__/__mocks__/expo-secure-store.ts',
    '^expo-notifications$': '<rootDir>/__tests__/__mocks__/expo-notifications.ts',
    '^expo-device$': '<rootDir>/__tests__/__mocks__/expo-device.ts',
  },
};
