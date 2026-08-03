import React, { useEffect, useRef } from 'react';
import {
  View, Text, StyleSheet, Modal, TouchableOpacity, Animated,
  ActivityIndicator, Easing,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT, RADIUS } from '../constants/theme';
import type { SubmitResult } from '../api/gamesApi';

/* ── Reward reveal modal (Phase 39M.3) ──
   Shows the REAL prize returned by
   POST /api/games_v2/sessions/{id}/submit. No mock prizes: when the
   server says `lose` we say so.

   BigCoin prizes are credited by the backend on submit, so we present
   them as already banked. Non-BigCoin prizes (coupons) expose a
   "Save to wallet" action wired to /claim_to_wallet. */

type Props = {
  visible: boolean;
  result: SubmitResult | null;
  onClose: () => void;
  onPlayAgain?: () => void;
  onClaim?: () => void;
  claiming?: boolean;
  claimed?: boolean;
  /** Optional line under the title, e.g. the correct trivia answer. */
  subtitle?: string | null;
};

export default function RewardModal({
  visible, result, onClose, onPlayAgain, onClaim,
  claiming = false, claimed = false, subtitle,
}: Props) {
  const pop = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (visible) {
      pop.setValue(0);
      // Spring reveal, comfortably under 400ms.
      Animated.spring(pop, {
        toValue: 1,
        useNativeDriver: true,
        friction: 7,
        tension: 90,
      }).start();
    } else {
      pop.setValue(0);
    }
  }, [visible, pop]);

  if (!result) return null;

  const won = result.result === 'win';
  const prize = result.prize;
  const bigcoin = Number(result.bigcoin_earned) || 0;
  const isBigCoin = prize?.prize_type === 'bigcoin';
  // Only non-BigCoin prizes need an explicit wallet claim.
  const needsClaim = won && !!prize && !isBigCoin;

  const scale = pop.interpolate({ inputRange: [0, 1], outputRange: [0.82, 1] });

  return (
    <Modal visible={visible} transparent animationType="fade" testID="reward-modal">
      <View style={s.backdrop}>
        <Animated.View
          style={[s.card, { opacity: pop, transform: [{ scale }] }]}
          testID="reward-modal-card"
        >
          <View style={[s.iconWrap, { backgroundColor: won ? '#16a34a15' : COLORS.inputBg }]}>
            <Ionicons
              name={won ? 'trophy' : 'sad-outline'}
              size={40}
              color={won ? COLORS.green : COLORS.textMuted}
            />
          </View>

          <Text style={s.title} testID="reward-title">
            {won ? 'You won!' : 'Not this time'}
          </Text>

          {!!subtitle && (
            <Text style={s.subtitle} testID="reward-subtitle">{subtitle}</Text>
          )}

          {won && prize ? (
            <View style={s.prizeBox} testID="reward-prize">
              <Text style={s.prizeTitle}>{prize.title}</Text>
              {!!prize.description && (
                <Text style={s.prizeDesc}>{prize.description}</Text>
              )}
              {isBigCoin && bigcoin > 0 && (
                <View style={s.coinRow} testID="reward-bigcoin">
                  <Text style={s.coinGlyph}>₿</Text>
                  <Text style={s.coinAmount}>+{bigcoin}</Text>
                  <Text style={s.coinLabel}>BigCoin added to your wallet</Text>
                </View>
              )}
            </View>
          ) : (
            <Text style={s.loseText} testID="reward-lose-text">
              No prize this round — give it another go.
            </Text>
          )}

          {needsClaim && (
            claimed ? (
              <View style={s.claimedRow} testID="reward-claimed">
                <Ionicons name="checkmark-circle" size={16} color={COLORS.green} />
                <Text style={s.claimedText}>Saved to your wallet</Text>
              </View>
            ) : (
              <TouchableOpacity
                style={s.claimBtn}
                onPress={onClaim}
                disabled={claiming}
                activeOpacity={0.85}
                testID="reward-claim-btn"
              >
                {claiming
                  ? <ActivityIndicator size="small" color="#fff" />
                  : <Text style={s.claimBtnText}>SAVE TO WALLET</Text>}
              </TouchableOpacity>
            )
          )}

          <View style={s.actions}>
            {!!onPlayAgain && (
              <TouchableOpacity
                style={s.primaryBtn}
                onPress={onPlayAgain}
                activeOpacity={0.85}
                testID="reward-play-again-btn"
              >
                <Text style={s.primaryBtnText}>PLAY AGAIN</Text>
              </TouchableOpacity>
            )}
            <TouchableOpacity
              style={s.secondaryBtn}
              onPress={onClose}
              activeOpacity={0.85}
              testID="reward-close-btn"
            >
              <Text style={s.secondaryBtnText}>DONE</Text>
            </TouchableOpacity>
          </View>
        </Animated.View>
      </View>
    </Modal>
  );
}

const s = StyleSheet.create({
  backdrop: {
    flex: 1, backgroundColor: 'rgba(15,23,42,0.55)',
    alignItems: 'center', justifyContent: 'center', padding: SPACING.lg,
  },
  card: {
    width: '100%', maxWidth: 380, backgroundColor: COLORS.card,
    borderRadius: RADIUS.xl, padding: SPACING.lg, alignItems: 'center',
    borderWidth: 1, borderColor: COLORS.cardBorder,
    shadowColor: '#000', shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.18, shadowRadius: 24, elevation: 12,
  },
  iconWrap: {
    width: 76, height: 76, borderRadius: 38,
    alignItems: 'center', justifyContent: 'center', marginBottom: SPACING.md,
  },
  title: { fontSize: FONT.xxl, fontWeight: '900', color: COLORS.text, textAlign: 'center' },
  subtitle: {
    fontSize: FONT.sm, color: COLORS.textDim, textAlign: 'center',
    marginTop: 6, lineHeight: 18,
  },
  prizeBox: {
    width: '100%', backgroundColor: COLORS.inputBg, borderRadius: RADIUS.lg,
    padding: SPACING.md, marginTop: SPACING.md, alignItems: 'center',
  },
  prizeTitle: {
    fontSize: FONT.xl, fontWeight: '900', color: COLORS.primary,
    textAlign: 'center',
  },
  prizeDesc: {
    fontSize: FONT.sm, color: COLORS.textDim, textAlign: 'center',
    marginTop: 4, lineHeight: 18,
  },
  coinRow: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    marginTop: 10, flexWrap: 'wrap', justifyContent: 'center',
  },
  coinGlyph: { fontSize: FONT.lg, color: COLORS.gold, fontWeight: '900' },
  coinAmount: { fontSize: FONT.lg, fontWeight: '900', color: COLORS.text },
  coinLabel: { fontSize: FONT.xs, color: COLORS.textDim },
  loseText: {
    fontSize: FONT.sm, color: COLORS.textDim, textAlign: 'center',
    marginTop: SPACING.md, lineHeight: 18,
  },
  claimBtn: {
    marginTop: SPACING.md, backgroundColor: COLORS.gold,
    borderRadius: RADIUS.full, paddingVertical: 12, paddingHorizontal: 24,
    alignSelf: 'stretch', alignItems: 'center', minHeight: 44,
    justifyContent: 'center',
  },
  claimBtnText: { color: '#fff', fontWeight: '800', fontSize: FONT.sm, letterSpacing: 0.6 },
  claimedRow: {
    flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: SPACING.md,
  },
  claimedText: { color: COLORS.green, fontWeight: '700', fontSize: FONT.sm },
  actions: { flexDirection: 'row', gap: 10, marginTop: SPACING.lg, alignSelf: 'stretch' },
  primaryBtn: {
    flex: 1, backgroundColor: COLORS.primary, borderRadius: RADIUS.full,
    paddingVertical: 13, alignItems: 'center',
  },
  primaryBtnText: { color: '#fff', fontWeight: '800', fontSize: FONT.sm, letterSpacing: 0.6 },
  secondaryBtn: {
    flex: 1, backgroundColor: COLORS.inputBg, borderRadius: RADIUS.full,
    paddingVertical: 13, alignItems: 'center',
    borderWidth: 1, borderColor: COLORS.cardBorder,
  },
  secondaryBtnText: { color: COLORS.text, fontWeight: '800', fontSize: FONT.sm, letterSpacing: 0.6 },
});
