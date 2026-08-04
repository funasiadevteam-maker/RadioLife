import React, { useEffect, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, ActivityIndicator,
  SafeAreaView,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../../src/constants/theme';
import api from '../../../src/api/client';

interface Category {
  id: string;
  name: string;
  icon?: string;
  tagline?: string;
}

export default function TriviaRoomCreateScreen() {
  const router = useRouter();
  const [cats, setCats] = useState<Category[]>([]);
  const [chosen, setChosen] = useState<Category | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get('/trivia/categories')
      .then((r) => setCats(r.data?.categories || []))
      .catch(() => {});
  }, []);

  const createRoom = async () => {
    if (!chosen || busy) return;
    setBusy(true);
    try {
      const r = await api.post('/trivia/rooms', { category_id: chosen.id, is_private: false });
      router.replace(`/trivia/rooms/${r.data.room_code}`);
    } catch (e: any) {
      setBusy(false);
    }
  };

  return (
    <SafeAreaView style={common.screen} testID="trivia-room-create">
      <ScrollView contentContainerStyle={s.scroll}>
        <TouchableOpacity onPress={() => router.back()} style={s.backRow}>
          <Ionicons name="chevron-back" size={16} color={COLORS.textDim} />
          <Text style={s.backText}>Trivia</Text>
        </TouchableOpacity>

        <Text style={s.title}>
          Host a <Text style={{ color: COLORS.primary }}>live room</Text>
        </Text>
        <Text style={s.sub}>Pick a topic, share the code, beat your friends. 10 questions, 15 seconds each.</Text>

        {cats.map((c) => (
          <TouchableOpacity
            key={c.id}
            onPress={() => setChosen(c)}
            testID={`trivia-room-cat-${c.id}`}
            style={[s.catCard, chosen?.id === c.id && s.catCardSelected]}
            activeOpacity={0.7}
          >
            <Text style={s.catIcon}>{c.icon || '🧠'}</Text>
            <View style={{ flex: 1 }}>
              <Text style={s.catName}>{c.name}</Text>
              {c.tagline ? <Text style={s.catTag}>{c.tagline}</Text> : null}
            </View>
            {chosen?.id === c.id && <Ionicons name="checkmark-circle" size={18} color={COLORS.secondary} />}
          </TouchableOpacity>
        ))}

        <TouchableOpacity
          style={[common.btnPrimary, (!chosen || busy) && { opacity: 0.5 }]}
          onPress={createRoom}
          disabled={!chosen || busy}
          testID="trivia-room-create-btn"
        >
          {busy && <ActivityIndicator size="small" color="#fff" />}
          <Text style={common.btnPrimaryText}>Create room</Text>
          <Ionicons name="chevron-forward" size={14} color="#fff" />
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  scroll: { padding: SPACING.md, paddingBottom: 100 },
  backRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: SPACING.md },
  backText: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '600' },
  title: { fontSize: 28, fontWeight: '900', color: COLORS.text, marginBottom: 8 },
  sub: { fontSize: 13, color: COLORS.textDim, marginBottom: SPACING.lg, lineHeight: 18 },
  catCard: {
    flexDirection: 'row', alignItems: 'center', gap: SPACING.md,
    backgroundColor: COLORS.card, borderRadius: RADIUS.lg,
    borderWidth: 1, borderColor: COLORS.cardBorder, padding: SPACING.md,
    marginBottom: SPACING.sm,
  },
  catCardSelected: { borderColor: COLORS.secondary, backgroundColor: 'rgba(59,130,246,0.05)' },
  catIcon: { fontSize: 24 },
  catName: { fontSize: 15, fontWeight: '800', color: COLORS.text },
  catTag: { fontSize: 11, color: COLORS.textDim, marginTop: 2 },
});
