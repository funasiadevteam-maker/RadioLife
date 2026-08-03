import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ScrollView, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT, RADIUS } from '../constants/theme';

type Channel = {
  slug: string;
  name: string;
  tagline?: string;
  hosts?: { name: string }[];
  cover_color?: string;
  premium_only?: boolean;
  exclusivity_tier?: string;
  access?: { allowed: boolean; upgrade_path?: string };
};

type Props = {
  channels: Channel[];
  activeSlug: string | null;
  switching: string | null;
  isPremium: boolean;
  onSwitch: (slug: string) => void;
  onLocked: (ch: Channel) => void;
};

export default function ChannelSwitcher({ channels, activeSlug, switching, isPremium, onSwitch, onLocked }: Props) {
  return (
    <View style={styles.wrap} testID="channel-switcher">
      <Text style={styles.label}>CHANNELS</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.strip}>
        {channels.map((c) => {
          const active = c.slug === activeSlug;
          const isSwitching = switching === c.slug;
          const access = c.access || { allowed: true };
          const locked = access.allowed === false;
          const tier = c.exclusivity_tier || 'free';
          const isPremiumTier = tier === 'premium' || c.premium_only;
          const isAmbassadorTier = tier?.startsWith('ambassador_');
          const hostsLine = c.hosts?.length ? c.hosts.map(h => h.name).join(' × ') : 'Auto';

          return (
            <TouchableOpacity
              key={c.slug}
              style={[
                styles.chip,
                active && styles.chipActive,
                locked && styles.chipLocked,
                isPremiumTier && styles.chipPremium,
                { borderLeftColor: c.cover_color || COLORS.primary, borderLeftWidth: 3 },
              ]}
              onPress={() => {
                if (active || switching) return;
                if (locked) { onLocked(c); return; }
                onSwitch(c.slug);
              }}
              disabled={!!switching}
              testID={`channel-chip-${c.slug}`}
              activeOpacity={0.7}
            >
              {(isPremiumTier || isAmbassadorTier) && (
                <View style={styles.premiumBadge}>
                  <Ionicons name={locked ? 'lock-closed' : 'diamond'} size={9} color={COLORS.gold} />
                  <Text style={styles.premiumBadgeText}>
                    {isPremiumTier ? 'VIP' : tier?.replace('ambassador_', '').toUpperCase()}
                  </Text>
                </View>
              )}
              <Text style={[styles.chipName, active && styles.chipNameActive]}>{c.name}</Text>
              {c.tagline && <Text style={styles.chipTagline}>{c.tagline}</Text>}
              <Text style={styles.chipHosts}>with {hostsLine}</Text>
              {isSwitching && (
                <View style={styles.switchingOverlay}>
                  <ActivityIndicator size="small" color={COLORS.secondary} />
                  <Text style={styles.switchingText}>TUNING…</Text>
                </View>
              )}
              {active && !isSwitching && (
                <View style={styles.liveTag}>
                  <View style={styles.liveDot} />
                  <Text style={styles.liveText}>LIVE</Text>
                </View>
              )}
              {locked && !isSwitching && (
                <View style={styles.lockedOverlay}>
                  <Ionicons name="lock-closed" size={10} color="#fff" />
                  <Text style={styles.lockedText}>UNLOCK</Text>
                </View>
              )}
            </TouchableOpacity>
          );
        })}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginBottom: SPACING.md },
  label: {
    fontSize: FONT.xs,
    color: COLORS.textDim,
    fontWeight: '700',
    letterSpacing: 2,
    marginBottom: SPACING.sm,
    paddingHorizontal: SPACING.md,
  },
  strip: {
    paddingHorizontal: SPACING.md,
    gap: SPACING.sm,
  },
  chip: {
    width: 150,
    padding: SPACING.sm + 2,
    borderRadius: RADIUS.md,
    backgroundColor: COLORS.card,
    borderWidth: 1,
    borderColor: COLORS.cardBorder,
    position: 'relative',
    overflow: 'hidden',
  },
  chipActive: {
    borderColor: COLORS.primary,
    backgroundColor: 'rgba(255, 45, 149, 0.08)',
  },
  chipLocked: { opacity: 0.6 },
  chipPremium: { borderColor: 'rgba(255, 215, 0, 0.3)' },
  premiumBadge: { flexDirection: 'row', alignItems: 'center', gap: 3, marginBottom: 4 },
  premiumBadgeText: { fontSize: 9, fontWeight: '700', color: COLORS.gold, letterSpacing: 1 },
  chipName: { fontSize: FONT.sm, color: COLORS.text, fontWeight: '700', marginBottom: 2 },
  chipNameActive: { color: COLORS.primary },
  chipTagline: { fontSize: 10, color: COLORS.textDim, marginBottom: 2 },
  chipHosts: { fontSize: 9, color: COLORS.textDim, fontWeight: '600', letterSpacing: 0.5 },
  switchingOverlay: {
    position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
    backgroundColor: 'rgba(10, 12, 24, 0.85)',
    alignItems: 'center', justifyContent: 'center', borderRadius: RADIUS.md,
  },
  switchingText: { fontSize: 9, color: COLORS.secondary, fontWeight: '700', letterSpacing: 1, marginTop: 4 },
  liveTag: { flexDirection: 'row', alignItems: 'center', marginTop: 6, gap: 4 },
  liveDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: COLORS.primary },
  liveText: { fontSize: 9, color: COLORS.primary, fontWeight: '800', letterSpacing: 1.5 },
  lockedOverlay: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 6 },
  lockedText: { fontSize: 9, color: COLORS.textDim, fontWeight: '700', letterSpacing: 1 },
});
