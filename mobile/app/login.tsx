import React, { useState, useEffect } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet, ActivityIndicator,
  KeyboardAvoidingView, Platform, ScrollView, Alert,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useAuth } from '../src/contexts/AuthContext';
import { COLORS, SPACING, RADIUS, FONT } from '../src/constants/theme';
import { Ionicons } from '@expo/vector-icons';
import * as AppleAuthentication from 'expo-apple-authentication';
import * as SecureStore from 'expo-secure-store';
import axios from 'axios';

export default function Login() {
  const { user, loading, login, register, googleSignIn } = useAuth();
  const router = useRouter();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (loading) return;
    if (user) {
      router.replace(user.onboarding_complete ? '/(tabs)/home' : '/onboarding');
    }
  }, [user, loading]);

  const submit = async () => {
    if (busy) return;
    setBusy(true);
    try {
      if (mode === 'login') {
        const u = await login(email.trim(), password);
        Alert.alert('Welcome back', u.name);
        router.replace(u.onboarding_complete ? '/(tabs)/radio' : '/onboarding');
      } else {
        const u = await register(email.trim(), password, name.trim() || email.split('@')[0]);
        Alert.alert('Account created', `Welcome, ${u.name}!`);
        router.replace('/onboarding');
      }
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      let message: string;
      if (Array.isArray(detail)) {
        message = detail.map((d: any) => d.msg || 'invalid').join(' · ');
      } else if (typeof detail === 'string') {
        message = detail;
      } else if (e?.response?.status === 409) {
        message = 'Email already registered — try signing in.';
      } else if (e?.response?.status === 401) {
        message = 'Invalid email or password.';
      } else {
        message = `Could not ${mode}. Please try again.`;
      }
      Alert.alert('Error', message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={s.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <ScrollView
        contentContainerStyle={s.scroll}
        keyboardShouldPersistTaps="handled"
      >
        <View style={s.brand} testID="login-brand">
          <View style={s.dot} />
          <Text style={s.brandName}>
            BigFM <Text style={s.brandDxb}>Dubai</Text>
          </Text>
        </View>

        <Text style={s.title} testID="login-title">
          {mode === 'login' ? 'Sign in to start' : 'Create your account'}
        </Text>
        <Text style={s.sub}>
          {mode === 'login'
            ? 'Aapka personalized Hinglish radio chalu karne ke liye ek tap door.'
            : 'Tell us your taste once, then non-stop music.'}
        </Text>

        <TouchableOpacity
          style={s.googleBtn}
          onPress={googleSignIn}
          testID="google-signin-btn"
          activeOpacity={0.8}
        >
          <Ionicons name="logo-google" size={18} color="#fff" />
          <Text style={s.googleText}>Continue with Google</Text>
        </TouchableOpacity>

        {Platform.OS === 'ios' && (
          <TouchableOpacity
            style={s.appleBtn}
            onPress={async () => {
              if (busy) return;
              setBusy(true);
              try {
                const r = await AppleAuthentication.signInAsync({
                  requestedScopes: [
                    AppleAuthentication.AppleAuthenticationScope.FULL_NAME,
                    AppleAuthentication.AppleAuthenticationScope.EMAIL,
                  ],
                });
                if (!r.identityToken) {
                  throw new Error('Apple did not return an identityToken');
                }
                const profile_name = (r.fullName && (r.fullName.givenName ||
                                                    r.fullName.familyName))
                  ? { firstName: r.fullName.givenName || '',
                        lastName:  r.fullName.familyName || '' }
                  : undefined;
                const apiBase = (process.env.EXPO_PUBLIC_BACKEND_URL || '')
                                          .replace(/\/+$/, '');
                const resp = await axios.post(
                  `${apiBase}/api/auth/apple/mobile`,
                  { identity_token: r.identityToken, profile_name });
                await SecureStore.setItemAsync(
                  'bigfm_session_token', resp.data.session_token);
                router.replace(resp.data.is_new_user
                                          ? '/onboarding'
                                          : '/(tabs)/radio');
              } catch (e: any) {
                if (e?.code !== 'ERR_CANCELED') {
                  Alert.alert('Apple sign-in failed',
                    e?.response?.data?.detail || e?.message || String(e));
                }
              } finally {
                setBusy(false);
              }
            }}
            testID="apple-signin-btn"
            activeOpacity={0.8}
          >
            <Ionicons name="logo-apple" size={18} color="#fff" />
            <Text style={s.googleText}>Sign in with Apple</Text>
          </TouchableOpacity>
        )}

        <TouchableOpacity
          style={s.demoBtn}
          onPress={async () => {
            if (busy) return;
            setBusy(true);
            try {
              const apiBase = (process.env.EXPO_PUBLIC_BACKEND_URL || '')
                                          .replace(/\/+$/, '');
              const resp = await axios.post(`${apiBase}/api/auth/demo`);
              await SecureStore.setItemAsync(
                'bigfm_session_token', resp.data.session_token);
              router.replace(resp.data.onboarding_complete
                                          ? '/(tabs)/radio'
                                          : '/onboarding');
            } catch (e: any) {
              const status = e?.response?.status;
              const msg = status === 429
                ? 'Demo login rate limit — try again in a minute.'
                : (e?.response?.data?.detail || e?.message ||
                    'Could not start the demo.');
              Alert.alert('Demo login', msg);
            } finally {
              setBusy(false);
            }
          }}
          testID="demo-login-btn"
          activeOpacity={0.8}
        >
          <Ionicons name="play-circle-outline" size={18} color="#7BD3F7" />
          <Text style={s.demoText}>Try the demo</Text>
        </TouchableOpacity>

        <View style={s.orRow}>
          <View style={s.orLine} />
          <Text style={s.orText}>OR WITH EMAIL</Text>
          <View style={s.orLine} />
        </View>

        {mode === 'register' && (
          <TextInput
            style={s.input}
            placeholder="Display name"
            placeholderTextColor={COLORS.textMuted}
            value={name}
            onChangeText={setName}
            autoCapitalize="words"
            testID="auth-name-input"
          />
        )}
        <TextInput
          style={s.input}
          placeholder="you@example.com"
          placeholderTextColor={COLORS.textMuted}
          value={email}
          onChangeText={setEmail}
          keyboardType="email-address"
          autoCapitalize="none"
          autoComplete="email"
          testID="auth-email-input"
        />
        <TextInput
          style={s.input}
          placeholder={mode === 'register' ? '8+ chars, letters & digits' : 'Password'}
          placeholderTextColor={COLORS.textMuted}
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
          testID="auth-password-input"
        />

        <TouchableOpacity
          style={[s.submitBtn, busy && { opacity: 0.6 }]}
          onPress={submit}
          disabled={busy}
          testID="auth-submit-btn"
          activeOpacity={0.8}
        >
          {busy ? (
            <ActivityIndicator color="#fff" size="small" />
          ) : (
            <>
              <Ionicons name="radio" size={16} color="#fff" />
              <Text style={s.submitText}>
                {mode === 'login' ? 'Sign in' : 'Create account'}
              </Text>
              <Ionicons name="chevron-forward" size={16} color="#fff" />
            </>
          )}
        </TouchableOpacity>

        <View style={s.switchRow}>
          <Text style={s.switchText}>
            {mode === 'login' ? 'New to BigFM Dubai? ' : 'Already with us? '}
          </Text>
          <TouchableOpacity
            onPress={() => setMode(mode === 'login' ? 'register' : 'login')}
            testID={mode === 'login' ? 'switch-to-register' : 'switch-to-login'}
          >
            <Text style={s.switchLink}>
              {mode === 'login' ? 'Create an account' : 'Sign in'}
            </Text>
          </TouchableOpacity>
        </View>

        {mode === 'login' && (
          <TouchableOpacity
            onPress={() => router.push('/forgot-password')}
            testID="forgot-password-link"
            style={{ alignSelf: 'center', marginTop: SPACING.md }}
          >
            <Text style={s.switchLink}>Forgot password?</Text>
          </TouchableOpacity>
        )}

        <Text style={s.footer}>BIGFM DUBAI · MOBILE</Text>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.bg },
  scroll: { flexGrow: 1, justifyContent: 'center', padding: SPACING.xl, paddingBottom: 60 },
  brand: { flexDirection: 'row', alignItems: 'center', marginBottom: SPACING.xl, gap: 10 },
  dot: { width: 12, height: 12, borderRadius: 6, backgroundColor: COLORS.primary },
  brandName: { color: COLORS.text, fontSize: FONT.xl, fontWeight: '900', letterSpacing: -0.5 },
  brandDxb: { color: COLORS.secondary },
  title: { color: COLORS.text, fontSize: FONT.xxl, fontWeight: '900', marginBottom: SPACING.sm },
  sub: { color: COLORS.textDim, fontSize: FONT.md, lineHeight: 22, marginBottom: SPACING.xl },
  googleBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10,
    backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder,
    paddingVertical: 16, borderRadius: RADIUS.lg,
  },
  appleBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10,
    backgroundColor: '#000', borderWidth: 1, borderColor: '#000',
    paddingVertical: 16, borderRadius: RADIUS.lg, marginTop: SPACING.sm,
  },
  demoBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    backgroundColor: 'transparent', borderWidth: 1, borderColor: '#7BD3F7',
    paddingVertical: 14, borderRadius: RADIUS.lg, marginTop: SPACING.sm,
  },
  demoText: { color: '#7BD3F7', fontWeight: '700', fontSize: FONT.md },
  googleText: { color: '#fff', fontWeight: '700', fontSize: FONT.md },
  orRow: { flexDirection: 'row', alignItems: 'center', marginVertical: SPACING.lg },
  orLine: { flex: 1, height: 1, backgroundColor: COLORS.surfaceBorder },
  orText: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '700', letterSpacing: 2, marginHorizontal: 12 },
  input: {
    backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.inputBorder,
    borderRadius: RADIUS.md, padding: 16, color: COLORS.text, fontSize: FONT.md, marginBottom: SPACING.md,
  },
  submitBtn: {
    backgroundColor: COLORS.primary, flexDirection: 'row', alignItems: 'center',
    justifyContent: 'center', gap: 8, paddingVertical: 16, borderRadius: RADIUS.lg,
    marginTop: SPACING.sm,
  },
  submitText: { color: '#fff', fontWeight: '800', fontSize: FONT.md },
  switchRow: { flexDirection: 'row', justifyContent: 'center', marginTop: SPACING.xl },
  switchText: { color: COLORS.textDim, fontSize: FONT.sm },
  switchLink: { color: COLORS.secondary, fontSize: FONT.sm, fontWeight: '700' },
  footer: {
    color: COLORS.textMuted, fontSize: FONT.xs, textAlign: 'center',
    marginTop: SPACING.xxl, letterSpacing: 2, fontWeight: '700',
  },
});
