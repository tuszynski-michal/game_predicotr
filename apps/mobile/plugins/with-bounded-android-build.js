const { withGradleProperties } = require('@expo/config-plugins');

const GRADLE_PROPERTIES = {
  'org.gradle.jvmargs': '-Xmx2048m -XX:MaxMetaspaceSize=768m',
  'org.gradle.parallel': 'false',
  'org.gradle.workers.max': '1',
  'kotlin.compiler.execution.strategy': 'in-process',
};

function upsertProperty(properties, key, value) {
  const existing = properties.find(
    (property) => property.type === 'property' && property.key === key,
  );
  if (existing) {
    existing.value = value;
    return;
  }
  properties.push({
    type: 'property',
    key,
    value,
  });
}

module.exports = function withBoundedAndroidBuild(config) {
  return withGradleProperties(config, (gradleConfig) => {
    for (const [key, value] of Object.entries(GRADLE_PROPERTIES)) {
      upsertProperty(gradleConfig.modResults, key, value);
    }
    return gradleConfig;
  });
};
