import React, { useState, useEffect } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView,
  ActivityIndicator, Alert, Animated, Easing,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import Svg, { Path, Circle, G, Text as SvgText } from 'react-native-svg';
import api from '../../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS } from '../../../src/constants/theme';

const WHEEL_SIZE = 260;
const CX = WHEEL_SIZE / 2;
const CY = WHEEL_SIZE / 2;
const R = WHEEL_SIZE / 2 - 8;

export default function CampaignGameScreen() {
  const { campaignId } = useLocalSearchParams<{ campaignId: string }>();
  const router = useRouter();
  const [meta, setMeta] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [playing, setPlaying] = useState(false);
  const [outcome, setOutcome] = useState<any>(null);
  const [scratchRevealed, setScratchRevealed] = useState<number[]>([]);
  const spinAnim = React.useRef(new Animated.Value(0)).current;
  const currentAngle = React.useRef(0);

  useEffect(() => {
    if (!campaignId) return;
    (async () => {
      try {
        const { data } = await api.get(`/games/${campaignId}`);
        setMeta(data);
      } catch (e: any) {
        Alert.alert('Error', e?.response?.data?.detail?.code || e.message || 'Load failed');
        router.back();
      } finally { setLoading(false); }
    })();
  }, [campaignId]);

  if (loading) {
    return (
      <SafeAreaView style={s.screen} testID="campaign-game-loading">
        <View style={s.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
      </SafeAreaView>
    );
  }

  if (!meta) return null;

  const canPlay = meta.eligibility?.can_play;
  const prizes = meta.prizes || [];

  const play = async () => {
    if (playing) return;
    setPlaying(true);
    try {
      const { data } = await api.post(`/games/${campaignId}/play`, {});
      const idx = prizes.findIndex((p: any) => p.prize_id === data.outcome_prize_id);

      if (meta.game_type === 'spin_win') {
        const wedgeAngle = 360 / prizes.length;
        const targetAngle = 360 * 6 + (360 - (idx * wedgeAngle + wedgeAngle / 2));
        const startAngle = currentAngle.current;
        const endAngle = startAngle + targetAngle;
        currentAngle.current = endAngle;

        spinAnim.setValue(startAngle);
        Animated.timing(spinAnim, {
          toValue: endAngle,
          duration: 4000,
          easing: Easing.out(Easing.cubic),
          useNativeDriver: true,
        }).start(() => {
          setOutcome(data);
          setPlaying(false);
        });
      } else {
        setScratchRevealed([0, 1, 2]);
        setTimeout(() => {
          setOutcome(data);
          setPlaying(false);
        }, 1200);
      }
    } catch (e: any) {
      const code = e?.response?.data?.detail?.code || 'error';
      if (code === 'max_plays_reached') Alert.alert('Limit', "You've already played today.");
      else if (code === 'sold_out') Alert.alert('Sold Out', 'All prizes claimed.');
      else Alert.alert('Error', `Play failed: ${code}`);
      setPlaying(false);
    }
  };

  const rotation = spinAnim.interpolate({
    inputRange: [0, 360],
    outputRange: ['0deg', '360deg'],
  });

  return (
    <SafeAreaView style={s.screen} testID="campaign-game-screen">
      {/* Header */}
      <View style={s.topBar}>
        <TouchableOpacity onPress={() => router.back()} style={s.backBtn} testID="campaign-game-back">
          <Ionicons name="chevron-back" size={20} color={COLORS.text} />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          {meta.merchant_name && (
            <Text style={s.merchant}>{meta.merchant_name.toUpperCase()}</Text>
          )}
          <Text style={s.title} numberOfLines={1} testID="campaign-game-name">{meta.name}</Text>
        </View>
      </View>

      <ScrollView contentContainerStyle={s.bodyContent}>
        {meta.description && <Text style={s.desc}>{meta.description}</Text>}

        {/* Not eligible */}
        {!canPlay && !outcome && (
          <View style={s.blockedCard} testID="campaign-game-blocked">
            <Ionicons name="sparkles-outline" size={28} color={COLORS.textMuted} />
            <Text style={s.blockedTitle}>
              {meta.eligibility?.reason === 'max_plays_reached' ? "You've already played"
                : meta.eligibility?.reason === 'sold_out' ? 'All prizes claimed'
                : meta.eligibility?.reason === 'ended' ? 'This game has ended'
                : "Can't play right now"}
            </Text>
          </View>
        )}

        {/* Spin Wheel */}
        {canPlay && meta.game_type === 'spin_win' && prizes.length > 0 && (
          <View style={s.wheelSection} testID="campaign-spin-wheel">
            <View style={s.pointerWrap}><View style={s.pointer} /></View>
            <Animated.View style={{ transform: [{ rotate: rotation }] }}>
              <Svg width={WHEEL_SIZE} height={WHEEL_SIZE}>
                {prizes.map((p: any, i: number) => {
                  const wedge = 360 / prizes.length;
                  const start = i * wedge - 90;
                  const end = (i + 1) * wedge - 90;
                  const sR = (start * Math.PI) / 180;
                  const eR = (end * Math.PI) / 180;
                  const x1 = CX + R * Math.cos(sR);
                  const y1 = CY + R * Math.sin(sR);
                  const x2 = CX + R * Math.cos(eR);
                  const y2 = CY + R * Math.sin(eR);
                  const large = wedge > 180 ? 1 : 0;
                  const path = `M ${CX} ${CY} L ${x1} ${y1} A ${R} ${R} 0 ${large} 1 ${x2} ${y2} Z`;
                  const lR = ((start + end) / 2 * Math.PI) / 180;
                  const lX = CX + (R * 0.6) * Math.cos(lR);
                  const lY = CY + (R * 0.6) * Math.sin(lR);
                  const lA = (start + end) / 2 + 90;
                  return (
                    <G key={i}>
                      <Path d={path} fill={p.display_color || '#a855f7'} stroke={COLORS.bg} strokeWidth={2} />
                      <SvgText x={lX} y={lY} fill="#fff" fontSize={10} fontWeight="900"
                        textAnchor="middle" alignmentBaseline="middle"
                        rotation={lA} origin={`${lX}, ${lY}`}>
                        {(p.display_label || '').slice(0, 10)}
                      </SvgText>
                    </G>
                  );
                })}
                <Circle cx={CX} cy={CY} r={22} fill={COLORS.bg} stroke="#a855f7" strokeWidth={3} />
              </Svg>
            </Animated.View>
            <TouchableOpacity style={[s.playBtn, playing && { opacity: 0.5 }]}
              onPress={play} disabled={playing || !!outcome} testID="campaign-spin-btn">
              <Text style={s.playBtnText}>{playing ? '...' : 'SPIN'}</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Scratch Grid */}
        {canPlay && meta.game_type === 'scratch_win' && (
          <View style={s.scratchSection} testID="campaign-scratch-grid">
            <View style={s.scratchGrid}>
              {Array.from({ length: 9 }).map((_, i) => {
                const isRev = scratchRevealed.includes(i);
                return (
                  <View key={i} style={[s.scratchCell, isRev && s.scratchCellRev]}
                    testID={`campaign-scratch-cell-${i}`}>
                    <Text style={s.scratchCellText}>
                      {isRev && outcome ? (outcome.outcome_label || '').slice(0, 6) : '?'}
                    </Text>
                  </View>
                );
              })}
            </View>
            <TouchableOpacity
              style={[s.playBtn, (playing || scratchRevealed.length > 0) && { opacity: 0.5 }]}
              onPress={play}
              disabled={playing || scratchRevealed.length > 0}
              testID="campaign-scratch-btn"
            >
              <Text style={s.playBtnText}>
                {playing ? '...' : scratchRevealed.length > 0 ? 'Revealed' : 'SCRATCH!'}
              </Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Result */}
        {outcome && (
          <View style={s.resultCard} testID="campaign-game-result">
            {outcome.won ? (
              <>
                <Ionicons name="trophy" size={36} color={COLORS.gold} />
                <Text style={s.resultWonLabel}>You won!</Text>
                <Text style={s.resultTitle} testID="campaign-game-result-label">
                  {outcome.outcome_label}
                </Text>
                {outcome.code && (
                  <View style={s.codeBadge}>
                    <Text style={s.codeText} testID="campaign-game-result-code">{outcome.code}</Text>
                  </View>
                )}
                {outcome.points_amount > 0 && (
                  <Text style={s.pointsText}>+{outcome.points_amount} points added</Text>
                )}
                <TouchableOpacity style={s.walletBtn} onPress={() => router.replace('/(tabs)/wallet')}
                  testID="campaign-game-view-wallet">
                  <Text style={s.walletBtnText}>View in Wallet</Text>
                  <Ionicons name="chevron-forward" size={14} color="#fff" />
                </TouchableOpacity>
              </>
            ) : (
              <>
                <Ionicons name="sparkles-outline" size={36} color={COLORS.textMuted} />
                <Text style={s.resultLostLabel}>So close...</Text>
                <Text style={s.resultTitle}>Better luck next time!</Text>
                <TouchableOpacity style={s.closeResultBtn} onPress={() => router.back()}
                  testID="campaign-game-close-result">
                  <Text style={s.closeResultText}>Close</Text>
                </TouchableOpacity>
              </>
            )}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: COLORS.bg },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  topBar: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    paddingHorizontal: SPACING.lg, paddingVertical: SPACING.md,
  },
  backBtn: { width: 32, height: 32, alignItems: 'center', justifyContent: 'center' },
  merchant: { fontSize: 9, fontWeight: '700', color: COLORS.textMuted, letterSpacing: 1 },
  title: { fontSize: FONT.xl, fontWeight: '900', color: COLORS.text },
  bodyContent: { padding: SPACING.lg, alignItems: 'center' },
  desc: { fontSize: FONT.sm, color: COLORS.textDim, textAlign: 'center', marginBottom: SPACING.lg },

  blockedCard: {
    backgroundColor: COLORS.card, borderRadius: RADIUS.lg,
    borderWidth: 1, borderColor: COLORS.cardBorder,
    padding: SPACING.xl, alignItems: 'center', width: '100%',
  },
  blockedTitle: { fontSize: FONT.lg, fontWeight: '800', color: COLORS.text, marginTop: 8, textAlign: 'center' },

  // Wheel
  wheelSection: { alignItems: 'center', marginBottom: SPACING.lg },
  pointerWrap: { alignItems: 'center', marginBottom: -8, zIndex: 10 },
  pointer: {
    width: 0, height: 0,
    borderLeftWidth: 12, borderRightWidth: 12, borderTopWidth: 18,
    borderLeftColor: 'transparent', borderRightColor: 'transparent',
    borderTopColor: '#a855f7',
  },
  playBtn: {
    backgroundColor: COLORS.primary, borderRadius: RADIUS.full,
    paddingHorizontal: 40, paddingVertical: 16, marginTop: SPACING.lg,
  },
  playBtnText: { color: '#fff', fontSize: FONT.lg, fontWeight: '900', letterSpacing: 1 },

  // Scratch
  scratchSection: { alignItems: 'center', marginBottom: SPACING.lg },
  scratchGrid: {
    flexDirection: 'row', flexWrap: 'wrap', width: 252, gap: 6,
    backgroundColor: COLORS.inputBg, borderRadius: RADIUS.lg, padding: 10,
  },
  scratchCell: {
    width: 72, height: 72, borderRadius: RADIUS.md,
    backgroundColor: '#a855f7', alignItems: 'center', justifyContent: 'center',
  },
  scratchCellRev: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder },
  scratchCellText: { fontSize: FONT.sm, fontWeight: '800', color: '#fff' },

  // Result
  resultCard: {
    backgroundColor: COLORS.card, borderRadius: RADIUS.lg,
    borderWidth: 1, borderColor: COLORS.cardBorder,
    padding: SPACING.xl, alignItems: 'center', width: '100%',
  },
  resultWonLabel: { fontSize: 10, fontWeight: '700', color: COLORS.green, letterSpacing: 0.6, marginTop: 8 },
  resultLostLabel: { fontSize: 10, fontWeight: '700', color: COLORS.textMuted, letterSpacing: 0.6, marginTop: 8 },
  resultTitle: { fontSize: FONT.xxl, fontWeight: '900', color: COLORS.text, marginTop: 4, textAlign: 'center' },
  codeBadge: {
    backgroundColor: COLORS.inputBg, borderRadius: RADIUS.md,
    paddingHorizontal: 14, paddingVertical: 8, marginTop: 12,
  },
  codeText: { fontVariant: ['tabular-nums'], fontSize: FONT.lg, fontWeight: '900', color: COLORS.text, letterSpacing: 2 },
  pointsText: { fontSize: FONT.sm, color: COLORS.textDim, marginTop: 8 },
  walletBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: COLORS.primary, borderRadius: RADIUS.full,
    paddingHorizontal: 24, paddingVertical: 14, marginTop: SPACING.lg,
  },
  walletBtnText: { color: '#fff', fontWeight: '800', fontSize: FONT.md },
  closeResultBtn: {
    backgroundColor: COLORS.inputBg, borderRadius: RADIUS.full,
    paddingHorizontal: 24, paddingVertical: 14, marginTop: SPACING.lg,
  },
  closeResultText: { color: COLORS.textDim, fontWeight: '700', fontSize: FONT.md },
});
