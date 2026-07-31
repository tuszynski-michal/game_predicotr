import type { ImageSourcePropType } from 'react-native';

const bundledSymbolAssets: Readonly<Record<string, ImageSourcePropType>> = {
  'symbols/v01/cherries.png': require('../../../assets/symbols/v01/cherries.png'),
  'symbols/v01/grapes.png': require('../../../assets/symbols/v01/grapes.png'),
  'symbols/v01/lemon.png': require('../../../assets/symbols/v01/lemon.png'),
  'symbols/v01/orange.png': require('../../../assets/symbols/v01/orange.png'),
  'symbols/v01/plum.png': require('../../../assets/symbols/v01/plum.png'),
  'symbols/v01/seven.png': require('../../../assets/symbols/v01/seven.png'),
  'symbols/v01/star.png': require('../../../assets/symbols/v01/star.png'),
  'symbols/v01/watermelon.png': require('../../../assets/symbols/v01/watermelon.png'),
};

export function resolveSymbolAsset(
  imageAssetKey: string | undefined,
): ImageSourcePropType | null {
  if (imageAssetKey === undefined) {
    return null;
  }
  return bundledSymbolAssets[imageAssetKey] ?? null;
}
