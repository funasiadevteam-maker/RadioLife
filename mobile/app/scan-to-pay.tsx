import React, { useState, useEffect, useRef } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, TextInput,
  SafeAreaView, Linking, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT, RADIUS, common } from '../src/constants/theme';

const TOKEN_RE = /stq_[a-zA-Z0-9_-]+/;
const IS_WEB = Platform.OS === 'web';

/* Lazy-load expo-camera only on native to avoid web crash */
let CameraView: any = null;
let useCameraPermissions: any = null;
if (!IS_WEB) {
  try {
    const cam = require('expo-camera');
    CameraView = cam.CameraView;
    useCameraPermissions = cam.useCameraPermissions;
  } catch {}
}

export default function ScanToPayScreen() {
  const router = useRouter();
  const [scanned, setScanned] = useState(false);
  const [manualToken, setManualToken] = useState('');
  const [torch, setTorch] = useState(false);
  const [showManual, setShowManual] = useState(IS_WEB); // web starts with manual
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  /* Permissions — only on native */
  const permHook = !IS_WEB && useCameraPermissions ? useCameraPermissions() : [null, () => {}];
  const permission = permHook[0];
  const requestPermission = permHook[1];

  useEffect(() => {
    if (IS_WEB) return;
    timeoutRef.current = setTimeout(() => { if (!scanned) setShowManual(true); }, 5000);
    return () => { if (timeoutRef.current) clearTimeout(timeoutRef.current); };
  }, [scanned]);

  const handleBarcode = (result: any) => {
    if (scanned) return;
    const raw = result?.data || '';
    const match = raw.match(TOKEN_RE);
    const token = match ? match[0] : (raw.startsWith('stq_') ? raw : null);
    if (!token) return;
    setScanned(true);
    router.replace(`/pay-checkout/${token}`);
  };

  const submitManual = () => {
    const t = manualToken.trim();
    if (t.startsWith('stq_') || t.length > 3) {
      setScanned(true);
      router.replace(`/pay-checkout/${t}`);
    }
  };

  /* WEB: show manual entry only */
  if (IS_WEB) {
    return (
      <SafeAreaView style={common.screen}>
        <View style={s.webWrap}>
          <TouchableOpacity onPress={() => router.back()} style={{ alignSelf: 'flex-start', padding: 4 }}>
            <Ionicons name="arrow-back" size={22} color={COLORS.text} />
          </TouchableOpacity>
          <View style={s.webCenter}>
            <Ionicons name="qr-code" size={56} color={COLORS.primary} />
            <Text style={s.webTitle}>Scan to Pay</Text>
            <Text style={s.webSubtitle}>Camera scanning is available in the RadioLife mobile app. Enter a payment code below.</Text>
            <Text style={common.label}>PAYMENT CODE</Text>
            <TextInput
              style={common.input}
              placeholder="stq_abc123..."
              placeholderTextColor={COLORS.textMuted}
              value={manualToken}
              onChangeText={setManualToken}
              autoCapitalize="none"
              autoCorrect={false}
              testID="manual-token-input"
            />
            <TouchableOpacity style={[common.btnPrimary, { width: '100%', marginTop: SPACING.md }]}
              onPress={submitManual} testID="manual-submit-btn">
              <Ionicons name="arrow-forward" size={18} color="#fff" />
              <Text style={common.btnPrimaryText}>Continue</Text>
            </TouchableOpacity>
          </View>
        </View>
      </SafeAreaView>
    );
  }

  /* NATIVE: Permission denied permanently */
  if (permission && !permission.granted && !permission.canAskAgain) {
    return (
      <SafeAreaView style={common.screen}>
        <View style={s.permDenied}>
          <TouchableOpacity onPress={() => router.back()} style={s.backBtn}>
            <Ionicons name="arrow-back" size={22} color={COLORS.text} />
          </TouchableOpacity>
          <Ionicons name="camera-outline" size={48} color={COLORS.textMuted} />
          <Text style={s.permTitle}>Camera Access Required</Text>
          <Text style={s.permText}>
            RadioLife needs your camera to scan payment QR codes. Please enable camera access in your device settings.
          </Text>
          <TouchableOpacity style={common.btnPrimary} onPress={() => Linking.openSettings()}>
            <Text style={common.btnPrimaryText}>Open Settings</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[common.btnGhost, { marginTop: 12 }]} onPress={() => setShowManual(true)}>
            <Text style={common.btnGhostText}>Enter code manually</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  /* NATIVE: Permission not yet asked */
  if (!permission || !permission.granted) {
    return (
      <SafeAreaView style={common.screen}>
        <View style={s.permDenied}>
          <TouchableOpacity onPress={() => router.back()} style={s.backBtn}>
            <Ionicons name="arrow-back" size={22} color={COLORS.text} />
          </TouchableOpacity>
          <Ionicons name="qr-code" size={48} color={COLORS.primary} />
          <Text style={s.permTitle}>Scan to Pay</Text>
          <Text style={s.permText}>Allow RadioLife to access your camera to scan merchant QR codes.</Text>
          <TouchableOpacity style={common.btnPrimary} onPress={requestPermission} testID="camera-perm-btn">
            <Ionicons name="camera" size={18} color="#fff" />
            <Text style={common.btnPrimaryText}>Allow Camera</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  /* NATIVE: Camera view */
  return (
    <View style={{ flex: 1, backgroundColor: '#000' }}>
      {CameraView && (
        <CameraView
          style={StyleSheet.absoluteFillObject}
          facing="back"
          enableTorch={torch}
          barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
          onBarcodeScanned={scanned ? undefined : handleBarcode}
        />
      )}

      <SafeAreaView style={StyleSheet.absoluteFillObject} pointerEvents="box-none">
        <View style={s.topBar}>
          <TouchableOpacity onPress={() => router.back()} style={s.topBtn} testID="scan-back-btn">
            <Ionicons name="arrow-back" size={22} color="#fff" />
          </TouchableOpacity>
          <Text style={s.topTitle}>Scan to Pay</Text>
          <TouchableOpacity onPress={() => setTorch(!torch)} style={s.topBtn} testID="scan-torch-btn">
            <Ionicons name={torch ? 'flash' : 'flash-outline'} size={20} color={torch ? '#fbbf24' : '#fff'} />
          </TouchableOpacity>
        </View>

        <View style={s.centerWrap}>
          <View style={s.scanFrame} testID="scan-frame">
            <View style={[s.corner, s.cornerTL]} />
            <View style={[s.corner, s.cornerTR]} />
            <View style={[s.corner, s.cornerBL]} />
            <View style={[s.corner, s.cornerBR]} />
          </View>
          <Text style={s.hint}>Point at a RadioLife merchant QR code</Text>
        </View>

        {showManual && (
          <View style={s.manualWrap} testID="manual-entry">
            <Text style={s.manualLabel}>Or enter code manually:</Text>
            <View style={s.manualRow}>
              <TextInput
                style={s.manualInput}
                placeholder="stq_abc123..."
                placeholderTextColor="rgba(255,255,255,0.4)"
                value={manualToken}
                onChangeText={setManualToken}
                autoCapitalize="none"
                autoCorrect={false}
                testID="manual-token-input"
              />
              <TouchableOpacity style={s.manualBtn} onPress={submitManual} testID="manual-submit-btn">
                <Ionicons name="arrow-forward" size={18} color="#fff" />
              </TouchableOpacity>
            </View>
          </View>
        )}

        {!showManual && (
          <TouchableOpacity style={s.manualToggle} onPress={() => setShowManual(true)} testID="show-manual-btn">
            <Text style={s.manualToggleText}>Enter code manually</Text>
          </TouchableOpacity>
        )}
      </SafeAreaView>
    </View>
  );
}

const FRAME_SIZE = 240;
const CORNER_LEN = 28;
const CORNER_W = 3;

const s = StyleSheet.create({
  webWrap: { flex: 1, padding: SPACING.xl },
  webCenter: { flex: 1, justifyContent: 'center', alignItems: 'center', gap: 12 },
  webTitle: { fontSize: FONT.xxl, fontWeight: '900', color: COLORS.text },
  webSubtitle: { fontSize: FONT.md, color: COLORS.textDim, textAlign: 'center', lineHeight: 22, marginBottom: SPACING.lg },
  backBtn: { position: 'absolute', top: SPACING.xl, left: SPACING.lg, zIndex: 10, padding: 4 },
  permDenied: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: SPACING.xl, gap: 16 },
  permTitle: { fontSize: FONT.xl, fontWeight: '800', color: COLORS.text, textAlign: 'center' },
  permText: { fontSize: FONT.md, color: COLORS.textDim, textAlign: 'center', lineHeight: 22 },
  topBar: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: SPACING.md, paddingTop: Platform.OS === 'android' ? 40 : 10,
  },
  topBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: 'rgba(0,0,0,0.4)', alignItems: 'center', justifyContent: 'center' },
  topTitle: { color: '#fff', fontSize: FONT.lg, fontWeight: '800' },
  centerWrap: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  scanFrame: { width: FRAME_SIZE, height: FRAME_SIZE, position: 'relative' },
  corner: { position: 'absolute', width: CORNER_LEN, height: CORNER_LEN },
  cornerTL: { top: 0, left: 0, borderTopWidth: CORNER_W, borderLeftWidth: CORNER_W, borderColor: '#fff' },
  cornerTR: { top: 0, right: 0, borderTopWidth: CORNER_W, borderRightWidth: CORNER_W, borderColor: '#fff' },
  cornerBL: { bottom: 0, left: 0, borderBottomWidth: CORNER_W, borderLeftWidth: CORNER_W, borderColor: '#fff' },
  cornerBR: { bottom: 0, right: 0, borderBottomWidth: CORNER_W, borderRightWidth: CORNER_W, borderColor: '#fff' },
  hint: { color: 'rgba(255,255,255,0.7)', fontSize: FONT.sm, marginTop: 16, textAlign: 'center' },
  manualWrap: { paddingHorizontal: SPACING.xl, paddingBottom: 30 },
  manualLabel: { color: 'rgba(255,255,255,0.6)', fontSize: FONT.xs, marginBottom: 8 },
  manualRow: { flexDirection: 'row', gap: 8 },
  manualInput: {
    flex: 1, backgroundColor: 'rgba(255,255,255,0.15)', borderRadius: RADIUS.md,
    paddingHorizontal: 14, paddingVertical: 12, color: '#fff', fontSize: FONT.md,
  },
  manualBtn: {
    width: 48, height: 48, borderRadius: RADIUS.md, backgroundColor: COLORS.primary,
    alignItems: 'center', justifyContent: 'center',
  },
  manualToggle: { alignItems: 'center', paddingBottom: 30 },
  manualToggleText: { color: 'rgba(255,255,255,0.6)', fontSize: FONT.sm, textDecorationLine: 'underline' },
});
