const { withAppBuildGradle } = require('@expo/config-plugins');

const PLUGIN_MARKER = 'GAME_PREDICTOR_RELEASE_SIGNING';

function addReleaseSigningConfig(source) {
  if (source.includes(PLUGIN_MARKER)) {
    return source;
  }

  const signingConfigsStart = source.indexOf('    signingConfigs {');
  const buildTypesStart = source.indexOf(
    '    buildTypes {',
    signingConfigsStart,
  );
  if (signingConfigsStart < 0 || buildTypesStart < 0) {
    throw new Error(
      'Could not locate Android signingConfigs/buildTypes in generated Gradle.',
    );
  }

  const signingConfigsEnd = source.lastIndexOf('    }', buildTypesStart);
  if (signingConfigsEnd < signingConfigsStart) {
    throw new Error('Could not locate the end of Android signingConfigs.');
  }

  const releaseSigningConfig = `
        // ${PLUGIN_MARKER}
        release {
            def releaseStoreFilePath = System.getenv("GAME_PREDICTOR_RELEASE_STORE_FILE")
            if (releaseStoreFilePath != null) {
                storeFile file(releaseStoreFilePath)
                storePassword System.getenv("GAME_PREDICTOR_RELEASE_STORE_PASSWORD")
                keyAlias System.getenv("GAME_PREDICTOR_RELEASE_KEY_ALIAS")
                keyPassword System.getenv("GAME_PREDICTOR_RELEASE_KEY_PASSWORD")
            }
        }
`;

  let updatedSource =
    source.slice(0, signingConfigsEnd) +
    releaseSigningConfig +
    source.slice(signingConfigsEnd);

  const updatedBuildTypesStart = updatedSource.indexOf('    buildTypes {');
  const releaseBuildStart = updatedSource.indexOf(
    '        release {',
    updatedBuildTypesStart,
  );
  if (releaseBuildStart < 0) {
    throw new Error('Could not locate the Android release build type.');
  }
  const debugSigningLine = 'signingConfig signingConfigs.debug';
  const debugSigningIndex = updatedSource.indexOf(
    debugSigningLine,
    releaseBuildStart,
  );
  if (debugSigningIndex < 0) {
    throw new Error(
      'Could not replace the generated debug signing config for release.',
    );
  }

  updatedSource =
    updatedSource.slice(0, debugSigningIndex) +
    'signingConfig signingConfigs.release' +
    updatedSource.slice(debugSigningIndex + debugSigningLine.length);

  return updatedSource;
}

function withReleaseSigning(config) {
  return withAppBuildGradle(config, (gradleConfig) => {
    if (gradleConfig.modResults.language !== 'groovy') {
      throw new Error('Release signing plugin requires Groovy build.gradle.');
    }
    gradleConfig.modResults.contents = addReleaseSigningConfig(
      gradleConfig.modResults.contents,
    );
    return gradleConfig;
  });
}

module.exports = withReleaseSigning;
