import React, { useEffect, useRef } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, Modal, Animated, Pressable,
  Dimensions,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT, RADIUS } from '../constants/theme';
import { useGateStore } from '../stores/gateStore';

const { height: SCREEN_H } = Dimensions.get('window');

export default function ChannelGateModal() {
  const { visible, access, channel, closeGate } = useGateStore();
  const router = useRouter();
  const slideAnim = useRef(new Animated.Value(SCREEN_H)).current;

  useEffect(() => {
    if (visible) {
      Animated.spring(slideAnim, { toValue: 0, useNativeDriver: true, tension: 65, friction: 11 }).start();
    } else {
      slideAnim.setValue(SCREEN_H);
    }
  }, [visible]);

  if (!visible || !access) return null;

  const upgradePath = access.upgrade_path;
  const cta = access.cta || {};
  const reqLevel = cta.required_level;
  const pointsNeeded = cta.points_needed;
  const currentPoints = cta.current_points || 0;
  const requiredPoints = cta.required_points || 0;
  const progressPct = requiredPoints > 0 ? Math.min(100, Math.round((currentPoints / requiredPoints) * 100)) : 0;

  const iconName: any = upgradePath === 'premium' ? 'diamond' : upgradePath === 'earn_badges' ? 'sparkles' : 'lock-closed';
  const iconColor = upgradePath === 'premium' ? '#F5D76E' : upgradePath === 'earn_badges' ? '#22d3ee' : COLORS.primary;

  const handleCta = () => {
    closeGate();
    if (upgradePath === 'premium') {
      router.push('/billing');
    } else if (upgradePath === 'earn_badges') {
      router.push('/passport');
    } else if (cta.href) {
      router.push(cta.href as any);
    }
  };

  const ctaLabel = cta.label || (
    upgradePath === 'premium' ? 'Upgrade to Premium'
    : upgradePath === 'earn_badges' ? 'Earn more points'
    : 'Learn more'
  );

  return (
    <Modal transparent visible={visible} animationType="none" onRequestClose={closeGate}>
      <Pressable style={s.backdrop} onPress={closeGate} testID="channel-gate-modal">
        <Animated.View
          style={[s.sheet, { transform: [{ translateY: slideAnim }] }]}
          accessibilityRole="alert"
          accessibilityLabel="Channel access required"
        >
          <Pressable onPress={() => {}}>
            {/* Close button */}
            <TouchableOpacity style={s.closeBtn} onPress={closeGate} testID="channel-gate-modal-close"
              accessibilityLabel="Close" accessibilityRole="button">
              <Ionicons name="close" size={18} color={COLORS.textDim} />
            </TouchableOpacity>

            {/* Icon */}
            <View style={[s.iconWrap, { borderColor: iconColor }]}>
              <Ionicons name={iconName} size={28} color={iconColor} />
            </View>

            {/* Channel name */}
            <Text style={s.channelName} testID="channel-gate-channel-name">
              {channel?.name || access.channel_name || 'This channel'}
            </Text>

            {/* Message */}
            <Text style={s.headline} testID="channel-gate-message">
              {access.unlock_message || access.message || 'This channel is currently locked.'}
            </Text>

            {/* Progress bar for ambassador tiers */}
            {upgradePath === 'earn_badges' && requiredPoints > 0 && (
              <View style={s.progressBlock} testID="channel-gate-progress">
                <View style={s.progressMeta}>
                  <Text style={s.progressLabel}>{currentPoints} pts</Text>
                  <Text style={s.progressLabel}>{requiredPoints} pts to L{reqLevel}</Text>
                </View>
                <View style={s.progressTrack}>
                  <View style={[s.progressFill, { width: `${progressPct}%`, backgroundColor: iconColor }]} />
                </View>
                <Text style={s.progressNeeded}>{pointsNeeded} more to unlock</Text>
              </View>
            )}

            {/* CTA button */}
            <TouchableOpacity style={s.ctaBtn} onPress={handleCta} testID="channel-gate-cta"
              accessibilityRole="button" accessibilityLabel={ctaLabel} activeOpacity={0.8}>
              <Text style={s.ctaText}>{ctaLabel}</Text>
              <Ionicons name="arrow-forward" size={14} color="#fff" />
            </TouchableOpacity>

            {/* Dismiss */}
            <TouchableOpacity style={s.dismissBtn} onPress={closeGate} testID="channel-gate-dismiss"
              accessibilityRole="button" activeOpacity={0.7}>
              <Text style={s.dismissText}>Stay on free channels</Text>
            </TouchableOpacity>
          </Pressable>
        </Animated.View>
      </Pressable>
    </Modal>
  );
}

const s = StyleSheet.create({
  backdrop: {
    flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'flex-end',
  },
  sheet: {
    backgroundColor: COLORS.card, borderTopLeftRadius: RADIUS.xl, borderTopRightRadius: RADIUS.xl,
    paddingHorizontal: SPACING.xl, paddingTop: SPACING.xl, paddingBottom: SPACING.xxl,
    alignItems: 'center', minHeight: 320,
  },
  closeBtn: {
    position: 'absolute', top: -8, right: -8, padding: 8,
    backgroundColor: COLORS.bg, borderRadius: RADIUS.full, zIndex: 10,
  },
  iconWrap: {
    width: 64, height: 64, borderRadius: 32, borderWidth: 2,
    alignItems: 'center', justifyContent: 'center', backgroundColor: COLORS.bg, marginBottom: SPACING.md,
  },
  channelName: {
    color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700', letterSpacing: 2,
    textTransform: 'uppercase', marginBottom: SPACING.sm,
  },
  headline: {
    color: COLORS.text, fontSize: FONT.lg, fontWeight: '700', textAlign: 'center',
    lineHeight: 24, marginBottom: SPACING.lg,
  },
  progressBlock: { width: '100%', marginBottom: SPACING.lg },
  progressMeta: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6 },
  progressLabel: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700', letterSpacing: 1 },
  progressTrack: { height: 6, backgroundColor: COLORS.cardBorder, borderRadius: 3, overflow: 'hidden' },
  progressFill: { height: 6, borderRadius: 3 },
  progressNeeded: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '700', letterSpacing: 1, marginTop: 6, textAlign: 'center' },
  ctaBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: COLORS.primary, paddingVertical: 16, paddingHorizontal: 28,
    borderRadius: RADIUS.lg, marginBottom: SPACING.md, minWidth: 200, justifyContent: 'center',
  },
  ctaText: { color: '#fff', fontWeight: '800', fontSize: FONT.md, letterSpacing: 0.5 },
  dismissBtn: { padding: 12 },
  dismissText: { color: COLORS.textMuted, fontSize: FONT.sm, fontWeight: '600' },
});
