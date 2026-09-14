import React from 'react';
import { View, Text, Pressable, StyleSheet, ScrollView } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { TUBE, TSPACE, TRADIUS, TFONT } from '../../src/constants/tube';

const ITEMS = [
  { key: 'lobbies', icon: 'chatbubbles', title: 'Lobbies', sub: 'Listen together, live', to: '/lobbies', tint: TUBE.electric },
  { key: 'leaderboard', icon: 'trophy', title: 'Leaderboard', sub: 'Top listeners this week', to: '/leaderboard', tint: TUBE.gold },
  { key: 'passport', icon: 'ribbon', title: 'Passport', sub: 'Your badges & streaks', to: '/(tabs)/passport', tint: TUBE.magenta },
  { key: 'trivia', icon: 'sparkles', title: 'Trivia rooms', sub: 'Play with friends', to: '/(tabs)/trivia', tint: TUBE.green },
  { key: 'predict', icon: 'analytics', title: 'Predict & Win', sub: 'Call it, win BigPoints', to: '/games/predict', tint: TUBE.pink },
];

export default function SocialScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  return (
    <View style={s.screen} testID="social-screen">
      <View style={[s.header, { paddingTop: insets.top + 10 }]}>
        <Text style={s.title}>Social</Text>
        <Text style={s.sub}>Lobbies, leaderboards & community</Text>
      </View>
      <ScrollView contentContainerStyle={{ padding: TSPACE.md, paddingBottom: 110, gap: 12 }}
        showsVerticalScrollIndicator={false}>
        {ITEMS.map((it) => (
          <Pressable key={it.key} testID={`social-${it.key}`} style={s.card} onPress={() => router.push(it.to as any)}>
            <View style={[s.icon, { backgroundColor: `${it.tint}22` }]}>
              <Ionicons name={it.icon as any} size={22} color={it.tint} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={s.cardTitle}>{it.title}</Text>
              <Text style={s.cardSub}>{it.sub}</Text>
            </View>
            <Ionicons name="chevron-forward" size={18} color={TUBE.textMuted} />
          </Pressable>
        ))}
      </ScrollView>
    </View>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: TUBE.bg },
  header: { paddingHorizontal: TSPACE.md, paddingBottom: TSPACE.sm, borderBottomWidth: 1, borderBottomColor: TUBE.line, backgroundColor: TUBE.bg },
  title: { color: TUBE.text, fontSize: TFONT.xxl, fontWeight: '900', letterSpacing: -0.5 },
  sub: { color: TUBE.textMuted, fontSize: TFONT.sm, fontWeight: '600', marginTop: 2 },
  card: { flexDirection: 'row', alignItems: 'center', gap: 14, padding: TSPACE.md, borderRadius: TRADIUS.lg, backgroundColor: TUBE.elevated, borderWidth: 1, borderColor: TUBE.line },
  icon: { width: 46, height: 46, borderRadius: 13, alignItems: 'center', justifyContent: 'center' },
  cardTitle: { color: TUBE.text, fontSize: TFONT.md, fontWeight: '800' },
  cardSub: { color: TUBE.textMuted, fontSize: TFONT.xs, fontWeight: '600', marginTop: 2 },
});
