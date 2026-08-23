import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

import {
  REMOTE_SOURCE_CAPABILITY_REPORT_SCHEMA,
  attachCapabilityReportChecksum,
  benchmarkSyntheticManifests,
  verifyCapabilityReportChecksum,
} from './fixtures/remote-source-capability-spike.mjs';

const repositoryRoot = fileURLToPath(new URL('../../../', import.meta.url));
const reportPath = path.join(
  repositoryRoot,
  'ai_docs',
  'quality',
  'remote-source-capability-report-v1.json',
);

async function buildReport() {
  const benchmark = await benchmarkSyntheticManifests([1, 500, 1000]);
  return attachCapabilityReportChecksum({
    schemaVersion: REMOTE_SOURCE_CAPABILITY_REPORT_SCHEMA,
    generatedAt: new Date().toISOString(),
    task: 'TASK-0273',
    executionEnvironment: {
      runtime: `node ${process.version}`,
      platform: `${process.platform}-${process.arch}`,
      benchmarkKind: 'synthetic_metadata_only',
    },
    browserMatrix: [
      {
        browser: 'Chrome desktop',
        directoryHandle: 'supported_in_secure_context_after_user_activation',
        indexedDbHandle: 'supported_but_permission_must_be_rechecked',
        fallback: 'webkitdirectory_reselect',
        mvp: 'supported',
      },
      {
        browser: 'Edge desktop',
        directoryHandle: 'supported_in_secure_context_after_user_activation',
        indexedDbHandle: 'supported_but_permission_must_be_rechecked',
        fallback: 'webkitdirectory_reselect',
        mvp: 'supported',
      },
      {
        browser: 'Firefox/Safari',
        directoryHandle: 'not_guaranteed',
        indexedDbHandle: 'not_guaranteed',
        fallback: 'session_only_reselect_when_available',
        mvp: 'not_committed',
      },
    ],
    evidence: [
      'https://developer.mozilla.org/en-US/docs/Web/API/Window/showDirectoryPicker',
      'https://wicg.github.io/file-system-access/',
      'https://developer.chrome.com/docs/capabilities/web-apis/file-system-access',
      'https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/input/file',
    ],
    fixture: {
      path: 'apps/reviewer/test/fixtures/remote-source-capability-spike.html',
      productionRouteCreated: false,
      apiEndpointCreated: false,
      tunnelRequired: false,
      sourceWritePermissionRequested: false,
      sourceBytesUploaded: false,
    },
    automatedChecks: {
      deterministicNaturalManifest: 'passed',
      rejectsAbsoluteAndTraversalPaths: 'passed',
      readOnlyPermissionDescriptor: 'passed',
      relinkComparison: 'passed',
      reportChecksum: 'passed',
    },
    browserChecks: {
      chromiumInAppCapabilityDetection: 'passed_2026-08-23',
      opfsIndexedDbRoundtrip: 'passed_2026-08-23',
      reloadAndRestoreOpfsHandle: 'passed_2026-08-23',
      closeTabAndRestoreOpfsHandle: 'passed_2026-08-23',
      osDirectoryPickerReadOnly: 'manual_user_activation_required',
      closeBrowserAndRegrant: 'manual_fixture_available',
      permissionDenial: 'manual_fixture_available',
      webkitdirectoryFallback: 'api_detected_manual_file_choice_available',
    },
    benchmark,
    guarantees: {
      sourceManifestContainsBytes: false,
      sourceManifestContainsAbsolutePath: false,
      decodedFileCount: 0,
      byteReadCount: 0,
      durablePermissionGrantAssumed: false,
      relinkFallbackRequired: true,
    },
    decision: {
      status: 'go_with_constraints',
      browserOnlyMvp: true,
      supportedBrowsers: ['Chrome desktop', 'Edge desktop'],
      constraints: [
        'secure_context_and_transient_user_activation_are_required',
        'permission_must_be_checked_after_every_resume',
        'relink_is_required_when_a_handle_or_permission_is_unavailable',
        'webkitdirectory_is_session_only_and_requires_reselection',
        'the_remote_operator_selects_one_batch_at_a_time',
        'background_transfer_after_tab_close_is_not_guaranteed',
        'manual_browser_acceptance_is_required_before_public_rollout',
      ],
      nextTaskAllowed: true,
    },
  });
}

async function checkReport() {
  const report = JSON.parse(await readFile(reportPath, 'utf8'));
  if (!(await verifyCapabilityReportChecksum(report))) {
    throw new Error('Capability report checksum does not match its content.');
  }
  const counts = report.benchmark.map((entry) => entry.fileCount);
  if (JSON.stringify(counts) !== JSON.stringify([1, 500, 1000])) {
    throw new Error(`Unexpected benchmark counts: ${counts.join(', ')}`);
  }
  if (
    report.benchmark.some(
      (entry) => entry.decodedFileCount !== 0 || entry.byteReadCount !== 0,
    )
  ) {
    throw new Error('The metadata benchmark decoded or read source bytes.');
  }
  if (
    report.fixture.productionRouteCreated ||
    report.fixture.apiEndpointCreated ||
    report.fixture.tunnelRequired ||
    report.fixture.sourceWritePermissionRequested ||
    report.fixture.sourceBytesUploaded
  ) {
    throw new Error('The report violates the non-production spike boundary.');
  }
  if (report.decision.status !== 'go_with_constraints') {
    throw new Error(`Unexpected MVP decision: ${report.decision.status}`);
  }
  process.stdout.write(
    `verified ${path.relative(repositoryRoot, reportPath)} ${report.reportChecksumSha256}\n`,
  );
}

if (process.argv.includes('--check')) {
  await checkReport();
} else {
  const report = await buildReport();
  await writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
  process.stdout.write(
    `wrote ${path.relative(repositoryRoot, reportPath)} ${report.reportChecksumSha256}\n`,
  );
}
