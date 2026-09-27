import type {
  AnnotationState,
  Source,
} from '../../../../packages/vision-lab-api-client/src/index';
import {
  boardStatus,
  photoReviewStatus,
  sourceAnnotations,
} from './annotation-status';

export function quickReviewEligible(source: Source, state: AnnotationState) {
  const rows = sourceAnnotations(state, source.id);
  return (
    rows.some((row) => boardStatus(row) === 'full') &&
    photoReviewStatus(rows, state.photo_reviews?.[source.id], source.sha256)
      .status === 'review'
  );
}

export function quickReviewQueue(
  sources: Source[],
  state: AnnotationState,
  game = '',
) {
  return sources.filter(
    (source) =>
      (!game || source.game_id === game) && quickReviewEligible(source, state),
  );
}

export function nextQuickReview(
  sources: Source[],
  state: AnnotationState,
  start: number,
) {
  for (let index = start; index < sources.length; index++) {
    if (quickReviewEligible(sources[index], state)) return index;
  }
  return sources.length;
}
