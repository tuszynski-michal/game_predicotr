import type {
  AdminApiClient,
  PayoutRuleCreate,
  PayoutRuleResponse,
  PayoutRuleUpdate,
  RulesVersionSymbolResponse,
  RulesVersionSymbolUpdate,
} from '@game-predictor/admin-api-client';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';
import type { ValidatedPayoutConfiguration } from './payout-rules-state.ts';

export type PayoutRulesClient = Pick<
  AdminApiClient,
  | 'createPayoutRule'
  | 'listPayoutRules'
  | 'listRulesVersionSymbols'
  | 'listSymbols'
  | 'updatePayoutRule'
  | 'updateRulesVersionSymbol'
>;

export type SavePayoutConfigurationResult =
  | {
      readonly configuration: RulesVersionSymbolResponse;
      readonly ok: true;
      readonly payoutRules: readonly PayoutRuleResponse[];
    }
  | { readonly error: string; readonly ok: false };

export async function savePayoutConfiguration(
  api: PayoutRulesClient,
  rulesVersionId: string,
  symbolId: string,
  existing: readonly PayoutRuleResponse[],
  draft: ValidatedPayoutConfiguration,
): Promise<SavePayoutConfigurationResult> {
  try {
    const configurationResult = await api.updateRulesVersionSymbol(
      rulesVersionId,
      symbolId,
      {
        isActive: draft.isActive,
        minimumMatchLength: draft.minimumMatchLength,
      } satisfies RulesVersionSymbolUpdate,
    );
    if (
      configurationResult.error !== undefined ||
      configurationResult.data === undefined
    ) {
      return {
        error: apiErrorMessage(
          configurationResult.error,
          'Nie udało się zapisać minimum symbolu.',
        ),
        ok: false,
      };
    }

    const saved: PayoutRuleResponse[] = [];
    for (const payout of draft.payouts) {
      const current = existing.find(
        (item) =>
          item.symbolId === symbolId && item.matchLength === payout.matchLength,
      );
      const result =
        current === undefined
          ? await api.createPayoutRule(rulesVersionId, {
              isActive: true,
              matchLength: payout.matchLength,
              payoutCredits: payout.payoutCredits,
              symbolId,
            } satisfies PayoutRuleCreate)
          : await api.updatePayoutRule(rulesVersionId, current.id, {
              isActive: true,
              payoutCredits: payout.payoutCredits,
            } satisfies PayoutRuleUpdate);
      if (result.error !== undefined || result.data === undefined) {
        return {
          error: apiErrorMessage(
            result.error,
            `Minimum zapisano, ale nie udało się zapisać wypłaty dla długości ${payout.matchLength}. Ponów zapis.`,
          ),
          ok: false,
        };
      }
      saved.push(result.data);
    }
    if (draft.archiveUnlistedPayouts === true) {
      const listed = new Set(draft.payouts.map((item) => item.matchLength));
      const unlisted = existing.filter(
        (item) =>
          item.symbolId === symbolId &&
          item.isActive &&
          !listed.has(item.matchLength),
      );
      for (const payout of unlisted) {
        const result = await api.updatePayoutRule(rulesVersionId, payout.id, {
          isActive: false,
        } satisfies PayoutRuleUpdate);
        if (result.error !== undefined || result.data === undefined) {
          return {
            error: apiErrorMessage(
              result.error,
              `Wypłaty zapisano, ale nie udało się wyłączyć wypłaty dla ${payout.matchLength} sztuk. Ponów zapis.`,
            ),
            ok: false,
          };
        }
        saved.push(result.data);
      }
    }
    return {
      configuration: configurationResult.data,
      ok: true,
      payoutRules: saved,
    };
  } catch {
    return {
      error:
        'Połączenie z lokalnym Admin API zostało przerwane. Ponów zapis konfiguracji.',
      ok: false,
    };
  }
}
