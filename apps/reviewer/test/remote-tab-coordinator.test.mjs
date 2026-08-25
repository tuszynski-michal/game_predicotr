import assert from 'node:assert/strict';
import test from 'node:test';

import { RemoteSelectionTabCoordinator } from '../src/features/manual-selection/remote-tab-coordinator.ts';

class BroadcastBus {
  channels = new Map();

  create(name) {
    const channel = {
      onmessage: null,
      close: () => this.channels.get(name)?.delete(channel),
      postMessage: (message) => {
        for (const target of this.channels.get(name) ?? []) {
          if (target !== channel) target.onmessage?.({ data: message });
        }
      },
    };
    const channels = this.channels.get(name) ?? new Set();
    channels.add(channel);
    this.channels.set(name, channels);
    return channel;
  }
}

test('elects one writer and keeps a second tab read-only', async () => {
  const bus = new BroadcastBus();
  let now = 100;
  const options = {
    channelFactory: (name) => bus.create(name),
    discoveryMs: 0,
    heartbeatMs: 60_000,
    staleMs: 6_000,
    now: () => now,
  };
  const first = new RemoteSelectionTabCoordinator('session-1', 'client-a', {
    ...options,
    tabInstanceId: 'tab-a',
  });
  const second = new RemoteSelectionTabCoordinator('session-1', 'client-b', {
    ...options,
    tabInstanceId: 'tab-b',
  });

  assert.equal((await first.start()).mode, 'writer');
  now += 1;
  assert.equal((await second.start()).mode, 'read_only');
  assert.equal(second.state().ownerClientInstanceId, 'client-a');

  first.close();
  assert.equal(second.claimIfAvailable().mode, 'writer');
  second.close();
});

test('keeps the first live claim and isolates separate sessions', async () => {
  const bus = new BroadcastBus();
  const options = {
    channelFactory: (name) => bus.create(name),
    discoveryMs: 0,
    heartbeatMs: 60_000,
    now: () => 100,
  };
  const laterLexically = new RemoteSelectionTabCoordinator(
    'session-1',
    'client-z',
    { ...options, tabInstanceId: 'tab-z' },
  );
  const earlierLexically = new RemoteSelectionTabCoordinator(
    'session-1',
    'client-a',
    { ...options, tabInstanceId: 'tab-a' },
  );
  const anotherSession = new RemoteSelectionTabCoordinator(
    'session-2',
    'client-z',
    { ...options, tabInstanceId: 'tab-other-session' },
  );

  try {
    await laterLexically.start();
    await Promise.all([earlierLexically.start(), anotherSession.start()]);
    assert.equal(laterLexically.state().mode, 'writer');
    assert.equal(earlierLexically.state().mode, 'read_only');
    assert.equal(anotherSession.state().mode, 'writer');
  } finally {
    laterLexically.close();
    earlierLexically.close();
    anotherSession.close();
  }
});

test('copied sessionStorage client id still elects only one writer tab', async () => {
  const bus = new BroadcastBus();
  let now = 100;
  const options = {
    channelFactory: (name) => bus.create(name),
    discoveryMs: 0,
    heartbeatMs: 60_000,
    staleMs: 6_000,
    now: () => now,
  };
  const first = new RemoteSelectionTabCoordinator(
    'session-1',
    'shared-client',
    { ...options, tabInstanceId: 'tab-a' },
  );
  const copied = new RemoteSelectionTabCoordinator(
    'session-1',
    'shared-client',
    { ...options, tabInstanceId: 'tab-b' },
  );

  assert.equal((await first.start()).mode, 'writer');
  now += 1;
  assert.equal((await copied.start()).mode, 'read_only');
  first.close();
  assert.equal(copied.claimIfAvailable().mode, 'writer');
  copied.close();
});

test('a legacy live tab without a tab id keeps a new same-client tab read-only', async () => {
  const bus = new BroadcastBus();
  const legacy = bus.create('game-predictor-remote-selection:session-1');
  const coordinator = new RemoteSelectionTabCoordinator(
    'session-1',
    'shared-client',
    {
      channelFactory: (name) => bus.create(name),
      discoveryMs: 5,
      heartbeatMs: 60_000,
      now: () => 200,
      tabInstanceId: 'new-tab',
    },
  );

  const started = coordinator.start();
  legacy.postMessage({
    claimedAtMs: 100,
    kind: 'owner',
    schemaVersion: 1,
    senderClientInstanceId: 'shared-client',
    sessionId: 'session-1',
  });
  assert.equal((await started).mode, 'read_only');
  coordinator.close();
  legacy.close();
});

test('falls back to a single-tab writer when BroadcastChannel is unavailable', async () => {
  const coordinator = new RemoteSelectionTabCoordinator(
    'session-1',
    'client-a',
    { channelFactory: null },
  );
  assert.deepEqual(await coordinator.start(), {
    mode: 'writer',
    ownerClientInstanceId: 'client-a',
    supported: false,
  });
  coordinator.close();
});
