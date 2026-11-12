import type { GridCorrectionLearningCandidateStatus } from '@game-predictor/admin-api-client';

/** TASK-1189: current candidate state next to the learning's immutable verdict. */
const GATE_LABELS: Readonly<Record<string, string>> = {
  'grid-model-per-game-gate-v2': 'bramka v2',
  'grid-model-per-game-gate-v3': 'bramka ekranowa v3',
  'grid-model-per-game-gate-v4': 'bramka v4',
};

export function gateLabel(policyVersion: string): string {
  return GATE_LABELS[policyVersion] ?? policyVersion;
}

function usage(
  candidate: GridCorrectionLearningCandidateStatus,
): string | null {
  if (candidate.isDefault && candidate.assignedToGame) {
    return 'domyślny i przypisany do gry';
  }
  if (candidate.assignedToGame) return 'przypisany do gry';
  if (candidate.isDefault) return 'domyślny';
  return null;
}

/** Short suffix for the run list; empty when nothing changed after the learning. */
export function candidateRunSuffix(
  candidate: GridCorrectionLearningCandidateStatus | null | undefined,
): string {
  if (!candidate) return '';
  const parts: string[] = [];
  const latest = candidate.latestEvaluation;
  if (candidate.laterEvaluation && latest) {
    parts.push(
      `później ${latest.verdict} (${gateLabel(latest.policyVersion)})`,
    );
  }
  const used = usage(candidate);
  if (used) parts.push(`w użyciu: ${used}`);
  return parts.length ? ` → ${parts.join(' · ')}` : '';
}

/** Full sentences for the selected learning; null when there is nothing to add. */
export function candidateSummary(
  candidate: GridCorrectionLearningCandidateStatus | null | undefined,
  learningVerdict: string | null | undefined,
): readonly string[] | null {
  if (!candidate) return null;
  const lines: string[] = [];
  const latest = candidate.latestEvaluation;
  if (candidate.laterEvaluation && latest) {
    lines.push(
      `Wynik uczenia${learningVerdict ? ` (${learningVerdict})` : ''} to pierwotna ocena tego przebiegu i nie zmienia się.`,
      `Ten sam kandydat ma nowszą ocenę: ${latest.verdict} (${gateLabel(latest.policyVersion)}, ocena ${latest.evaluationId.slice(0, 8)}).`,
    );
  }
  const used = usage(candidate);
  lines.push(
    used
      ? `Kandydat ${candidate.versionId.slice(0, 8)} jest obecnie ${used}.`
      : `Kandydat ${candidate.versionId.slice(0, 8)} nie jest obecnie używany.`,
  );
  return lines;
}
