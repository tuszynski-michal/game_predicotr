import { StatusBar } from 'expo-status-bar';

import { LocalSnapshotGate } from '@/features/local-snapshot/local-snapshot-gate';

export default function HomeScreen() {
  return (
    <>
      <StatusBar style="dark" />
      <LocalSnapshotGate />
    </>
  );
}
