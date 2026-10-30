/* Companion Memory — standalone screen (reached from Profile preferences). */
import React from 'react';
import { View, Text, ScrollView, TouchableOpacity, StyleSheet, SafeAreaView } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT, common } from '../src/constants/theme';
import FunAiMemory from '../src/fun-ai/FunAiMemory';

export default function FunAiMemoryScreen() {
  const router = useRouter();
  return (
    <SafeAreaView style={common.screen}>
      <ScrollView contentContainerStyle={st.scroll}>
        <View style={st.headerRow}>
          <TouchableOpacity testID="fai-memory-back" onPress={() => router.back()} hitSlop={10}>
            <Ionicons name="chevron-back" size={24} color={COLORS.text} />
          </TouchableOpacity>
          <View style={{ flex: 1 }}>
            <Text style={st.title}>Companion Memory</Text>
            <Text style={st.subtitle}>What Fun AI remembers about your taste</Text>
          </View>
        </View>
        <FunAiMemory />
        <Text style={st.note}>
          Fun AI uses these approved preferences to tailor your radio and news. Turn memory off any
          time — nothing is used unless you add it here.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  scroll: { padding: SPACING.lg, paddingBottom: 48 },
  headerRow: { flexDirection: 'row', alignItems: 'center', gap: SPACING.sm, marginBottom: SPACING.lg },
  title: { color: COLORS.text, fontSize: FONT.xxl, fontWeight: '900' },
  subtitle: { color: COLORS.textDim, fontSize: FONT.sm, marginTop: 2 },
  note: { color: COLORS.textMuted, fontSize: FONT.xs, lineHeight: 18, marginTop: SPACING.lg },
});
