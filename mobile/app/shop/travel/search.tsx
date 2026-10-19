// FUUSIC Travel — mobile live metasearch.
// The Travelpayouts White Label is a browser/DOM widget, so it runs inside a
// WebView here (it cannot execute natively in React Native). Same wl_id + mounts
// as the web integration (src/design_radiolife/screens/TravelWidget.jsx).
import React, { useRef, useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, ActivityIndicator, SafeAreaView, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { WebView } from 'react-native-webview';
import { COLORS, SPACING, FONT } from '../../../src/constants/theme';

const WL_HTML = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover" />
<style>
  html, body { margin: 0; padding: 0; background: #ffffff; -webkit-text-size-adjust: 100%; }
  body { padding: 10px; font-family: -apple-system, system-ui, Roboto, sans-serif; }
  #tpwl-tickets { margin-top: 12px; }
</style>
</head>
<body>
  <div id="tpwl-search"></div>
  <div id="tpwl-tickets"></div>
  <script async type="module" src="https://tpwidg.com/wl_web/main.js?wl_id=23601"></script>
</body>
</html>`;

export default function TravelSearchScreen() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const webRef = useRef<WebView>(null);

  return (
    <SafeAreaView style={styles.screen}>
      <View style={styles.topbar}>
        <Pressable onPress={() => router.back()} hitSlop={10} testID="travel-search-back" style={styles.backBtn}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </Pressable>
        <Text style={styles.title} numberOfLines={1}>Live flight search</Text>
        <View style={styles.liveBadge}><Text style={styles.liveBadgeTxt}>LIVE</Text></View>
      </View>

      <View style={{ flex: 1 }} testID="travel-search-webview">
        {Platform.OS === 'web' ? (
          <View style={styles.overlay} testID="travel-search-web-notice">
            <Ionicons name="phone-portrait-outline" size={34} color={COLORS.primary} />
            <Text style={styles.noticeTitle}>Open in the app</Text>
            <Text style={styles.loadingTxt}>
              Live flight &amp; hotel search runs inside the FUUSIC app. Open it on your
              phone to search real-time deals.
            </Text>
            <Pressable onPress={() => router.back()} style={styles.retry} testID="travel-search-web-back">
              <Text style={styles.retryTxt}>Back to deals</Text>
            </Pressable>
          </View>
        ) : (
          <WebView
            ref={webRef}
            originWhitelist={['*']}
            source={{ html: WL_HTML, baseUrl: 'https://tpwidg.com/' }}
            javaScriptEnabled
            domStorageEnabled
            setSupportMultipleWindows={false}
            startInLoadingState
            onLoadEnd={() => setLoading(false)}
            onError={() => { setFailed(true); setLoading(false); }}
            onHttpError={() => setLoading(false)}
            style={{ flex: 1, backgroundColor: '#fff' }}
          />
        )}
        {Platform.OS !== 'web' && loading && !failed && (
          <View style={styles.overlay} pointerEvents="none">
            <ActivityIndicator size="large" color={COLORS.primary} />
            <Text style={styles.loadingTxt}>Loading live deals…</Text>
          </View>
        )}
        {Platform.OS !== 'web' && failed && (
          <View style={styles.overlay} testID="travel-search-error">
            <Ionicons name="cloud-offline-outline" size={32} color={COLORS.textMuted} />
            <Text style={styles.loadingTxt}>Couldn't load live search. Check your connection.</Text>
            <Pressable onPress={() => { setFailed(false); setLoading(true); webRef.current?.reload(); }}
              style={styles.retry} testID="travel-search-retry">
              <Text style={styles.retryTxt}>Try again</Text>
            </Pressable>
          </View>
        )}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: COLORS.full || '#fff' },
  topbar: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder, backgroundColor: COLORS.card },
  backBtn: { padding: 2 },
  title: { flex: 1, color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  liveBadge: { backgroundColor: COLORS.red, borderRadius: 999, paddingHorizontal: 9, paddingVertical: 3 },
  liveBadgeTxt: { color: '#fff', fontSize: 9, fontWeight: '900', letterSpacing: 0.5 },
  overlay: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, alignItems: 'center', justifyContent: 'center', gap: 10, backgroundColor: 'rgba(255,255,255,0.92)' },
  loadingTxt: { color: COLORS.textMuted, fontSize: FONT.sm, fontWeight: '700', textAlign: 'center', paddingHorizontal: 30 },
  noticeTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900', marginTop: 2 },
  retry: { backgroundColor: COLORS.primary, borderRadius: 999, paddingHorizontal: 18, paddingVertical: 10, marginTop: 6 },
  retryTxt: { color: '#fff', fontSize: FONT.sm, fontWeight: '900' },
});
