import type { DatasetValidationReportResponse } from '@game-predictor/admin-api-client';

import {
  datasetValidationCheckLabel,
  datasetValidationStatusLabel,
  formatDiagnosticNumbers,
} from './dataset-state';

interface DatasetValidationReportProps {
  readonly report: DatasetValidationReportResponse;
}

export function DatasetValidationReport({
  report,
}: DatasetValidationReportProps) {
  return (
    <section
      aria-label={`Raport integralności datasetu v${report.datasetVersion}`}
      className={`datasetValidationReport ${
        report.readyForPublication
          ? 'datasetValidationReportReady'
          : 'datasetValidationReportBlocked'
      }`}
    >
      <header className="datasetValidationHeader">
        <div>
          <p className="eyebrow">Raport integralności</p>
          <h3>
            {report.readyForPublication
              ? 'Gotowy do publikacji'
              : 'Publikacja zablokowana'}
          </h3>
        </div>
        <strong>
          {report.actualLayoutCount}/{report.declaredLayoutCount} plansz
        </strong>
      </header>

      <dl className="datasetValidationMetrics">
        <div>
          <dt>Zakres sekwencji</dt>
          <dd>
            {report.minSequenceNumber ?? '—'}–{report.maxSequenceNumber ?? '—'}
          </dd>
        </div>
        <div>
          <dt>Grupy duplikatów</dt>
          <dd>{report.duplicateSignatureGroupCount}</dd>
        </div>
        <div>
          <dt>Plansze w grupach</dt>
          <dd>{report.duplicateSignatureAffectedLayoutCount}</dd>
        </div>
        <div>
          <dt>Nadmiarowe wystąpienia</dt>
          <dd>{report.duplicateSignatureExcessLayoutCount}</dd>
        </div>
      </dl>

      <ul className="datasetValidationChecks">
        {report.checks.map((check) => (
          <li
            className={`datasetValidationCheck datasetValidationCheck-${check.status}`}
            key={check.code}
          >
            <div>
              <strong>{datasetValidationCheckLabel(check.code)}</strong>
              <span>
                {datasetValidationStatusLabel(check.status)}
                {check.issueCount > 0 ? ` · ${check.issueCount}` : ''}
              </span>
            </div>
            {check.sequenceNumbers.length > 0 ? (
              <p>
                Pozycje: {formatDiagnosticNumbers(check.sequenceNumbers)}
                {check.truncated ? '…' : ''}
              </p>
            ) : null}
            {check.mobileCodes.length > 0 ? (
              <p>
                Obce kody: {formatDiagnosticNumbers(check.mobileCodes)}
                {check.truncated ? '…' : ''}
              </p>
            ) : null}
          </li>
        ))}
      </ul>

      {report.duplicateSignatures.length > 0 ? (
        <div className="datasetDuplicateTableWrap">
          <table className="datasetDuplicateTable">
            <thead>
              <tr>
                <th>Sygnatura</th>
                <th>Wystąpienia</th>
                <th>Numery sekwencji</th>
              </tr>
            </thead>
            <tbody>
              {report.duplicateSignatures.map((group) => (
                <tr key={group.signature}>
                  <td>
                    <code>{group.signature}</code>
                  </td>
                  <td>{group.occurrenceCount}</td>
                  <td>
                    {formatDiagnosticNumbers(group.sequenceNumbers)}
                    {group.truncated ? '…' : ''}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {report.duplicateSignaturesTruncated ? (
            <p className="datasetDiagnosticNote">
              Lista grup została ograniczona; liczniki powyżej obejmują cały
              dataset.
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
