// The snapshot keeps original source-directory identities. Only the lab label
// follows the operator's game names from game_predictor_traning_set.
const displayNamesByLegacyGameId: Record<string, string> = {
  'local-8f24e7200f37e017db540839': 'blazing',
  'local-ca1a5075dbd40725f464d429': 'gang',
  'local-7a0650634c7a607f30c93774': 'mumie',
  'local-d0e1a94c35b78ceb9211ee6a': 'treasure',
};

export function gameDisplayName(gameId: string, originalName: string): string {
  return displayNamesByLegacyGameId[gameId] ?? originalName;
}
