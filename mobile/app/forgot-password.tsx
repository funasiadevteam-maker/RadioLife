import React, { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  KeyboardAvoidingView, Platform, ActivityIndicator, SafeAreaView,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../src/api/client';
import { COLORS, SPACING, FONT, common } from '../src/constants/theme';

export default function ForgotPasswordScreen() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState('');

  const submit = async () => {
    if (!email.includes('@')) { setError('Enter a valid email'); return; }
    setBusy(true);
    setError('');
    try {
      await api.post('/auth/forgot-password', { email: email.trim().toLowerCase() });
      setSent(true);
    } catch (e: any) {
      // Anti-enumeration: backend always 200s, but handle network errors
      if (e?.response?.status && e.response.status < 500) {
        setSent(true); // still show success (anti-enum)
      } else {
        setError('Network error. Please try again.');
      }
    } finally { setBusy(false); }
  };

  return (
    <SafeAreaView style={common.screen}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={{ flex: 1 }}>
        <View style={s.inner}>
          {/* Back */}
          <TouchableOpacity onPress={() => router.back()} testID="forgot-pw-back" style={s.backBtn}>
            <Ionicons name="arrow-back" size={22} color={COLORS.text} />
          </TouchableOpacity>

          <Text style={s.title}>Reset Password</Text>
          <Text style={s.subtitle}>Enter your email and we will send a reset link.</Text>

          {sent ? (
            <View testID="forgot-pw-success" style={s.successCard}>
              <Ionicons name="checkmark-circle" size={48} color={COLORS.green} />
              <Text style={s.successTitle}>Check your email</Text>
              <Text style={s.successText}>If an account exists for {email}, you will receive a reset link.</Text>
              <TouchableOpacity style={common.btnPrimary} onPress={() => router.replace('/login')} testID="forgot-pw-back-login">
                <Text style={common.btnPrimaryText}>Back to Login</Text>
              </TouchableOpacity>
            </View>
          ) : (
            <>
              <Text style={common.label}>Email Address</Text>
              <TextInput
                testID="forgot-pw-email"
                style={common.input}
                placeholder="you@example.com"
                placeholderTextColor={COLORS.textMuted}
                keyboardType="email-address"
                autoCapitalize="none"
                autoCorrect={false}
                value={email}
                onChangeText={setEmail}
              />

              {error ? <Text testID="forgot-pw-error" style={s.error}>{error}</Text> : null}

              <TouchableOpacity
                testID="forgot-pw-submit"
                style={[common.btnPrimary, { marginTop: SPACING.lg }, busy && { opacity: 0.6 }]}
                onPress={submit}
                disabled={busy}
              >
                {busy ? <ActivityIndicator color="#fff" size="small" /> : null}
                <Text style={common.btnPrimaryText}>Send Reset Link</Text>
              </TouchableOpacity>
            </>
          )}
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  inner: { flex: 1, padding: SPACING.xl, justifyContent: 'center' },
  backBtn: { position: 'absolute', top: SPACING.xl, left: SPACING.xl, zIndex: 10, padding: 4 },
  title: { fontSize: FONT.xxl, fontWeight: '900', color: COLORS.text, marginBottom: 8 },
  subtitle: { fontSize: FONT.md, color: COLORS.textDim, marginBottom: SPACING.xl },
  error: { color: COLORS.red, fontSize: FONT.sm, marginTop: SPACING.sm },
  successCard: { alignItems: 'center', gap: 12, paddingVertical: SPACING.xl },
  successTitle: { fontSize: FONT.xl, fontWeight: '800', color: COLORS.text },
  successText: { fontSize: FONT.md, color: COLORS.textDim, textAlign: 'center', lineHeight: 22 },
});
