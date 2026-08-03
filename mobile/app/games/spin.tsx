import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView,
  ActivityIndicator, Animated, Easing,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import Svg, { Path, Circle, G, Text as SvgText } from 'react-native-svg';
import { COLORS, SPACING, FONT, RADIUS } from '../../src/constants/theme';
import {
  HOUSE_CAMPAIGNS, fetchCampaign, startSession, submitSession, claimToWallet,
  normalizeGameError, resolveWheelIndex,
} from '../../src/api/gamesApi';
import type { SubmitResult, WheelSegment, GameError } from '../../src/api/gamesApi';
import useBigCoinStore from '../../src/stores/useBigCoinStore';
import RewardModal from '../../src/components/RewardModal';

/* Phase 39M.3 — rewired from the retired Phase 5 endpoint
   (`POST /api/games/spin/play`, which now answers 410 Gone) onto the live
   games_v2 flow: start -> submit -> (claim_to_wallet for coupons).
   Wedge labels/colours come from the server's render_config, so the wheel
   always mirrors the real prize table. */

const CAMPAIGN_ID = HOUSE_CAMPAIGNS.spin;
const FALLBACK_COLORS = ['#ff2d95', '#7BD3F7', '#fdb756', '#a855f7', '#4ade80', '#fb7185'];

const WHEEL_SIZE = 280;
const CX = WHEEL_SIZE / 2;
const CY = WHEEL_SIZE / 2;
const R = WHEEL_SIZE / 2 - 8;

export default function SpinScreen() {
  const router = useRouter();
  const [campaign, setCampaign] = useState<any>(null);
  const [segments, setSegments] = useState<WheelSegment[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [spinDuration, setSpinDuration] = useState(4000);
  const [booting, setBooting] = useState(true);
  const [spinning, setSpinning] = useState(false);
  const [result, setResult] = useState<SubmitResult | null>(null);
  const [showReward, setShowReward] = useState(false);
  const [claiming, setClaiming] = useState(false);
  const [claimed, setClaimed] = useState(false);
  const [error, setError] = useState<GameError | null>(null);

  const spinAnim = React.useRef(new Animated.Value(0)).current;
  const currentAngle = React.useRef(0);
  const addOptimistic = useBigCoinStore((s) => s.addOptimistic);
  const refreshBalance = useBigCoinStore((s) => s.refresh);

  /* Open a session up-front so the wheel renders the server's real
     segments before the first spin. */
  const boot = useCallback(async () => {
    setBooting(true);
    setError(null);
    setResult(null);
    setShowReward(false);
    setClaimed(false);
    try {
      const c = await fetchCampaign(CAMPAIGN_ID).catch(() => null);
      if (c) setCampaign(c);
      const s = await startSession(CAMPAIGN_ID);
      setSessionId(s.session_id);
      const segs: WheelSegment[] = (s?.render_config?.segments || []).map(
        (x: any, i: number) => ({
          label: x.label ?? `Prize ${i + 1}`,
          color: x.color || FALLBACK_COLORS[i % FALLBACK_COLORS.length],
          idx: typeof x.idx === 'number' ? x.idx : i,
        }),
      );
      setSegments(segs);
      setSpinDuration(Number(s?.render_config?.spin_duration_ms) || 4000);
    } catch (e) {
      setError(normalizeGameError(e));
    } finally {
      setBooting(false);
    }
  }, []);

  useEffect(() => { boot(); }, [boot]);

  const handleSpin = async () => {
    if (spinning || !sessionId || !segments.length) return;
    setSpinning(true);
    try {
      const res = await submitSession(sessionId, {});
      // The wheel is cosmetic — land it on the wedge matching the real prize.
      const target = resolveWheelIndex(segments, res.prize);
      const sliceSize = 360 / segments.length;
      const desired = ((360 - (target * sliceSize + sliceSize / 2)) % 360 + 360) % 360;
      const cur = ((currentAngle.current % 360) + 360) % 360;
      const delta = ((desired - cur) % 360 + 360) % 360;
      const startAngle = currentAngle.current;
      const endAngle = startAngle + 360 * 5 + delta;
      currentAngle.current = endAngle;

      spinAnim.setValue(startAngle);
      Animated.timing(spinAnim, {
        toValue: endAngle,
        duration: spinDuration,
        easing: Easing.out(Easing.cubic),
        useNativeDriver: true,
      }).start(() => {
        setResult(res);
        setShowReward(true);
        setSpinning(false);
        setSessionId(null); // session consumed
        if (Number(res.bigcoin_earned) > 0) {
          addOptimistic(Number(res.bigcoin_earned));
          refreshBalance();
        }
      });
    } catch (e) {
      setSpinning(false);
      setError(normalizeGameError(e));
    }
  };

  const handleClaim = async () => {
    if (!result) return;
    setClaiming(true);
    try {
      await claimToWallet(result.session_id);
      setClaimed(true);
      refreshBalance();
    } catch (e) {
      setError(normalizeGameError(e));
    } finally {
      setClaiming(false);
    }
  };

  const wedgeAngle = 360 / Math.max(1, segments.length);

  const wedges = segments.map((s, i) => {
    const startAngle = i * wedgeAngle - 90;
    const endAngle = (i + 1) * wedgeAngle - 90;
    const startRad = (startAngle * Math.PI) / 180;
    const endRad = (endAngle * Math.PI) / 180;
    const x1 = CX + R * Math.cos(startRad);
    const y1 = CY + R * Math.sin(startRad);
    const x2 = CX + R * Math.cos(endRad);
    const y2 = CY + R * Math.sin(endRad);
    const large = wedgeAngle > 180 ? 1 : 0;
    const path = `M ${CX} ${CY} L ${x1} ${y1} A ${R} ${R} 0 ${large} 1 ${x2} ${y2} Z`;
    const labelRad = ((startAngle + endAngle) / 2 * Math.PI) / 180;
    const labelX = CX + (R * 0.6) * Math.cos(labelRad);
    const labelY = CY + (R * 0.6) * Math.sin(labelRad);
    const labelAngle = (startAngle + endAngle) / 2 + 90;
    return { ...s, path, labelX, labelY, labelAngle };
  });

  const rotation = spinAnim.interpolate({
    inputRange: [0, 360],
    outputRange: ['0deg', '360deg'],
  });

  if (booting) {
    return (
      <SafeAreaView style={styles.screen} testID="spin-loading">
        <View style={styles.centerFill}>
          <ActivityIndicator size="large" color={COLORS.primary} />
          <Text style={styles.spinningText}>Loading the wheel…</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (error && !result) {
    return (
      <SafeAreaView style={styles.screen} testID="spin-error">
        <View style={styles.topBar}>
          <TouchableOpacity onPress={() => router.back()} style={styles.backBtn} testID="spin-back-btn">
            <Ionicons name="chevron-back" size={20} color={COLORS.text} />
          </TouchableOpacity>
          <Text style={styles.topTitle}>Spin & Win</Text>
          <View style={{ width: 32 }} />
        </View>
        <View style={styles.body}>
          <View style={styles.unavailableCard}>
            <Ionicons name="alert-circle-outline" size={40} color={COLORS.textMuted} />
            <Text style={styles.unavailableTitle}>{error.title}</Text>
            <Text style={styles.unavailableDesc}>{error.message}</Text>
            {error.retryable && (
              <TouchableOpacity style={styles.spinBtn} onPress={boot} testID="spin-retry-btn">
                <Ionicons name="refresh" size={16} color="#fff" />
                <Text style={styles.spinBtnText}>TRY AGAIN</Text>
              </TouchableOpacity>
            )}
            <TouchableOpacity onPress={() => router.back()} testID="spin-go-back">
              <Text style={styles.linkText}>Back to Games</Text>
            </TouchableOpacity>
          </View>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.screen} testID="spin-screen">
      {/* Header */}
      <View style={styles.topBar}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn} testID="spin-back-btn">
          <Ionicons name="chevron-back" size={20} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={styles.topTitle}>Spin & Win</Text>
        <View style={{ width: 32 }} />
      </View>

      <View style={styles.body}>
        <Text style={styles.subtitle}>
          {campaign?.description || 'Give the wheel a spin and win real BigCoin.'}
        </Text>

        {/* Pointer */}
        <View style={styles.pointerWrap}>
          <View style={styles.pointer} />
        </View>

        {/* Wheel */}
        <Animated.View style={[styles.wheelWrap, { transform: [{ rotate: rotation }] }]} testID="spin-wheel">
          <Svg width={WHEEL_SIZE} height={WHEEL_SIZE}>
            {wedges.map((w, i) => (
              <G key={i}>
                <Path d={w.path} fill={w.color} stroke={COLORS.bg} strokeWidth={2} />
                <SvgText
                  x={w.labelX} y={w.labelY}
                  fill="#fff" fontSize={11} fontWeight="900"
                  textAnchor="middle" alignmentBaseline="middle"
                  rotation={w.labelAngle}
                  origin={`${w.labelX}, ${w.labelY}`}
                >
                  {w.label}
                </SvgText>
              </G>
            ))}
            <Circle cx={CX} cy={CY} r={24} fill={COLORS.bg} stroke="#a855f7" strokeWidth={3} />
          </Svg>
        </Animated.View>

        {/* Spin button / spinning / play-again */}
        {!spinning && sessionId && (
          <TouchableOpacity style={styles.spinBtn} onPress={handleSpin} testID="do-spin-btn">
            <Ionicons name="sparkles" size={16} color="#fff" />
            <Text style={styles.spinBtnText}>SPIN!</Text>
          </TouchableOpacity>
        )}

        {spinning && (
          <View style={styles.spinningRow}>
            <ActivityIndicator size="small" color={COLORS.primary} />
            <Text style={styles.spinningText}>Spinning...</Text>
          </View>
        )}

        {!spinning && !sessionId && !!result && (
          <TouchableOpacity style={styles.spinBtn} onPress={boot} testID="spin-again-btn">
            <Ionicons name="refresh" size={16} color="#fff" />
            <Text style={styles.spinBtnText}>SPIN AGAIN</Text>
          </TouchableOpacity>
        )}
      </View>

      <RewardModal
        visible={showReward}
        result={result}
        claiming={claiming}
        claimed={claimed}
        onClaim={handleClaim}
        onClose={() => setShowReward(false)}
        onPlayAgain={() => { setShowReward(false); boot(); }}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: COLORS.bg },
  centerFill: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12 },
  linkText: {
    color: COLORS.primary, fontWeight: '700', fontSize: FONT.sm,
    marginTop: SPACING.md,
  },
  topBar: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: SPACING.lg, paddingVertical: SPACING.md,
  },
  backBtn: { width: 32, height: 32, alignItems: 'center', justifyContent: 'center' },
  topTitle: { fontSize: FONT.lg, fontWeight: '900', color: COLORS.text },
  body: { flex: 1, alignItems: 'center', paddingTop: SPACING.lg },
  subtitle: {
    fontSize: FONT.sm, color: COLORS.textDim, textAlign: 'center',
    marginBottom: SPACING.lg, paddingHorizontal: SPACING.xl,
  },
  pointerWrap: { alignItems: 'center', marginBottom: -8, zIndex: 10 },
  pointer: {
    width: 0, height: 0,
    borderLeftWidth: 12, borderRightWidth: 12, borderTopWidth: 18,
    borderLeftColor: 'transparent', borderRightColor: 'transparent',
    borderTopColor: '#a855f7',
  },
  wheelWrap: { width: WHEEL_SIZE, height: WHEEL_SIZE },
  spinBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: COLORS.primary, borderRadius: RADIUS.full,
    paddingHorizontal: 32, paddingVertical: 16, marginTop: SPACING.xl,
  },
  spinBtnText: { color: '#fff', fontSize: FONT.lg, fontWeight: '900', letterSpacing: 1 },
  spinningRow: {
    flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: SPACING.xl,
  },
  spinningText: { color: COLORS.textDim, fontSize: FONT.md },
  resultCard: {
    alignItems: 'center', marginTop: SPACING.xl,
    backgroundColor: COLORS.card, borderRadius: RADIUS.lg,
    borderWidth: 1, borderColor: COLORS.cardBorder,
    padding: SPACING.xl, width: '85%',
  },
  resultTitle: {
    fontSize: FONT.xl, fontWeight: '900', color: COLORS.gold,
    marginTop: 8, marginBottom: 4,
  },
  resultSub: { fontSize: FONT.sm, color: COLORS.textDim, marginBottom: SPACING.md },
  unavailableCard: {
    alignItems: 'center', marginTop: SPACING.md,
    backgroundColor: COLORS.card, borderRadius: RADIUS.lg,
    borderWidth: 1, borderColor: COLORS.cardBorder,
    padding: SPACING.xl, width: '85%',
  },
  unavailableTitle: { fontSize: FONT.xl, fontWeight: '900', color: COLORS.text, marginTop: 12 },
  unavailableDesc: { fontSize: FONT.sm, color: COLORS.textDim, textAlign: 'center', marginTop: 8, lineHeight: 20 },
});
