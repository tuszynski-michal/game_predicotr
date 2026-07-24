function readVersionCode(defaultVersionCode) {
  const configuredVersionCode = process.env.GAME_PREDICTOR_VERSION_CODE;
  if (configuredVersionCode === undefined) {
    return defaultVersionCode;
  }

  const versionCode = Number.parseInt(configuredVersionCode, 10);
  if (
    !Number.isSafeInteger(versionCode) ||
    versionCode < 1 ||
    String(versionCode) !== configuredVersionCode
  ) {
    throw new Error('GAME_PREDICTOR_VERSION_CODE must be a positive integer.');
  }
  return versionCode;
}

module.exports = ({ config }) => {
  const version =
    process.env.GAME_PREDICTOR_VERSION_NAME ?? config.version ?? '0.1.0';
  if (!/^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$/.test(version)) {
    throw new Error('GAME_PREDICTOR_VERSION_NAME must be a semantic version.');
  }

  return {
    ...config,
    android: {
      ...config.android,
      versionCode: readVersionCode(config.android?.versionCode ?? 1),
    },
    version,
  };
};
