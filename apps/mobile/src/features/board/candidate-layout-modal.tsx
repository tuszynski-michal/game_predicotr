import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';

import type {
  LayoutCandidate,
  LocalGameConfig,
} from '@/data/local-layout-repository';

import { BoardGrid } from './board-grid';
import { boardColors } from './board-theme';

type Props = {
  candidate: LayoutCandidate | null;
  game: LocalGameConfig;
  onAccept: () => void;
  onClose: () => void;
};

export function CandidateLayoutModal({
  candidate,
  game,
  onAccept,
  onClose,
}: Props) {
  return (
    <Modal
      animationType="fade"
      onRequestClose={onClose}
      statusBarTranslucent
      transparent
      visible={candidate !== null}
    >
      <View style={styles.backdrop}>
        {candidate === null ? null : (
          <View
            accessibilityLabel="Propozycja pełnego layoutu"
            accessibilityViewIsModal
            style={styles.card}
            testID="candidate-modal"
          >
            <Text style={styles.eyebrow}>JEDEN KANDYDAT</Text>
            <Text accessibilityRole="header" style={styles.title}>
              Uzupełnić layout?
            </Text>
            <Text style={styles.sequence}>
              Numer sekwencji: {candidate.sequenceNumber}
            </Text>

            <View style={styles.board}>
              <BoardGrid
                cells={candidate.cells}
                columns={game.columns}
                rows={game.rows}
                symbols={game.symbols}
              />
            </View>

            <Text style={styles.explanation}>
              Lokalny snapshot zawiera tylko jeden layout pasujący do
              wprowadzonego prefiksu.
            </Text>

            <View style={styles.actions}>
              <Pressable
                accessibilityLabel="Zamknij propozycję bez zmiany planszy"
                accessibilityRole="button"
                onPress={onClose}
                style={({ pressed }) => [
                  styles.button,
                  styles.closeButton,
                  pressed && styles.closeButtonPressed,
                ]}
                testID="candidate-close-button"
              >
                <Text style={styles.closeButtonText}>Zamknij</Text>
              </Pressable>
              <Pressable
                accessibilityLabel="Akceptuj i uzupełnij planszę"
                accessibilityRole="button"
                onPress={onAccept}
                style={({ pressed }) => [
                  styles.button,
                  styles.acceptButton,
                  pressed && styles.acceptButtonPressed,
                ]}
                testID="candidate-accept-button"
              >
                <Text style={styles.acceptButtonText}>Akceptuj</Text>
              </Pressable>
            </View>
          </View>
        )}
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  acceptButton: {
    backgroundColor: boardColors.accent,
  },
  acceptButtonPressed: {
    backgroundColor: boardColors.accentPressed,
  },
  acceptButtonText: {
    color: boardColors.textDark,
    fontSize: 15,
    fontWeight: '900',
  },
  actions: {
    flexDirection: 'row',
    gap: 10,
    marginTop: 20,
  },
  backdrop: {
    alignItems: 'center',
    backgroundColor: 'rgba(2, 8, 23, 0.82)',
    flex: 1,
    justifyContent: 'center',
    padding: 18,
  },
  board: {
    marginTop: 18,
  },
  button: {
    alignItems: 'center',
    borderRadius: 12,
    flex: 1,
    justifyContent: 'center',
    minHeight: 48,
    paddingHorizontal: 14,
  },
  card: {
    backgroundColor: boardColors.card,
    borderColor: boardColors.border,
    borderRadius: 20,
    borderWidth: 1,
    maxWidth: 520,
    padding: 20,
    width: '100%',
  },
  closeButton: {
    borderColor: boardColors.border,
    borderWidth: 1,
  },
  closeButtonPressed: {
    backgroundColor: '#1c3654',
  },
  closeButtonText: {
    color: boardColors.text,
    fontSize: 15,
    fontWeight: '800',
  },
  explanation: {
    color: boardColors.muted,
    fontSize: 13,
    lineHeight: 19,
    marginTop: 16,
  },
  eyebrow: {
    color: boardColors.primary,
    fontSize: 11,
    fontWeight: '900',
    letterSpacing: 0.9,
  },
  sequence: {
    color: '#bae6fd',
    fontSize: 14,
    fontWeight: '700',
    marginTop: 8,
  },
  title: {
    color: boardColors.text,
    fontSize: 23,
    fontWeight: '900',
    marginTop: 5,
  },
});
