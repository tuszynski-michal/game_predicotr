module.exports = {
  packagerConfig: {
    asar: true,
    executableName: 'Selektor-zdjec',
    // All runtime dependencies are bundled. Do not ship source or monorepo links.
    ignore: (path) =>
      path !== '' && !/^\/(dist(?:\/|$)|package\.json$)/.test(path),
  },
  makers: [{ name: '@electron-forge/maker-zip', platforms: ['win32'] }],
};
