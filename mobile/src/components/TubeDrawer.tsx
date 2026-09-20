import React from 'react';
import {
  View, Text, StyleSheet, Pressable, Modal, ScrollView, Dimensions,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { TUBE, TSPACE, TRADIUS, TFONT } from '../constants/tube';

const PANEL_W = Math.min(300, Dimensions.get('window').width * 0.82);

type Item = { icon: any; label: string; path: string; accent?: string };

const PRIMARY: Item[] = [
  { icon: 'home', label: 'Home', path: '/(tabs)/home' },
  { icon: 'radio', label: 'Listen', path: '/(tabs)/listen' },
  { icon: 'storefront', label: 'Shop & Eat', path: '/(tabs)/shop' },
  { icon: 'game-controller', label: 'Play', path: '/(tabs)/games' },
  { icon: 'wallet', label: 'Wallet', path: '/(tabs)/wallet' },
];

const DISCOVER: Item[] = [
  { icon: 'newspaper', label: 'News', path: '/(tabs)/news', accent: TUBE.live },
  { icon: 'mic', label: 'Podcasts', path: '/(tabs)/podcasts', accent: TUBE.magenta },
  { icon: 'help-circle', label: 'Trivia', path: '/(tabs)/trivia', accent: TUBE.electric },
  { icon: 'ribbon', label: 'Passport', path: '/(tabs)/passport', accent: TUBE.gold },
  { icon: 'globe', label: 'All stations', path: '/stations', accent: TUBE.green },
  { icon: 'person', label: 'Profile', path: '/(tabs)/profile' },
];

export default function TubeDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const insets = useSafeAreaInsets();
  const router = useRouter();

  const go = (path: string) => { onClose(); setTimeout(() => router.push(path as any), 60); };

  const Row = ({ it }: { it: Item }) => (
    <Pressable style={s.row} testID={`drawer-${it.label.toLowerCase().replace(/\s+/g, '-')}`}
      onPress={() => go(it.path)} android_ripple={{ color: TUBE.line }}>
      <View style={[s.rowIcon, { backgroundColor: (it.accent || TUBE.electric) + '22' }]}>
        <Ionicons name={it.icon} size={18} color={it.accent || TUBE.electric} />
      </View>
      <Text style={s.rowLabel}>{it.label}</Text>
    </Pressable>
  );

  return (
    <Modal visible={open} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={s.backdrop} onPress={onClose} testID="drawer-backdrop" />
      <View style={[s.panel, { paddingTop: insets.top + TSPACE.md, width: PANEL_W }]} testID="tube-drawer">
        <View style={s.brandRow}>
          <View style={s.brandDot} />
          <Text style={s.brand}>FUUSIC<Text style={{ color: TUBE.textMuted }}>.app</Text></Text>
        </View>
        <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: insets.bottom + 24 }}>
          {PRIMARY.map((it) => <Row key={it.label} it={it} />)}
          <View style={s.divider} />
          <Text style={s.groupLabel}>DISCOVER</Text>
          {DISCOVER.map((it) => <Row key={it.label} it={it} />)}
        </ScrollView>
      </View>
    </Modal>
  );
}

const s = StyleSheet.create({
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.6)' },
  panel: {
    position: 'absolute', left: 0, top: 0, bottom: 0,
    backgroundColor: TUBE.elevated, borderRightWidth: 1, borderRightColor: TUBE.line,
    paddingHorizontal: TSPACE.sm,
  },
  brandRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: TSPACE.sm, marginBottom: TSPACE.lg },
  brandDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: TUBE.electric },
  brand: { color: TUBE.text, fontSize: TFONT.lg, fontWeight: '900' },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 11, paddingHorizontal: TSPACE.sm, borderRadius: TRADIUS.md },
  rowIcon: { width: 34, height: 34, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  rowLabel: { color: TUBE.text, fontSize: TFONT.md, fontWeight: '700' },
  divider: { height: 1, backgroundColor: TUBE.line, marginVertical: TSPACE.md, marginHorizontal: TSPACE.sm },
  groupLabel: { color: TUBE.textMuted, fontSize: TFONT.xs, fontWeight: '800', letterSpacing: 2, paddingHorizontal: TSPACE.sm, marginBottom: 6 },
});
