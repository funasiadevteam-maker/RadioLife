// FUUSIC Travel — mobile live metasearch (Flights · Hotels · Cars).
// Travelpayouts widgets are browser/DOM scripts, so they run inside a WebView
// here (they cannot execute natively in React Native). Flights uses the White
// Label module (same wl_id as web); Hotels (Klook) & Cars use content widgets.
import React, { useRef, useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, ActivityIndicator, SafeAreaView, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { WebView } from 'react-native-webview';
import { COLORS, SPACING, FONT } from '../../../src/constants/theme';

type Tab = 'flights' | 'hotels' | 'cars';

const WL_FLIGHTS = `<!DOCTYPE html>
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

const KLOOK_HOTELS = 'https://tpwidg.com/content?currency=USD&trs=587763&shmarker=174867&locale=en-US&city_id=2&category=4&amount=6&powered_by=true&campaign_id=137&promo_id=4497&sub_id=fuusic_app';
const CARS = 'https://tpwidg.com/content?trs=587763&shmarker=174867&locale=en-US&country=153&city=68511&powered_by=true&campaign_id=87&promo_id=2466&sub_id=fuusic_app';

const contentHtml = (src: string) => `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
<style>
  html, body { margin: 0; padding: 10px; background: #ffffff; font-family: -apple-system, system-ui, Roboto, sans-serif; }
</style>
</head>
<body>
  <script async charset="utf-8" src="${src}"></script>
</body>
</html>`;

const htmlFor = (t: Tab) =>
  t === 'flights' ? WL_FLIGHTS : t === 'hotels' ? contentHtml(KLOOK_HOTELS) : contentHtml(CARS);

const TABS: { key: Tab; label: string; icon: any }[] = [
  { key: 'flights', label: 'Flights', icon: 'airplane' },
  { key: 'hotels', label: 'Hotels', icon: 'bed' },
  { key: 'cars', label: 'Cars', icon: 'car-sport' },
];

export default function TravelSearchScreen() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [tab, setTab] = useState<Tab>('flights');
  const webRef = useRef<WebView>(null);

  const switchTab = (t: Tab) => {
    if (t === tab) return;
    setTab(t); setLoading(true); setFailed(false);
  };

  return (
    <SafeAreaView style={styles.screen}>
      <View style={styles.topbar}>
        <Pressable onPress={() => router.back()} hitSlop={10} testID="travel-search-back" style={styles.backBtn}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </Pressable>
        <Text style={styles.title} numberOfLines={1}>Live search</Text>
        <View style={styles.liveBadge}><Text style={styles.liveBadgeTxt}>LIVE</Text></View>
      </View>

      <View style={styles.tabs}>
        {TABS.map((t) => {
          const on = tab === t.key;
          return (
            <Pressable key={t.key} onPress={() => switchTab(t.key)} testID={`travel-tab-${t.key}`}
              style={[styles.tab, on && styles.tabOn]}>
              <Ionicons name={t.icon} size={14} color={on ? '#fff' : COLORS.textMuted} />
              <Text style={[styles.tabTxt, on && styles.tabTxtOn]}>{t.label}</Text>
            </Pressable>
          );
        })}
      </View>

      <View style={{ flex: 1 }} testID="travel-search-webview">
        {Platform.OS === 'web' ? (
          <View style={styles.overlay} testID="travel-search-web-notice">
            <Ionicons name="phone-portrait-outline" size={34} color={COLORS.primary} />
            <Text style={styles.noticeTitle}>Open in the app</Text>
            <Text style={styles.loadingTxt}>
              Live flight, hotel &amp; car search runs inside the FUUSIC app. Open it on your
              phone to search real-time deals.
            </Text>
            <Pressable onPress={() => router.back()} style={styles.retry} testID="travel-search-web-back">
              <Text style={styles.retryTxt}>Back to deals</Text>
            </Pressable>
          </View>
        ) : (
          <WebView
            key={tab}
            ref={webRef}
            originWhitelist={['*']}
            source={{ html: htmlFor(tab), baseUrl: 'https://tpwidg.com/' }}
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
  tabs: { flexDirection: 'row', gap: 8, paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, backgroundColor: COLORS.card, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  tab: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 999, backgroundColor: COLORS.inputBg },
  tabOn: { backgroundColor: COLORS.primary },
  tabTxt: { color: COLORS.textMuted, fontSize: FONT.sm, fontWeight: '900' },
  tabTxtOn: { color: '#fff' },
});
