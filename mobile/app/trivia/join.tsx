import React, { useState } from 'react';
import {
  View, Text, TouchableOpacity, TextInput, StyleSheet,
  SafeAreaView, KeyboardAvoidingView, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';
import { normalizeRoomCode, isValidRoomCode } from '../../src/utils/normalizeRoomCode';

export default function TriviaJoinScreen() {
  const router = useRouter();
  const [code, setCode] = useState('');
  const canon = normalizeRoomCode(code);
  const valid = isValidRoomCode(canon);

  const go = () => {
    if (!valid) return;
    router.push(`/trivia/rooms/${canon}`);
  };

  return (
    <SafeAreaView style={common.screen} testID="trivia-join">
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={{ flex: 1 }}
      >
        <View style={s.container}>
          <TouchableOpacity onPress={() => router.back()} style={s.backRow}>
            <Ionicons name="chevron-back" size={16} color={COLORS.textDim} />
            <Text style={s.backText}>Trivia</Text>
          </TouchableOpacity>

          <Text style={s.title}>
            Join a <Text style={{ color: COLORS.secondary }}>live room</Text>
          </Text>
          <Text style={s.sub}>
            Paste or type the 10-char code your host shared (e.g. BFM-XJG979).
          </Text>

          <TextInput
            value={code}
            onChangeText={(t) => setCode(t.toUpperCase())}
            placeholder="BFM-XXXXXX"
            placeholderTextColor={COLORS.textDim}
            autoCapitalize="characters"
            autoFocus
            style={s.input}
            testID="trivia-join-input"
          />

          {code.length > 0 && (
            <Text style={s.preview} testID="trivia-join-preview">
              Will join: <Text style={{ color: COLORS.secondary }}>{canon || '—'}</Text>
            </Text>
          )}

          <TouchableOpacity
            style={[common.btnPrimary, !valid && { opacity: 0.5 }]}
            onPress={go}
            disabled={!valid}
            testID="trivia-join-btn"
          >
            <Text style={common.btnPrimaryText}>Join room</Text>
            <Ionicons name="chevron-forward" size={14} color="#fff" />
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container: { padding: SPACING.md, paddingTop: SPACING.lg },
  backRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: SPACING.md },
  backText: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '600' },
  title: { fontSize: 28, fontWeight: '900', color: '#fff', marginBottom: 8 },
  sub: { fontSize: 13, color: COLORS.textDim, marginBottom: SPACING.lg, lineHeight: 18 },
  input: {
    backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.inputBorder,
    borderRadius: RADIUS.md, padding: 16, color: '#fff', fontSize: 22,
    fontWeight: '700', letterSpacing: 3, textAlign: 'center', marginBottom: SPACING.sm,
  },
  preview: { fontSize: 11, color: COLORS.textDim, textAlign: 'center', marginBottom: SPACING.lg },
});
