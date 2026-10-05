/** Match Next's single React runtime when rendering workspace components in Node. */
export function resolve(specifier, context, nextResolve) {
  if (
    specifier === 'react' ||
    specifier.startsWith('react/') ||
    specifier === 'react-dom' ||
    specifier.startsWith('react-dom/')
  ) {
    return nextResolve(specifier, { ...context, parentURL: import.meta.url });
  }
  return nextResolve(specifier, context);
}
